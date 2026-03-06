import os
import sys
import typing


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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.architecture import BACKEND_DIR, router as architecture_router
from app.api.ai_parse import router as ai_router
from app.api.coverage import router as coverage_router
from app.api.projects import router as project_router
from app.api.recommendation import router as recommendation_router
from app.api.risks import router as risk_router
from app.api.rule_tree_session import router as rule_tree_session_router
from app.api.rules import router as rule_router
from app.api.testcase_import import router as testcase_import_router
from app.api.testcases import router as testcase_router
from app.api.tree_diff import router as tree_diff_router
from app.core.database import engine
from app.core.schema_migrations import ensure_requirements_versioning_columns
from app.models.entities import Base

Base.metadata.create_all(bind=engine)
ensure_requirements_versioning_columns(engine)

app = FastAPI(title="Test Knowledge Base MVP", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


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
app.include_router(architecture_router)
app.include_router(risk_router)
