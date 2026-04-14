import logging
import os
import sys
import typing
from datetime import datetime

from sqlalchemy import text


def _patch_forwardref_evaluate_for_python_312() -> None:
    """Compat shim for pydantic v1 calling ForwardRef._evaluate with old args."""
    if sys.version_info < (3, 12):
        return

    forward_ref = typing.ForwardRef
    original = forward_ref._evaluate
    if getattr(original, "__codex_forwardref_compat__", False):
        return

    def _compat(self, globalns, localns, *args, **kwargs):
        type_params = kwargs.pop("type_params", None)
        recursive_guard = kwargs.pop("recursive_guard", None)

        if args:
            if len(args) == 1:
                if recursive_guard is None and isinstance(args[0], set):
                    recursive_guard = args[0]
                else:
                    type_params = args[0]
            else:
                type_params = args[0]
                if recursive_guard is None:
                    recursive_guard = args[1]

        if recursive_guard is None:
            recursive_guard = set()

        return original(
            self,
            globalns,
            localns,
            type_params=type_params,
            recursive_guard=recursive_guard,
        )

    _compat.__codex_forwardref_compat__ = True  # type: ignore[attr-defined]
    forward_ref._evaluate = _compat


_patch_forwardref_evaluate_for_python_312()

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.architecture import BACKEND_DIR, router as architecture_router
from app.api.ai_parse import router as ai_router
from app.api.clarification_review import router as clarification_review_router
from app.api.coverage import router as coverage_router
from app.api.effective_requirements import router as effective_requirements_router
from app.api.evidence_blocks import router as evidence_blocks_router
from app.api.normalized_requirement_docs import router as normalized_requirement_doc_router
from app.api.normalized_requirement_doc_tasks import router as normalized_requirement_doc_task_router
from app.api.product_docs import router as product_doc_router
from app.api.projects import router as project_router
from app.api.recommendation import router as recommendation_router
from app.api.risk_analysis_tasks import router as risk_analysis_task_router
from app.api.requirement_inputs import router as requirement_inputs_router
from app.api.risks import router as risk_router
from app.api.test_plan import router as test_plan_router
from app.api.rule_tree_session import router as rule_tree_session_router
from app.api.rules import router as rule_router
from app.api.testcase_import import router as testcase_import_router
from app.api.testcases import router as testcase_router
from app.api.tree_diff import router as tree_diff_router
from app.core.database import SessionLocal, engine
from app.core.schema_migrations import (
    ensure_requirement_source_type_values,
    ensure_product_knowledge_columns,
    ensure_hierarchical_knowledge_columns,
    ensure_risk_analysis_task_columns,
    ensure_requirements_versioning_columns,
    ensure_risk_convergence_columns,
    ensure_rule_tree_session_async_columns,
    ensure_test_cases_precondition_column,
)
from app.models.entities import (
    Base,
    NormalizedRequirementDocTask,
    RiskAnalysisTask,
    RiskAnalysisTaskStatus,
    RuleTreeSession,
    RuleTreeSessionStatus,
)

Base.metadata.create_all(bind=engine)
ensure_requirements_versioning_columns(engine)
ensure_requirement_source_type_values(engine)
ensure_test_cases_precondition_column(engine)
ensure_rule_tree_session_async_columns(engine)
ensure_risk_analysis_task_columns(engine)
ensure_product_knowledge_columns(engine)
ensure_risk_convergence_columns(engine)
ensure_hierarchical_knowledge_columns(engine)

app = FastAPI(title="Test Knowledge Base MVP", version="0.1.0")
app.state.ready = False

# CORS: only mount middleware when CORS_ORIGINS is configured (non-empty).
# In production with same-domain Nginx reverse proxy, leave CORS_ORIGINS empty
# so no CORSMiddleware is added at all.
from app.core.config import CORS_ORIGINS

