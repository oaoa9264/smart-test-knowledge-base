from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.normalized_requirement_doc import NormalizedRequirementDocPreview
from app.services.normalized_requirement_doc_service import (
    NormalizedRequirementDocGenerationError,
    build_normalized_requirement_doc,
)

router = APIRouter(tags=["normalized-requirement-docs"])


@router.post(
    "/api/requirements/{requirement_id}/normalized-doc/preview",
    response_model=NormalizedRequirementDocPreview,
)
def preview_normalized_requirement_doc(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    try:
        return NormalizedRequirementDocPreview(**build_normalized_requirement_doc(db, requirement_id))
    except NormalizedRequirementDocGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
