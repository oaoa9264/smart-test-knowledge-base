import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.clarification_review_pdf import PdfDraftInferResponse, PdfDraftRead
from app.services import pdf_draft_service
from app.services.pdf_draft_service import PdfDraftInferConflictError


router = APIRouter(prefix="/api/ai/clarification-review/pdf-drafts", tags=["clarification-review"])


@router.post("", response_model=PdfDraftRead, status_code=status.HTTP_201_CREATED)
def create_pdf_draft_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        draft = pdf_draft_service.create_pdf_draft(db=db, file=file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_dependency_http_error(exc) from exc
    return _serialize_pdf_draft(draft)


@router.get("/{draft_id}", response_model=PdfDraftRead)
def get_pdf_draft_endpoint(draft_id: int, db: Session = Depends(get_db)):
    try:
        draft = pdf_draft_service.get_pdf_draft(db=db, draft_id=draft_id)
    except pdf_draft_service.PdfDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail="pdf draft not found") from exc
    return _serialize_pdf_draft(draft)


@router.post("/{draft_id}/infer", response_model=PdfDraftInferResponse)
def infer_pdf_draft_endpoint(draft_id: int, db: Session = Depends(get_db)):
    try:
        draft = pdf_draft_service.infer_pdf_draft(db=db, draft_id=draft_id)
    except pdf_draft_service.PdfDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail="pdf draft not found") from exc
    except PdfDraftInferConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_dependency_http_error(exc) from exc
    return _serialize_pdf_draft(draft)


def _serialize_pdf_draft(draft) -> PdfDraftRead:
    return PdfDraftRead(
        id=draft.id,
        file_name=draft.file_name,
        file_size_bytes=draft.file_size_bytes,
        page_count=draft.page_count,
        status=draft.status,
        llm_status=draft.llm_status,
        llm_provider=draft.llm_provider,
        llm_message=draft.llm_message,
        infer_llm_status=draft.infer_llm_status,
        infer_llm_provider=draft.infer_llm_provider,
        infer_llm_message=draft.infer_llm_message,
        infer_task_status=draft.infer_task_status,
        progress_message=draft.progress_message,
        progress_percent=draft.progress_percent,
        strict_result=_decode_result(draft.strict_result_json),
        inference_result=_decode_result(draft.inference_result_json),
        expires_at=draft.expires_at,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


def _decode_result(value):
    if not value:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _runtime_dependency_http_error(exc: RuntimeError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))
