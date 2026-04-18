import json
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator


class ClarificationReviewQuestionItem(BaseModel):
    question: str
    why_ask: str
    risk_if_unasked: str
    required_output: str = ""
    answer_format: str = ""
    resolution_status: Optional[str] = None
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None


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
    gap_type: str = ""
    priority: str = ""
    blocking_reason: str = ""
    resolution_status: Optional[str] = None
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None


class ClarificationReviewAssumptionItem(BaseModel):
    assumption: str
    basis: str
    risk: str
    resolution_status: Optional[str] = None
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None


class ClarificationReviewInferredItem(BaseModel):
    statement: str
    evidence: str
    source_type: str


class ClarificationReviewRoleDescriptorItem(BaseModel):
    key: str
    source: str


class LLMErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool
    detail_url: Optional[str] = None


class ClarificationReviewResult(BaseModel):
    result_version: Optional[int] = None
    inferred_items: List[ClarificationReviewInferredItem] = Field(default_factory=list)
    assumption_items: List[ClarificationReviewAssumptionItem] = Field(default_factory=list)
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
    llm_error: Optional[LLMErrorDetail] = None


class ClarificationReviewAnalyzeRequest(BaseModel):
    requirement_text: str = ""
    current_surface_flow: str = ""
    involved_modules: str = ""
    known_background: str = ""
    unknowns: str = ""
    rule_text: str
    source_draft_id: Optional[int] = None
    applied_fields: List[str] = Field(default_factory=list)


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
    task_status: str = "completed"
    progress_percent: Optional[int] = None
    source_meta: Optional["ClarificationReviewSourceMeta"] = None
    generated_requirement_id: Optional[int] = None

    @validator("source_meta", pre=True)
    def _parse_source_meta(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v


class ClarificationReviewRecordRead(BaseModel):
    id: int
    input_payload: ClarificationReviewInputPayload
    rule_text: str
    result: ClarificationReviewResult
    llm_status: str
    llm_provider: Optional[str] = None
    llm_message: Optional[str] = None
    task_status: str = "completed"
    progress_message: Optional[str] = None
    progress_percent: Optional[int] = None
    source_meta: Optional["ClarificationReviewSourceMeta"] = None
    generated_requirement_id: Optional[int] = None
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

    @validator("source_meta", pre=True)
    def _parse_source_meta(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    class Config:
        orm_mode = True


class ClarificationReviewSourceMeta(BaseModel):
    source_kind: str
    draft_id: int
    file_name: Optional[str] = None
    draft_created_at: Optional[datetime] = None
    draft_expired: bool
    applied_fields: List[str] = Field(default_factory=list)


ClarificationReviewRecordSummaryRead.update_forward_refs()
ClarificationReviewRecordRead.update_forward_refs()


class ClarificationReviewItemResolutionUpdate(BaseModel):
    item_type: str  # "gap" | "assumption" | "question"
    role: Optional[str] = None  # required when item_type="question"
    index: int
    resolution_status: str  # "pending" | "confirmed" | "assume_and_proceed" | "dismissed"
    resolution_note: str = ""
    resolved_by: str = ""


class ClarificationReviewItemResolutionBatchRequest(BaseModel):
    updates: List[ClarificationReviewItemResolutionUpdate]


class CreateRequirementFromReviewRequest(BaseModel):
    project_id: int
    title: str = ""
