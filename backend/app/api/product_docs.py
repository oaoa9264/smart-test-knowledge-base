import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import ProductDoc, ProductDocChunk, ProductDocUpdate
from app.schemas.product_doc import (
    ProductDocChunkRead,
    ProductDocChunkUpdateRequest,
    ProductDocDetailRead,
    ProductDocImportRequest,
    ProductDocRead,
    ProductDocUpdateRead,
    SuggestUpdateRequest,
)
from app.services.product_doc_service import (
    apply_doc_update,
    import_product_doc_from_text,
    reject_doc_update,
    suggest_doc_update,
    _extract_keywords_from_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/product-docs", tags=["product-docs"])


@router.post("/import", response_model=ProductDocRead, status_code=status.HTTP_201_CREATED)
def import_doc(payload: ProductDocImportRequest, db: Session = Depends(get_db)):
    try:
        doc = import_product_doc_from_text(
            db=db,
            content=payload.content,
            product_code=payload.product_code,
            name=payload.name,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return doc


@router.get("", response_model=List[ProductDocRead])
def list_docs(db: Session = Depends(get_db)):
    return db.query(ProductDoc).order_by(ProductDoc.id.desc()).all()


@router.get("/{product_code}", response_model=ProductDocDetailRead)
def get_doc(product_code: str, db: Session = Depends(get_db)):
    doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if not doc:
        raise HTTPException(status_code=404, detail="product doc not found")
    chunks = (
        db.query(ProductDocChunk)
        .filter(ProductDocChunk.product_doc_id == doc.id)
        .order_by(ProductDocChunk.sort_order)
        .all()
    )
    return ProductDocDetailRead(
        id=doc.id,
        product_code=doc.product_code,
        name=doc.name,
        description=doc.description,
        file_path=doc.file_path,
        version=doc.version,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        chunks=[ProductDocChunkRead.from_orm(c) for c in chunks],
    )


@router.put("/{product_code}/chunks/{chunk_id}", response_model=ProductDocChunkRead)
def update_chunk(
    product_code: str,
    chunk_id: int,
    payload: ProductDocChunkUpdateRequest,
    db: Session = Depends(get_db),
):
    doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if not doc:
        raise HTTPException(status_code=404, detail="product doc not found")
    chunk = db.query(ProductDocChunk).filter(
        ProductDocChunk.id == chunk_id,
        ProductDocChunk.product_doc_id == doc.id,
    ).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="chunk not found")
    chunk.content = payload.content
    chunk.keywords = ",".join(_extract_keywords_from_text(chunk.title + " " + payload.content))
    db.commit()
    db.refresh(chunk)
    return chunk


@router.delete("/{product_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc(product_code: str, db: Session = Depends(get_db)):
    doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if not doc:
        raise HTTPException(status_code=404, detail="product doc not found")
    db.delete(doc)
    db.commit()


@router.post("/suggest-update", response_model=ProductDocUpdateRead, status_code=status.HTTP_201_CREATED)
def create_suggest_update(payload: SuggestUpdateRequest, db: Session = Depends(get_db)):
    try:
        update = suggest_doc_update(
            db=db,
            product_doc_id=payload.product_doc_id,
            risk_item_id=payload.risk_item_id,
            clarification_text=payload.clarification_text,
            supplement_text=payload.supplement_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return update


@router.get("/updates/list", response_model=List[ProductDocUpdateRead])
def list_updates(product_doc_id: int = 0, db: Session = Depends(get_db)):
    query = db.query(ProductDocUpdate)
    if product_doc_id:
        query = query.filter(ProductDocUpdate.product_doc_id == product_doc_id)
    return query.order_by(ProductDocUpdate.id.desc()).all()


@router.put("/updates/{update_id}/apply", response_model=ProductDocUpdateRead)
def apply_update(update_id: int, db: Session = Depends(get_db)):
    try:
        update = apply_doc_update(db=db, update_id=update_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return update


@router.put("/updates/{update_id}/reject", response_model=ProductDocUpdateRead)
def reject_update(update_id: int, db: Session = Depends(get_db)):
    try:
        update = reject_doc_update(db=db, update_id=update_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return update
