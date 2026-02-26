from typing import List, Optional

from pydantic import BaseModel


class RuleNodeCreate(BaseModel):
    requirement_id: int
    parent_id: Optional[str] = None
    node_type: str
    content: str
    risk_level: str = "medium"


class RuleNodeUpdate(BaseModel):
    parent_id: Optional[str] = None
    node_type: Optional[str] = None
    content: Optional[str] = None
    risk_level: Optional[str] = None
    status: Optional[str] = None


class RuleNodeRead(BaseModel):
    id: str
    requirement_id: int
    parent_id: Optional[str] = None
    node_type: str
    content: str
    risk_level: str
    version: int
    status: str

    class Config:
        orm_mode = True


class RulePathRead(BaseModel):
    id: str
    requirement_id: int
    node_sequence: List[str]


class RuleTreeRead(BaseModel):
    nodes: List[RuleNodeRead]
    paths: List[RulePathRead]
