import json
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, validator


PDF_RESULT_FIELDS = (
    "requirement_text",
    "current_surface_flow",
    "involved_modules",
    "known_background",
    "unknowns",
)


class PdfFieldResult(BaseModel):
    value: str = ""
    evidence: str = ""


class PdfConflict(BaseModel):
    field: str
    description: str
    evidence: str = ""


class PdfDraftResult(BaseModel):
    fields: dict[str, PdfFieldResult] = Field(default_factory=dict)
    conflicts: List[PdfConflict] = Field(default_factory=list)

    @validator("fields", pre=True, always=True)
    def _normalize_fields(cls, value):
        raw = value if isinstance(value, dict) else {}
        normalized = {}
        for field_name in PDF_RESULT_FIELDS:
            item = raw.get(field_name) if isinstance(raw, dict) else None
            if isinstance(item, dict):
                normalized[field_name] = PdfFieldResult(
                    value=str(item.get("value", "") or ""),
                    evidence=str(item.get("evidence", "") or ""),
                )
            else:
                normalized[field_name] = PdfFieldResult()
        return normalized


class PdfDraftRead(BaseModel):
    id: int
    file_name: str
    file_size_bytes: int
    page_count: int
    status: str
    llm_status: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_message: Optional[str] = None
    infer_llm_status: Optional[str] = None
    infer_llm_provider: Optional[str] = None
    infer_llm_message: Optional[str] = None
    infer_task_status: Optional[str] = None
    progress_message: Optional[str] = None
    progress_percent: Optional[int] = None
    strict_result: Optional[PdfDraftResult] = None
    inference_result: Optional[PdfDraftResult] = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    @validator("strict_result", "inference_result", pre=True)
    def _parse_result(cls, value):
        if isinstance(value, str):
            return json.loads(value)
        return value

    class Config:
        orm_mode = True


class PdfDraftInferResponse(PdfDraftRead):
    pass
