from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import InputType, Requirement, RequirementInput
from app.schemas.risk_convergence import RequirementInputCreate, RequirementInputRead

router = APIRouter(tags=["requirement-inputs"])

_VALID_INPUT_TYPES = {t.value for t in InputType}


@router.post(
    "/api/requirements/{requirement_id}/inputs",
    response_model=RequirementInputRead,
    status_code=status.HTTP_201_CREATED,
)
def add_requirement_input(
    requirement_id: int,
    payload: RequirementInputCreate,
    db: Session = Depends(get_db),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    if payload.input_type not in _VALID_INPUT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="invalid input_type, must be one of: {0}".format(", ".join(sorted(_VALID_INPUT_TYPES))),
        )

    ri = RequirementInput(
        requirement_id=requirement_id,
        input_type=InputType(payload.input_type),
        content=payload.content,
        source_label=payload.source_label,
        created_by=payload.created_by,
    )
    db.add(ri)
    db.commit()
    db.refresh(ri)
    return RequirementInputRead.from_orm(ri)


@router.get(
    "/api/requirements/{requirement_id}/inputs",
    response_model=List[RequirementInputRead],
)
def list_requirement_inputs(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    inputs = (
        db.query(RequirementInput)
        .filter(RequirementInput.requirement_id == requirement_id)
        .order_by(RequirementInput.created_at.desc())
        .all()
    )
    return [RequirementInputRead.from_orm(ri) for ri in inputs]
