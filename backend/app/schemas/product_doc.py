from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ProductDocChunkRead(BaseModel):
    id: int
    product_doc_id: int
    stage_key: str
    title: str
    content: str
    sort_order: int
    keywords: Optional[str] = None

    class Config:
        orm_mode = True


class ProductDocRead(BaseModel):
    id: int
    product_code: str
    name: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    version: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class ProductDocDetailRead(ProductDocRead):
    chunks: List[ProductDocChunkRead] = []


class ProductDocImportRequest(BaseModel):
    product_code: str
    name: str
    description: str = ""
    content: str


class ProductDocChunkUpdateRequest(BaseModel):
    content: str


class ProductDocUpdateRead(BaseModel):
    id: int
    product_doc_id: int
    chunk_id: Optional[int] = None
    risk_item_id: Optional[str] = None
    original_content: Optional[str] = None
    suggested_content: Optional[str] = None
    status: str
    reviewed_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class SuggestUpdateRequest(BaseModel):
    product_doc_id: int
    risk_item_id: str
    clarification_text: str
