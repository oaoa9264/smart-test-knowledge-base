import json
from typing import List, Optional

from pydantic import BaseModel, validator


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    product_code: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    product_code: Optional[str] = None


class ProjectRead(ProjectCreate):
    id: int

    class Config:
        orm_mode = True


class RequirementCreate(BaseModel):
    title: str
    raw_text: str
    source_type: str = "prd"
    matched_chains: Optional[List[str]] = None


class RequirementUpdate(BaseModel):
    title: str
    raw_text: str
    source_type: str = "prd"
    matched_chains: Optional[List[str]] = None


class RequirementRead(RequirementCreate):
    id: int
    project_id: int
    version: int = 1
    requirement_group_id: Optional[int] = None

    @validator("matched_chains", pre=True)
    def _parse_matched_chains(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v

    class Config:
        orm_mode = True


class RequirementVersionRead(RequirementRead):
    rule_node_count: int = 0
