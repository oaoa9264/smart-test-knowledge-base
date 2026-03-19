import json
import threading
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import (
    NormalizedRequirementDocTask,
    Requirement,
    RiskAnalysisTaskStatus,
)
from app.services.effective_requirement_service import (
    annotate_snapshot_freshness,
    compute_basis_hash,
    get_latest_snapshot,
    list_requirement_inputs,
)
from app.services.normalized_requirement_doc_service import (
    build_normalized_requirement_doc_source_payload,
    generate_normalized_requirement_doc_from_task_payloads,
    serialize_normalized_requirement_snapshot,
)


class NormalizedRequirementDocTaskConflictError(Exception):
    pass


_IN_PROGRESS_STATUSES = {
    RiskAnalysisTaskStatus.queued,
    RiskAnalysisTaskStatus.running,
}


def _run_normalized_requirement_doc_task(task_id: int) -> None:
    run_normalized_requirement_doc_task(task_id=task_id, db_session_factory=SessionLocal)


def _launch_normalized_requirement_doc_task_worker(task_id: int) -> None:
    worker = threading.Thread(
        target=_run_normalized_requirement_doc_task,
        kwargs={"task_id": task_id},
        daemon=True,
    )
    worker.start()


def get_normalized_requirement_doc_task(db: Session, requirement_id: int) -> Optional[NormalizedRequirementDocTask]:
    return (
        db.query(NormalizedRequirementDocTask)
        .filter(NormalizedRequirementDocTask.requirement_id == requirement_id)
        .first()
    )


def start_normalized_requirement_doc_task(db: Session, requirement_id: int) -> NormalizedRequirementDocTask:
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    task = get_normalized_requirement_doc_task(db, requirement_id)
    if task and task.status in _IN_PROGRESS_STATUSES:
        raise NormalizedRequirementDocTaskConflictError("规范化需求文档生成进行中，请稍后再试")

    inputs = list_requirement_inputs(db, requirement_id)
    latest_snapshot = annotate_snapshot_freshness(
        db,
        get_latest_snapshot(db, requirement_id),
        requirement=requirement,
        inputs=inputs,
    )
    basis_hash = compute_basis_hash(requirement, inputs)
    uses_fresh_snapshot = bool(latest_snapshot and not latest_snapshot.is_stale)
    snapshot_stale = bool(latest_snapshot and latest_snapshot.is_stale)
    source_payload = build_normalized_requirement_doc_source_payload(requirement, inputs)
    snapshot_payload = serialize_normalized_requirement_snapshot(latest_snapshot) if uses_fresh_snapshot else None

    if not task:
        task = NormalizedRequirementDocTask(requirement_id=requirement_id)
        db.add(task)

    task.status = RiskAnalysisTaskStatus.queued
    task.progress_message = "已接受规范化需求文档生成任务，等待开始执行"
    task.progress_percent = 5
    task.last_error = None
    task.basis_hash = basis_hash
    task.uses_fresh_snapshot = uses_fresh_snapshot
    task.snapshot_stale = snapshot_stale
    task.source_payload_json = json.dumps(source_payload, ensure_ascii=False)
    task.snapshot_payload_json = json.dumps(snapshot_payload, ensure_ascii=False) if snapshot_payload is not None else None
    task.result_markdown = None
    task.llm_provider = None
    task.current_task_started_at = datetime.utcnow()
    task.current_task_finished_at = None

    db.commit()
    db.refresh(task)

    _launch_normalized_requirement_doc_task_worker(task.id)
    return task


def run_normalized_requirement_doc_task(task_id: int, db_session_factory=SessionLocal) -> None:
    db = db_session_factory()
    try:
        task = db.query(NormalizedRequirementDocTask).filter(NormalizedRequirementDocTask.id == task_id).first()
        if not task:
            return

        task.status = RiskAnalysisTaskStatus.running
        task.progress_message = "正在生成规范化需求文档"
        task.progress_percent = 45
        task.last_error = None
        db.commit()
        db.refresh(task)

        source_payload = json.loads(task.source_payload_json or "{}")
        snapshot_payload = json.loads(task.snapshot_payload_json) if task.snapshot_payload_json else None
        result = generate_normalized_requirement_doc_from_task_payloads(
            source_payload=source_payload,
            snapshot_payload=snapshot_payload,
        )

        task.result_markdown = result.get("markdown", "")
        task.llm_provider = result.get("llm_provider")
        task.status = RiskAnalysisTaskStatus.completed
        task.progress_message = "规范化需求文档生成完成"
        task.progress_percent = 100
        task.current_task_finished_at = datetime.utcnow()
        task.last_error = None
        db.commit()
    except Exception as exc:
        db.rollback()
        task = db.query(NormalizedRequirementDocTask).filter(NormalizedRequirementDocTask.id == task_id).first()
        if task:
            task.status = RiskAnalysisTaskStatus.failed
            task.progress_message = "规范化需求文档生成失败"
            task.progress_percent = 100
            task.last_error = str(exc)
            task.current_task_finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
