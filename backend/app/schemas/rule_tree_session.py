from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RuleTreeSessionCreate(BaseModel):
    requirement_id: int
    title: str


class RuleTreeSessionRead(BaseModel):
    id: int
    requirement_id: int
    title: str
    status: str
    confirmed_tree_snapshot: Optional[str] = None
    requirement_text_snapshot: Optional[str] = None
    progress_stage: Optional[str] = None
    progress_message: Optional[str] = None
    progress_percent: Optional[int] = None
    last_error: Optional[str] = None
    generated_tree_snapshot: Optional[str] = None
    reviewed_tree_snapshot: Optional[str] = None
    current_task_started_at: Optional[datetime] = None
    current_task_finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class RuleTreeMessageRead(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    message_type: str
    tree_snapshot: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True


class RuleTreeSessionDetailRead(BaseModel):
    session: RuleTreeSessionRead
    messages: List[RuleTreeMessageRead]


class RuleTreeGeneratePayload(BaseModel):
    requirement_text: str
    title: Optional[str] = None


class RuleTreeGenerateResponse(BaseModel):
    accepted: bool
    session: RuleTreeSessionRead


class RuleTreeUpdatePayload(BaseModel):
    new_requirement_text: str


class RuleTreeUpdateResponse(BaseModel):
    session: RuleTreeSessionRead
    updated_tree: Dict[str, Any]
    requirement_diff: str
    node_diff: Dict[str, Any]


class RuleTreeConfirmPayload(BaseModel):
    tree_json: Dict[str, Any]
    requirement_text: str


class RuleTreeConfirmResponse(BaseModel):
    ok: bool
    session: RuleTreeSessionRead
    imported_nodes: int
