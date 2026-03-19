from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import NormalizedRequirementDocTask, Requirement
from app.schemas.normalized_requirement_doc_task import (
    NormalizedRequirementDocTaskRead,
    NormalizedRequirementDocTaskStartResponse,
)
from app.services.normalized_requirement_doc_task_service import (
    NormalizedRequirementDocTaskConflictError,
    get_normalized_requirement_doc_task,
    start_normalized_requirement_doc_task,
)

router = APIRouter(tags=["normalized-requirement-doc-tasks"])


def _get_requirement_or_404(db: Session, requirement_id: int) -> Requirement:
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")
    return requirement


@router.get(
    "/api/requirements/{requirement_id}/normalized-doc-tasks/latest",
    response_model=Optional[NormalizedRequirementDocTaskRead],
)
def get_latest_normalized_requirement_doc_task(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    _get_requirement_or_404(db, requirement_id)
    task: Optional[NormalizedRequirementDocTask] = get_normalized_requirement_doc_task(db, requirement_id)
    if not task:
        return None
    return NormalizedRequirementDocTaskRead.from_orm(task)


@router.post(
    "/api/requirements/{requirement_id}/normalized-doc-tasks",
    response_model=NormalizedRequirementDocTaskStartResponse,
)
def start_requirement_normalized_doc_task(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    _get_requirement_or_404(db, requirement_id)
    try:
        task = start_normalized_requirement_doc_task(db, requirement_id)
    except NormalizedRequirementDocTaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return NormalizedRequirementDocTaskStartResponse(
        accepted=True,
        task=NormalizedRequirementDocTaskRead.from_orm(task),
    )
