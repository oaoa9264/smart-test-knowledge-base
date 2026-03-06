import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import Requirement
from app.schemas.tree_diff import SemanticDiffResult, TreeDiffSummaryResult
from app.services.tree_diff import diff_summary_with_llm, diff_trees, diff_trees_with_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("/diff", response_model=SemanticDiffResult)
def get_rule_tree_diff(base_requirement_id: int, compare_requirement_id: int, db: Session = Depends(get_db)):
    base_requirement = db.query(Requirement).filter(Requirement.id == base_requirement_id).first()
    compare_requirement = db.query(Requirement).filter(Requirement.id == compare_requirement_id).first()
    if not base_requirement or not compare_requirement:
        raise HTTPException(status_code=404, detail="requirement not found")
    if base_requirement.project_id != compare_requirement.project_id:
        raise HTTPException(status_code=400, detail="requirements must belong to same project")

    try:
        return diff_trees_with_llm(
            db=db,
            old_requirement_id=base_requirement_id,
            new_requirement_id=compare_requirement_id,
        )
    except Exception:
        logger.warning("LLM semantic diff failed, falling back to algorithmic diff", exc_info=True)
        return diff_trees(
            db=db,
            old_requirement_id=base_requirement_id,
            new_requirement_id=compare_requirement_id,
        )


@router.get("/diff/summary", response_model=TreeDiffSummaryResult, deprecated=True)
def get_rule_tree_diff_summary(base_requirement_id: int, compare_requirement_id: int, db: Session = Depends(get_db)):
    """Deprecated: functionality merged into GET /diff."""
    base_requirement = db.query(Requirement).filter(Requirement.id == base_requirement_id).first()
    compare_requirement = db.query(Requirement).filter(Requirement.id == compare_requirement_id).first()
    if not base_requirement or not compare_requirement:
        raise HTTPException(status_code=404, detail="requirement not found")
    if base_requirement.project_id != compare_requirement.project_id:
        raise HTTPException(status_code=400, detail="requirements must belong to same project")

    try:
        return diff_summary_with_llm(
            db=db,
            old_requirement_id=base_requirement_id,
            new_requirement_id=compare_requirement_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