if CORS_ORIGINS:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def recover_interrupted_rule_tree_sessions() -> int:
    db = SessionLocal()
    try:
        sessions = (
            db.query(RuleTreeSession)
            .filter(
                RuleTreeSession.status.in_(
                    [
                        RuleTreeSessionStatus.generating,
                        RuleTreeSessionStatus.reviewing,
                        RuleTreeSessionStatus.saving,
                    ]
                )
            )
            .all()
        )
        interrupted_at = datetime.utcnow()
        for session in sessions:
            session.status = RuleTreeSessionStatus.interrupted
            session.progress_stage = RuleTreeSessionStatus.interrupted.value
            session.progress_message = "服务重启导致任务中断，请重新发起生成"
            session.last_error = "服务重启导致任务中断，请重新发起生成"
            session.current_task_finished_at = interrupted_at
        db.commit()
        return len(sessions)
    finally:
        db.close()


def recover_interrupted_risk_analysis_tasks() -> int:
    db = SessionLocal()
    try:
        tasks = (
            db.query(RiskAnalysisTask)
            .filter(
                RiskAnalysisTask.status.in_(
                    [
                        RiskAnalysisTaskStatus.queued,
                        RiskAnalysisTaskStatus.running,
                    ]
                )
            )
            .all()
        )
        interrupted_at = datetime.utcnow()
        for task in tasks:
            task.status = RiskAnalysisTaskStatus.interrupted
            task.progress_message = "服务重启导致任务中断，请重新发起分析"
            task.last_error = "服务重启导致任务中断，请重新发起分析"
            task.current_task_finished_at = interrupted_at
        db.commit()
        return len(tasks)
    finally:
        db.close()


def recover_interrupted_normalized_requirement_doc_tasks() -> int:
    db = SessionLocal()
    try:
        tasks = (
            db.query(NormalizedRequirementDocTask)
            .filter(
                NormalizedRequirementDocTask.status.in_(
                    [
                        RiskAnalysisTaskStatus.queued,
                        RiskAnalysisTaskStatus.running,
                    ]
                )
            )
            .all()
        )
        interrupted_at = datetime.utcnow()
        for task in tasks:
            task.status = RiskAnalysisTaskStatus.interrupted
            task.progress_message = "服务重启导致任务中断，请重新发起生成"
            task.last_error = "服务重启导致任务中断，请重新发起生成"
            task.current_task_finished_at = interrupted_at
        db.commit()
        return len(tasks)
    finally:
        db.close()


@app.on_event("startup")
def _startup() -> None:
    """Single startup handler: recover interrupted tasks, sync knowledge base, then mark ready."""
    # 1. Recover interrupted tasks
    recover_interrupted_rule_tree_sessions()
    recover_interrupted_risk_analysis_tasks()
    recover_interrupted_normalized_requirement_doc_tasks()

    # 2. Sync knowledge base
    from app.services.knowledge_base_importer import import_all_domains

    kb_root = os.path.join(BACKEND_DIR, "..", "knowledge_base", "products")
    if os.path.isdir(kb_root):
        db = SessionLocal()
        try:
            docs = import_all_domains(db, kb_root)
            if docs:
                logging.getLogger(__name__).info(
                    "Knowledge base synced: %d domains (%s)",
                    len(docs),
                    ", ".join(d.product_code for d in docs),
                )
        finally:
            db.close()

    # 3. Mark service as ready
    app.state.ready = True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    """Readiness probe: checks startup completion AND database connectivity."""
    if not app.state.ready:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "startup not completed"},
        )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "database check failed"},
        )
    return {"status": "ready"}


os.makedirs(os.path.join(BACKEND_DIR, "uploads"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=os.path.join(BACKEND_DIR, "uploads")), name="uploads")

app.include_router(project_router)
app.include_router(rule_router)
app.include_router(rule_tree_session_router)
app.include_router(tree_diff_router)
app.include_router(testcase_router)
app.include_router(testcase_import_router)
app.include_router(coverage_router)
app.include_router(recommendation_router)
app.include_router(ai_router)
app.include_router(clarification_review_router)
app.include_router(architecture_router)
app.include_router(risk_router)
app.include_router(test_plan_router)
app.include_router(product_doc_router)
app.include_router(risk_analysis_task_router)
app.include_router(requirement_inputs_router)
app.include_router(evidence_blocks_router)
app.include_router(effective_requirements_router)
app.include_router(normalized_requirement_doc_router)
app.include_router(normalized_requirement_doc_task_router)
