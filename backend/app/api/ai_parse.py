from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ai_parser import parse_requirement_text

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AIParsePayload(BaseModel):
    raw_text: str


@router.post("/parse")
def parse_requirement(payload: AIParsePayload):
    return parse_requirement_text(payload.raw_text)
