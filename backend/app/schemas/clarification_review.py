import json
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator


class ClarificationReviewQuestionItem(BaseModel):
    question: str
    why_ask: str
    risk_if_unasked: str


class ClarificationReviewRuleItem(BaseModel):
    rule: str
    reason: str


class ClarificationReviewMissingRuleItem(BaseModel):
    rule: str
    why_missing: str
    impact: str


class ClarificationReviewGapItem(BaseModel):
    gap: str
    reason: str
    impact: str


class ClarificationReviewAssumptionItem(BaseModel):
    assumption: str
    basis: str
    risk: str


class ClarificationReviewRoleDescriptorItem(BaseModel):
    key: str
    source: str


class ClarificationReviewResult(BaseModel):
    likely_historical_rules: List[ClarificationReviewRuleItem] = Field(default_factory=list)
    missing_critical_rules: List[ClarificationReviewMissingRuleItem] = Field(default_factory=list)
    priority_questions_by_role: Dict[str, List[ClarificationReviewQuestionItem]] = Field(default_factory=dict)
    configured_roles: List[str] = Field(default_factory=list)
    role_descriptors: List[ClarificationReviewRoleDescriptorItem] = Field(default_factory=list)
    known_requirement_gaps: List[ClarificationReviewGapItem] = Field(default_factory=list)
    risk_assumptions: List[ClarificationReviewAssumptionItem] = Field(default_factory=list)
    summary_markdown: str = ""
    llm_status: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_message: Optional[str] = None


class ClarificationReviewAnalyzeRequest(BaseModel):
    requirement_text: str = ""
    current_surface_flow: str = ""
    involved_modules: str = ""
    known_background: str = ""
    unknowns: str = ""
    rule_text: str


class ClarificationReviewInputPayload(BaseModel):
    requirement_text: str = ""
    current_surface_flow: str = ""
    involved_modules: str = ""
    known_background: str = ""
    unknowns: str = ""


class ClarificationReviewRecordSummaryRead(BaseModel):
    id: int
    llm_status: str
    llm_provider: Optional[str] = None
    created_at: datetime
    requirement_text_preview: str


class ClarificationReviewRecordRead(BaseModel):
    id: int
    input_payload: ClarificationReviewInputPayload
    rule_text: str
    result: ClarificationReviewResult
    llm_status: str
    llm_provider: Optional[str] = None
    llm_message: Optional[str] = None
    created_at: datetime

    @validator("input_payload", pre=True)
    def _parse_input_payload(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @validator("result", pre=True)
    def _parse_result(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    class Config:
        orm_mode = True
