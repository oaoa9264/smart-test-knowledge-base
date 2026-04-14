import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.clarification_review import (
    ClarificationReviewAnalyzeRequest,
    ClarificationReviewRecordRead,
    ClarificationReviewRecordSummaryRead,
)
from app.services import clarification_review_service


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
        source_meta=record.source_meta_json,
        created_at=record.created_at,
    )


@router.get("/records", response_model=list[ClarificationReviewRecordSummaryRead])
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
                source_meta=record.source_meta_json,
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
        source_meta=record.source_meta_json,
        created_at=record.created_at,
    )
