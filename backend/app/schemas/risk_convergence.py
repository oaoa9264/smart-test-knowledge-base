from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class RequirementInputCreate(BaseModel):
    input_type: str
    content: str
    source_label: Optional[str] = None
    created_by: Optional[str] = None


class RequirementInputRead(BaseModel):
    id: int
    requirement_id: int
    input_type: str
    content: str
    source_label: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class EffectiveFieldRead(BaseModel):
    id: int
    snapshot_id: int
    field_key: str
    value: Optional[str] = None
    derivation: Optional[str] = None
    confidence: Optional[float] = None
    source_refs: Optional[str] = None
    notes: Optional[str] = None
    sort_order: int = 0

    class Config:
        orm_mode = True


class EffectiveSnapshotRead(BaseModel):
    id: int
    requirement_id: int
    stage: str
    status: str
    based_on_input_ids: Optional[str] = None
    basis_hash: Optional[str] = None
    is_stale: Optional[bool] = None
    summary: Optional[str] = None
    base_snapshot_id: Optional[int] = None
    created_at: Optional[datetime] = None
    fields: List[EffectiveFieldRead] = []

    class Config:
        orm_mode = True


class EvidenceBlockRead(BaseModel):
    id: int
    product_doc_id: int
    chunk_id: Optional[int] = None
    evidence_type: str
    module_name: Optional[str] = None
    statement: str
    status: str
    source_span: Optional[str] = None
    created_from: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class EvidenceBlockCreate(BaseModel):
    evidence_type: str = "field_rule"
    module_name: Optional[str] = None
    statement: str
    source_span: Optional[str] = None


class EvidenceBlockUpdate(BaseModel):
    statement: Optional[str] = None
    evidence_type: Optional[str] = None
    module_name: Optional[str] = None


class EvidenceFromClarificationRequest(BaseModel):
    risk_item_id: str
    statement: str
    evidence_type: str = "field_rule"
    module_name: Optional[str] = None


class EvidenceBootstrapResponse(BaseModel):
    created: int
    evidences: List[EvidenceBlockRead] = []


class RiskItemCompact(BaseModel):
    id: str
    category: str
    risk_level: str
    description: str
    suggestion: str
    validity: Optional[str] = "active"
    analysis_stage: Optional[str] = None

    class Config:
        orm_mode = True


class ReviewSnapshotResponse(BaseModel):
    snapshot: EffectiveSnapshotRead
    risks: List[RiskItemCompact] = []
    clarification_hints: List[str] = []


class MatchedEvidence(BaseModel):
    evidence_statement: str = ""
    related_field_key: str = ""
    match_type: str = "consistent"


class ConflictItem(BaseModel):
    conflict_type: str = ""
    description: str = ""
    source_a: str = ""
    source_b: str = ""


class PredevAnalysisRequest(BaseModel):
    requirement_id: int


class PredevAnalysisResponse(BaseModel):
    snapshot: EffectiveSnapshotRead
    risks: List[RiskItemCompact] = []
    conflicts: List[ConflictItem] = []
    matched_evidence: List[MatchedEvidence] = []


class PrereleaseAuditRequest(BaseModel):
    requirement_id: int


class BlockingRisk(BaseModel):
    risk_id: str = ""
    reason: str = ""
    severity: str = "high"


class ReopenedRisk(BaseModel):
    risk_id: str = ""
    reason: str = ""


class ResolvedRisk(BaseModel):
    risk_id: str = ""
    reason: str = ""


class PrereleaseAuditResponse(BaseModel):
    closure_summary: str = ""
    blocking_risks: List[BlockingRisk] = []
    reopened_risks: List[ReopenedRisk] = []
    resolved_risks: List[ResolvedRisk] = []
    audit_notes: List[str] = []
