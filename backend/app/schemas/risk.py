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
    analysis_stage: Optional[str] = None
    validity: Optional[str] = "active"
    origin_snapshot_id: Optional[int] = None
    last_seen_snapshot_id: Optional[int] = None
    last_analysis_at: Optional[datetime] = None
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
    active: int = 0
    superseded: int = 0
    reopened: int = 0
    resolved: int = 0


class ClarificationQuestion(BaseModel):
    module: str
    question: str
    context: str


class ClarificationQuestionsRequest(BaseModel):
    requirement_id: int


class ClarificationQuestionsResponse(BaseModel):
    questions: List[ClarificationQuestion]
    total: int
