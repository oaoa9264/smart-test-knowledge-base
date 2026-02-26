from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectRead(ProjectCreate):
    id: int

    class Config:
        orm_mode = True


class RequirementCreate(BaseModel):
    title: str
    raw_text: str
    source_type: str = "prd"


class RequirementUpdate(BaseModel):
    title: str
    raw_text: str
    source_type: str = "prd"


class RequirementRead(RequirementCreate):
    id: int
    project_id: int

    class Config:
        orm_mode = True
