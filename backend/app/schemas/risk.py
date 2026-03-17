from datetime import datetime
from typing import List, Optional

from typing_extensions import Literal

from pydantic import BaseModel


class RiskItemRead(BaseModel):
    id: str
    requirement_id: int
    related_node_id: Optional[str] = None
    category: str
    risk_level: str
    description: str
    suggestion: str
    decision: str
    decision_reason: Optional[str] = None
    decided_at: Optional[datetime] = None
    risk_source: str = "rule_tree"
    clarification_text: Optional[str] = None
    doc_update_needed: bool = False
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class RiskDecisionRequest(BaseModel):
    decision: Literal["accepted", "ignored"]
    reason: str
    auto_create_node: bool = False


class RiskClarifyRequest(BaseModel):
    clarification_text: str
    doc_update_needed: bool = False


class RiskAnalyzeRequest(BaseModel):
    requirement_id: int


class RiskAnalyzeResponse(BaseModel):
    risks: List[RiskItemRead]
    total: int


class RiskListResponse(BaseModel):
    risks: List[RiskItemRead]
    total: int
    pending: int
    accepted: int
    ignored: int
