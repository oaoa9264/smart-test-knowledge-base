import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.clarification_review import (
    ClarificationReviewAnalyzeRequest,
    ClarificationReviewItemResolutionBatchRequest,
    ClarificationReviewRecordRead,
    ClarificationReviewRecordSummaryRead,
    CreateRequirementFromReviewRequest,
)
from app.services import clarification_review_service
from app.services.clarification_review_service import CreateRequirementError, ItemResolutionError


router = APIRouter(prefix="/api/ai/clarification-review", tags=["clarification-review"])


@router.post("/analyze", response_model=ClarificationReviewRecordRead, status_code=status.HTTP_201_CREATED)
def analyze_clarification_review_endpoint(
    payload: ClarificationReviewAnalyzeRequest,
    db: Session = Depends(get_db),
):
    if not str(payload.rule_text or "").strip():
        raise HTTPException(status_code=400, detail="rule_text is required")

    if not any(
        str(value or "").strip()
        for value in (
            payload.requirement_text,
            payload.current_surface_flow,
            payload.involved_modules,
            payload.known_background,
            payload.unknowns,
        )
    ):
        raise HTTPException(status_code=400, detail="at least one known info field is required")

    record = clarification_review_service.analyze_clarification_review(db=db, payload=payload)
    return _build_record_read(record)


@router.get("/records", response_model=List[ClarificationReviewRecordSummaryRead])
def list_clarification_review_records_endpoint(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    records = clarification_review_service.list_clarification_review_records(db=db, limit=limit)
    result = []
    for record in records:
        payload = json.loads(record.input_payload_json)
        result.append(
            ClarificationReviewRecordSummaryRead(
                id=record.id,
                llm_status=record.llm_status,
                llm_provider=record.llm_provider,
                created_at=record.created_at,
                requirement_text_preview=str(payload.get("requirement_text", "") or "")[:80],
                task_status=record.task_status,
                progress_percent=record.progress_percent,
                source_meta=record.source_meta_json,
                generated_requirement_id=record.generated_requirement_id,
            )
        )
    return result


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clarification_review_record_endpoint(record_id: int, db: Session = Depends(get_db)):
    deleted = clarification_review_service.delete_clarification_review_record(db=db, record_id=record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="record not found")
    return None


@router.get("/records/{record_id}", response_model=ClarificationReviewRecordRead)
def get_clarification_review_record_endpoint(record_id: int, db: Session = Depends(get_db)):
    record = clarification_review_service.get_clarification_review_record(db=db, record_id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record not found")
    return _build_record_read(record)


@router.patch("/records/{record_id}/items", response_model=ClarificationReviewRecordRead)
def update_clarification_review_item_resolutions_endpoint(
    record_id: int,
    payload: ClarificationReviewItemResolutionBatchRequest,
    db: Session = Depends(get_db),
):
    try:
        record = clarification_review_service.update_item_resolutions(
            db=db,
            record_id=record_id,
            updates=[update.dict() for update in payload.updates],
        )
    except ItemResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _build_record_read(record)


@router.post("/records/{record_id}/create-requirement", status_code=status.HTTP_201_CREATED)
def create_requirement_from_review_endpoint(
    record_id: int,
    payload: CreateRequirementFromReviewRequest,
    db: Session = Depends(get_db),
):
    try:
        requirement = clarification_review_service.create_requirement_from_review(
            db=db,
            record_id=record_id,
            project_id=payload.project_id,
            title=payload.title,
        )
    except CreateRequirementError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    record = clarification_review_service.get_clarification_review_record(db=db, record_id=record_id)
    return {
        "requirement": {
            "id": requirement.id,
            "project_id": requirement.project_id,
            "title": requirement.title,
        },
        "record": _build_record_read(record),
    }


def _build_record_read(record) -> ClarificationReviewRecordRead:
    return ClarificationReviewRecordRead(
        id=record.id,
        input_payload=record.input_payload_json,
        rule_text=record.rule_text,
        result=clarification_review_service.normalize_clarification_review_result(
            json.loads(record.result_json),
            record.rule_text,
            allow_pdf_source=record.source_draft_id is not None,
        ),
        llm_status=record.llm_status,
        llm_provider=record.llm_provider,
        llm_message=record.llm_message,
        task_status=record.task_status,
        progress_message=record.progress_message,
        progress_percent=record.progress_percent,
        source_meta=record.source_meta_json,
        generated_requirement_id=record.generated_requirement_id,
        created_at=record.created_at,
    )
