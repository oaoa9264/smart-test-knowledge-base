import json
import threading
from datetime import datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import AnalysisStage, RiskAnalysisTask, RiskAnalysisTaskStatus
from app.schemas.risk_convergence import (
    BlockingRisk,
    ConflictItem,
    EffectiveSnapshotRead,
    MatchedEvidence,
    ReopenedRisk,
    ResolvedRisk,
    RiskItemCompact,
)
from app.services.effective_requirement_service import generate_review_snapshot
from app.services.predev_analyzer import analyze_for_predev
from app.services.prerelease_auditor import audit_for_prerelease


class RiskAnalysisTaskConflictError(Exception):
    pass


_IN_PROGRESS_STATUSES = {
    RiskAnalysisTaskStatus.queued,
    RiskAnalysisTaskStatus.running,
}

_STAGE_PROGRESS_MESSAGES = {
    AnalysisStage.review: "已接受评审分析任务，等待开始执行",
    AnalysisStage.pre_dev: "已接受开发前分析任务，等待开始执行",
    AnalysisStage.pre_release: "已接受提测前审计任务，等待开始执行",
}

_STAGE_RUNNING_MESSAGES = {
    AnalysisStage.review: "正在生成评审快照",
    AnalysisStage.pre_dev: "正在执行开发前分析",
    AnalysisStage.pre_release: "正在执行提测前审计",
}

_STAGE_COMPLETED_MESSAGES = {
    AnalysisStage.review: "评审分析完成",
    AnalysisStage.pre_dev: "开发前分析完成",
    AnalysisStage.pre_release: "提测前审计完成",
}


def _run_risk_analysis_task(task_id: int) -> None:
    run_risk_analysis_task(task_id=task_id, db_session_factory=SessionLocal)


def _launch_risk_analysis_task_worker(task_id: int) -> None:
    worker = threading.Thread(
        target=_run_risk_analysis_task,
        kwargs={"task_id": task_id},
        daemon=True,
    )
    worker.start()


def get_risk_analysis_task(db: Session, requirement_id: int, stage: AnalysisStage) -> RiskAnalysisTask:
    return (
        db.query(RiskAnalysisTask)
        .filter(
            RiskAnalysisTask.requirement_id == requirement_id,
            RiskAnalysisTask.stage == stage,
        )
        .first()
    )


def _serialize_snapshot(snapshot):
    if snapshot is None:
        return None
    if isinstance(snapshot, dict):
        return jsonable_encoder(snapshot)
    return jsonable_encoder(EffectiveSnapshotRead.from_orm(snapshot))


def _serialize_risks(items):
    payload = []
    for item in items or []:
        if isinstance(item, dict):
            payload.append(jsonable_encoder(item))
        else:
            payload.append(jsonable_encoder(RiskItemCompact.from_orm(item)))
    return payload


def _serialize_models(items, schema_cls):
    payload = []
    for item in items or []:
        if isinstance(item, dict):
            payload.append(jsonable_encoder(schema_cls(**item)))
        else:
            payload.append(jsonable_encoder(schema_cls.from_orm(item)))
    return payload


def _serialize_result(stage: AnalysisStage, result):
    if stage == AnalysisStage.review:
        return {
            "snapshot": _serialize_snapshot(result.get("snapshot")),
            "risks": _serialize_risks(result.get("risks", [])),
            "clarification_hints": list(result.get("clarification_hints", [])),
        }
    if stage == AnalysisStage.pre_dev:
        return {
            "snapshot": _serialize_snapshot(result.get("snapshot")),
            "risks": _serialize_risks(result.get("risks", [])),
            "conflicts": _serialize_models(result.get("conflicts", []), ConflictItem),
            "matched_evidence": _serialize_models(result.get("matched_evidence", []), MatchedEvidence),
        }
    return {
        "closure_summary": result.get("closure_summary", ""),
        "blocking_risks": _serialize_models(result.get("blocking_risks", []), BlockingRisk),
        "reopened_risks": _serialize_models(result.get("reopened_risks", []), ReopenedRisk),
        "resolved_risks": _serialize_models(result.get("resolved_risks", []), ResolvedRisk),
        "audit_notes": list(result.get("audit_notes", [])),
    }


def _extract_snapshot_id(result):
    snapshot = result.get("snapshot") if isinstance(result, dict) else None
    if isinstance(snapshot, dict):
        return snapshot.get("id")
    return getattr(snapshot, "id", None)


def run_risk_analysis_task(task_id: int, db_session_factory=SessionLocal) -> None:
    db = db_session_factory()
    try:
        task = db.query(RiskAnalysisTask).filter(RiskAnalysisTask.id == task_id).first()
        if not task:
            return

        task.status = RiskAnalysisTaskStatus.running
        task.progress_message = _STAGE_RUNNING_MESSAGES[task.stage]
        task.progress_percent = 45
        task.last_error = None
        db.commit()
        db.refresh(task)

        if task.stage == AnalysisStage.review:
            result = generate_review_snapshot(db=db, requirement_id=task.requirement_id)
        elif task.stage == AnalysisStage.pre_dev:
            result = analyze_for_predev(db=db, requirement_id=task.requirement_id)
        else:
            result = audit_for_prerelease(db=db, requirement_id=task.requirement_id)

        snapshot_id = _extract_snapshot_id(result)
        if snapshot_id is not None:
            task.snapshot_id = snapshot_id
        task.result_json = json.dumps(jsonable_encoder(_serialize_result(task.stage, result)), ensure_ascii=False)
        task.status = RiskAnalysisTaskStatus.completed
        task.progress_message = _STAGE_COMPLETED_MESSAGES[task.stage]
        task.progress_percent = 100
        task.last_error = None
        task.current_task_finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        task = db.query(RiskAnalysisTask).filter(RiskAnalysisTask.id == task_id).first()
        if task:
            task.status = RiskAnalysisTaskStatus.failed
            task.progress_message = "分析执行失败"
            task.progress_percent = 100
            task.last_error = str(exc)
            task.current_task_finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def start_risk_analysis_task(db: Session, requirement_id: int, stage: AnalysisStage) -> RiskAnalysisTask:
    task = get_risk_analysis_task(db, requirement_id, stage)
    if task and task.status in _IN_PROGRESS_STATUSES:
        raise RiskAnalysisTaskConflictError("当前阶段分析进行中，请稍后再试")

    if not task:
        task = RiskAnalysisTask(
            requirement_id=requirement_id,
            stage=stage,
        )
        db.add(task)

    task.status = RiskAnalysisTaskStatus.queued
    task.progress_message = _STAGE_PROGRESS_MESSAGES[stage]
    task.progress_percent = 5
    task.last_error = None
    task.current_task_started_at = datetime.utcnow()
    task.current_task_finished_at = None

    db.commit()
    db.refresh(task)

    _launch_risk_analysis_task_worker(task.id)
    return task
