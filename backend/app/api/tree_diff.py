import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import DiffRecord, Requirement
from app.schemas.tree_diff import DiffRecordRead, SemanticDiffResult, TreeDiffSummaryResult
from app.services.tree_diff import diff_summary_with_llm, diff_trees, diff_trees_with_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _save_diff_record(
    db: Session,
    project_id: int,
    base_requirement_id: int,
    compare_requirement_id: int,
    result: dict,
    diff_type: str,
) -> DiffRecord:
    base_version = result.get("base_version", 0)
    compare_version = result.get("compare_version", 0)
    record = DiffRecord(
        project_id=project_id,
        base_requirement_id=base_requirement_id,
        compare_requirement_id=compare_requirement_id,
        base_version=base_version,
        compare_version=compare_version,
        result_json=json.dumps(result, ensure_ascii=False),
        diff_type=diff_type,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _record_to_read(record: DiffRecord) -> DiffRecordRead:
    result_data = json.loads(record.result_json)
    return DiffRecordRead(
        id=record.id,
        base_requirement_id=record.base_requirement_id,
        compare_requirement_id=record.compare_requirement_id,
        base_version=record.base_version,
        compare_version=record.compare_version,
        diff_type=record.diff_type,
        created_at=record.created_at,
        result=SemanticDiffResult(**result_data),
    )


@router.get("/diff", response_model=SemanticDiffResult)
def get_rule_tree_diff(base_requirement_id: int, compare_requirement_id: int, db: Session = Depends(get_db)):
    base_requirement = db.query(Requirement).filter(Requirement.id == base_requirement_id).first()
    compare_requirement = db.query(Requirement).filter(Requirement.id == compare_requirement_id).first()
    if not base_requirement or not compare_requirement:
        raise HTTPException(status_code=404, detail="requirement not found")
    if base_requirement.project_id != compare_requirement.project_id:
        raise HTTPException(status_code=400, detail="requirements must belong to same project")

    diff_type = "semantic"
    try:
        result = diff_trees_with_llm(
            db=db,
            old_requirement_id=base_requirement_id,
            new_requirement_id=compare_requirement_id,
        )
    except Exception:
        logger.warning("LLM semantic diff failed, falling back to algorithmic diff", exc_info=True)
        diff_type = "algorithmic"
        result = diff_trees(
            db=db,
            old_requirement_id=base_requirement_id,
            new_requirement_id=compare_requirement_id,
        )

    try:
        result_dict = result if isinstance(result, dict) else result.dict() if hasattr(result, "dict") else result.model_dump()
        _save_diff_record(
            db=db,
            project_id=base_requirement.project_id,
            base_requirement_id=base_requirement_id,
            compare_requirement_id=compare_requirement_id,
            result=result_dict,
            diff_type=diff_type,
        )
    except Exception:
        logger.warning("Failed to save diff record", exc_info=True)

    return result


@router.get("/diff/history", response_model=List[DiffRecordRead])
def list_diff_history(
    project_id: int,
    requirement_group_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(DiffRecord).filter(DiffRecord.project_id == project_id)

    if requirement_group_id is not None:
        req_ids = [
            r.id
            for r in db.query(Requirement.id)
            .filter(Requirement.requirement_group_id == requirement_group_id)
            .all()
        ]
        if req_ids:
            query = query.filter(
                (DiffRecord.base_requirement_id.in_(req_ids))
                | (DiffRecord.compare_requirement_id.in_(req_ids))
            )
        else:
            return []

    records = query.order_by(DiffRecord.created_at.desc()).limit(50).all()
    return [_record_to_read(r) for r in records]


@router.get("/diff/history/{record_id}", response_model=DiffRecordRead)
def get_diff_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(DiffRecord).filter(DiffRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="diff record not found")
    return _record_to_read(record)


@router.delete("/diff/history/{record_id}")
def delete_diff_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(DiffRecord).filter(DiffRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="diff record not found")
    db.delete(record)
    db.commit()
    return {"ok": True}


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
