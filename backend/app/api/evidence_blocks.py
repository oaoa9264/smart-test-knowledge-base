from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import EvidenceBlock, ProductDoc
from app.schemas.risk_convergence import (
    EvidenceBlockRead,
    EvidenceBlockUpdate,
    EvidenceBootstrapResponse,
    EvidenceFromClarificationRequest,
)
from app.services.evidence_service import (
    bootstrap_evidence_from_chunks,
    create_evidence_from_clarification,
    reject_evidence,
    update_evidence,
    verify_evidence,
)

router = APIRouter(tags=["evidence-blocks"])


@router.get(
    "/api/product-docs/{product_code}/evidence",
    response_model=List[EvidenceBlockRead],
)
def list_evidence_blocks(
    product_code: str,
    db: Session = Depends(get_db),
):
    doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if not doc:
        raise HTTPException(status_code=404, detail="product doc not found")

    blocks = (
        db.query(EvidenceBlock)
        .filter(EvidenceBlock.product_doc_id == doc.id)
        .order_by(EvidenceBlock.created_at.desc())
        .all()
    )
    return [EvidenceBlockRead.from_orm(b) for b in blocks]


@router.post(
    "/api/product-docs/{product_code}/evidence/bootstrap",
    response_model=EvidenceBootstrapResponse,
)
def bootstrap_evidence(
    product_code: str,
    db: Session = Depends(get_db),
):
    try:
        blocks = bootstrap_evidence_from_chunks(db=db, product_code=product_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return EvidenceBootstrapResponse(
        created=len(blocks),
        evidences=[EvidenceBlockRead.from_orm(b) for b in blocks],
    )


@router.post(
    "/api/evidence/from-clarification",
    response_model=EvidenceBlockRead,
    status_code=201,
)
def create_evidence_from_clarification_endpoint(
    payload: EvidenceFromClarificationRequest,
    db: Session = Depends(get_db),
):
    try:
        block = create_evidence_from_clarification(
            db=db,
            risk_item_id=payload.risk_item_id,
            statement=payload.statement,
            evidence_type=payload.evidence_type,
            module_name=payload.module_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return EvidenceBlockRead.from_orm(block)


@router.put(
    "/api/evidence/{evidence_id}",
    response_model=EvidenceBlockRead,
)
def edit_evidence(
    evidence_id: int,
    payload: EvidenceBlockUpdate,
    db: Session = Depends(get_db),
):
    try:
        block = update_evidence(
            db=db,
            evidence_id=evidence_id,
            statement=payload.statement,
            evidence_type=payload.evidence_type,
            module_name=payload.module_name,
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    return EvidenceBlockRead.from_orm(block)


@router.put(
    "/api/evidence/{evidence_id}/verify",
    response_model=EvidenceBlockRead,
)
def verify_evidence_endpoint(
    evidence_id: int,
    db: Session = Depends(get_db),
):
    try:
        block = verify_evidence(db=db, evidence_id=evidence_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return EvidenceBlockRead.from_orm(block)


@router.put(
    "/api/evidence/{evidence_id}/reject",
    response_model=EvidenceBlockRead,
)
def reject_evidence_endpoint(
    evidence_id: int,
    db: Session = Depends(get_db),
):
    try:
        block = reject_evidence(db=db, evidence_id=evidence_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return EvidenceBlockRead.from_orm(block)
