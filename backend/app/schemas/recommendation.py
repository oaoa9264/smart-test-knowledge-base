from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class RecoCaseFilter(BaseModel):
    status_in: Optional[List[str]] = None
    case_ids: Optional[List[int]] = None


class RecoRequest(BaseModel):
    requirement_id: int
    mode: str = "FULL"
    k: int = 10
    changed_node_ids: Optional[List[str]] = None
    case_filter: Optional[RecoCaseFilter] = None
    cost_mode: str = "UNIT"


class RecoContributor(BaseModel):
    node_id: str
    risk: float


class RecoCaseRead(BaseModel):
    rank: int
    case_id: int
    gain_risk: float
    gain_nodes: List[str]
    top_contributors: List[RecoContributor]
    why_selected: str


class RecoGapRead(BaseModel):
    node_id: str
    risk: float


class RecoSummaryRead(BaseModel):
    k: int
    picked: int
    covered_risk: float
    total_target_risk: float
    coverage_ratio: float


class RecoResponse(BaseModel):
    run_id: int
    summary: RecoSummaryRead
    cases: List[RecoCaseRead]
    remaining_high_risk_gaps: List[RecoGapRead]


class RecoRunRead(BaseModel):
    id: int
    requirement_id: int
    mode: str
    k: int
    input_changed_node_ids: List[str]
    total_target_risk: float
    covered_risk: float
    coverage_ratio: float
    created_at: datetime

    class Config:
        orm_mode = True


class RecoResultRead(BaseModel):
    id: int
    run_id: int
    rank: int
    case_id: int
    gain_risk: float
    gain_node_ids: List[str]
    top_contributors: List[RecoContributor]
    why_selected: str


class RecoRunDetailRead(BaseModel):
    run: RecoRunRead
    results: List[RecoResultRead]
