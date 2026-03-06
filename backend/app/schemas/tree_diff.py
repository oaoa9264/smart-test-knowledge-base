from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class DiffNodeItem(BaseModel):
    node_id: str
    node_type: str
    content: str
    risk_level: str
    parent_id: Optional[str] = None


class DiffNodeChange(BaseModel):
    status: str
    current: Optional[DiffNodeItem] = None
    previous: Optional[DiffNodeItem] = None
    changed_fields: Optional[List[str]] = None


class TreeDiffResult(BaseModel):
    base_version: int
    compare_version: int
    summary: Dict[str, int]
    node_changes: List[DiffNodeChange]


class TreeDiffSummaryResult(BaseModel):
    base_version: int
    compare_version: int
    summary: str


class FlowChange(BaseModel):
    change_type: str
    description: str
    detail: Optional[str] = None
    impact: str


class SemanticDiffResult(BaseModel):
    base_version: int
    compare_version: int
    flow_changes: List[FlowChange]
    summary: str
    risk_notes: Optional[str] = None


class DiffRecordRead(BaseModel):
    id: int
    base_requirement_id: int
    compare_requirement_id: int
    base_version: int
    compare_version: int
    diff_type: str
    created_at: datetime
    result: SemanticDiffResult

    class Config:
        from_attributes = True
