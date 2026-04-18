import json
import logging
import threading
from datetime import datetime
from typing import List

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


def start_risk_analysis_task(
    db: Session, requirement_id: int, stage: AnalysisStage, auto_launch: bool = True,
) -> RiskAnalysisTask:
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

    if auto_launch:
        _launch_risk_analysis_task_worker(task.id)
    return task


logger = logging.getLogger(__name__)

_UNIFIED_STAGE_ORDER = [
    AnalysisStage.review,
    AnalysisStage.pre_dev,
    AnalysisStage.pre_release,
]

_UNIFIED_PROGRESS_MESSAGES = {
    AnalysisStage.review: "统一分析：正在执行评审分析",
    AnalysisStage.pre_dev: "统一分析：正在执行开发前分析",
    AnalysisStage.pre_release: "统一分析：正在执行发布前审计",
}


def start_unified_risk_analysis(db: Session, requirement_id: int) -> List[AnalysisStage]:
    """Determine which stages need execution and launch a unified background worker.

    Returns the list of stages that will be executed.
    """
    from app.models.entities import NodeStatus, Requirement, RuleNode
    from app.services.effective_requirement_service import (
        get_latest_snapshot,
        is_snapshot_stale,
    )
    from app.services.requirement_context_helpers import list_requirement_inputs

    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    # Check for any in-progress tasks
    for stage in _UNIFIED_STAGE_ORDER:
        task = get_risk_analysis_task(db, requirement_id, stage)
        if task and task.status in _IN_PROGRESS_STATUSES:
            raise RiskAnalysisTaskConflictError("当前有阶段分析进行中，请稍后再试")

    inputs = list_requirement_inputs(db, requirement_id)
    review_snapshot = get_latest_snapshot(db, requirement_id, stage="review")

    stages_to_run: List[AnalysisStage] = []

    # 1. Review: needed if no snapshot or snapshot is stale
    need_review = not review_snapshot or is_snapshot_stale(requirement, inputs, review_snapshot)
    if need_review:
        stages_to_run.append(AnalysisStage.review)

    # 2. Pre-dev: needed if rule tree nodes exist
    has_nodes = (
        db.query(RuleNode)
        .filter(
            RuleNode.requirement_id == requirement_id,
            RuleNode.status != NodeStatus.deleted,
        )
        .count()
        > 0
    )
    if has_nodes:
        stages_to_run.append(AnalysisStage.pre_dev)

    # 3. Pre-release: only add when there is already a set of committed nodes
    #    AND the latest review/pre_dev runs didn't just get queued (avoid redundant work).
    #    We keep the gating conservative: pre_release runs only if rule tree
    #    has at least one active node AND there exists at least one test case.
    from app.models.entities import TestCase

    has_test_cases = (
        db.query(TestCase).filter(TestCase.requirement_id == requirement_id).count() > 0
    )
    if has_nodes and has_test_cases:
        stages_to_run.append(AnalysisStage.pre_release)

    # Minimum: always run review
    if not stages_to_run:
        stages_to_run = [AnalysisStage.review]

    # Create/reset tasks for all stages upfront so frontend can track them
    for stage in stages_to_run:
        start_risk_analysis_task(db, requirement_id, stage, auto_launch=False)

    _launch_unified_analysis_worker(requirement_id, stages_to_run)
    return stages_to_run


def _launch_unified_analysis_worker(
    requirement_id: int, stages: List[AnalysisStage],
) -> None:
    worker = threading.Thread(
        target=_run_unified_analysis,
        kwargs={"requirement_id": requirement_id, "stages": stages},
        daemon=True,
    )
    worker.start()


def _run_unified_analysis(
    requirement_id: int,
    stages: List[AnalysisStage],
) -> None:
    """Execute stages sequentially in a background thread."""
    for stage in stages:
        task_id = None
        db = SessionLocal()
        try:
            task = get_risk_analysis_task(db, requirement_id, stage)
            if not task:
                logger.warning(
                    "Unified analysis: task for stage %s not found, skipping", stage.value,
                )
                continue

            task_id = task.id
            # Update progress message to show unified context
            task.progress_message = _UNIFIED_PROGRESS_MESSAGES.get(
                stage, _STAGE_RUNNING_MESSAGES[stage],
            )
            db.commit()
        except Exception:
            logger.exception("Unified analysis: failed to update progress for stage %s", stage.value)
            if task_id is None:
                continue
        finally:
            db.close()

        # run_risk_analysis_task creates its own DB session
        try:
            run_risk_analysis_task(task_id=task_id, db_session_factory=SessionLocal)
        except Exception:
            logger.exception(
                "Unified analysis: run_risk_analysis_task crashed for stage %s (task_id=%s)",
                stage.value, task_id,
            )
            # Ensure the task is marked failed even if run_risk_analysis_task raised unexpectedly
            db = SessionLocal()
            try:
                stuck_task = db.query(RiskAnalysisTask).filter(RiskAnalysisTask.id == task_id).first()
                if stuck_task and stuck_task.status in _IN_PROGRESS_STATUSES:
                    stuck_task.status = RiskAnalysisTaskStatus.failed
                    stuck_task.progress_message = "分析执行异常中断"
                    stuck_task.progress_percent = 100
                    stuck_task.last_error = "后台任务异常退出"
                    stuck_task.current_task_finished_at = datetime.utcnow()
                    db.commit()
            except Exception:
                logger.exception("Unified analysis: failed to mark task %s as failed", task_id)
            finally:
                db.close()
            break

        # Check if stage succeeded before continuing
        db = SessionLocal()
        try:
            task = db.query(RiskAnalysisTask).filter(RiskAnalysisTask.id == task_id).first()
            if not task or task.status != RiskAnalysisTaskStatus.completed:
                logger.warning(
                    "Unified analysis: stage %s did not complete successfully (status=%s), "
                    "stopping chain",
                    stage.value,
                    task.status.value if task else "missing",
                )
                break
        finally:
            db.close()
