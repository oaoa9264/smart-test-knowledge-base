from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from sqlalchemy import func

from app.core.database import get_db
from app.models.entities import InputType, NodeStatus, Project, Requirement, RequirementInput, RuleNode, SourceType
from app.schemas.project import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    RequirementCreate,
    RequirementRead,
    RequirementUpdate,
    RequirementVersionRead,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

_VALID_SOURCE_TYPES = {source_type.value for source_type in SourceType}


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name, description=payload.description, product_code=payload.product_code)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=List[ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.id.desc()).all()


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    project.name = payload.name
    project.description = payload.description
    project.product_code = payload.product_code
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_id}/requirements",
    response_model=RequirementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_requirement(project_id: int, payload: RequirementCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    if payload.source_type not in _VALID_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="invalid source_type, must be one of: {0}".format(", ".join(sorted(_VALID_SOURCE_TYPES))),
        )

    requirement = Requirement(
        project_id=project_id,
        title=payload.title,
        raw_text=payload.raw_text,
        source_type=SourceType(payload.source_type),
    )
    db.add(requirement)
    db.flush()
    db.add(
        RequirementInput(
            requirement_id=requirement.id,
            input_type=InputType.raw_requirement,
            content=payload.raw_text,
            source_label="requirement.raw_text",
        )
    )
    db.commit()
    db.refresh(requirement)
    return requirement


@router.get("/{project_id}/requirements", response_model=List[RequirementRead])
def list_requirements(project_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Requirement)
        .filter(Requirement.project_id == project_id)
        .order_by(Requirement.id.desc())
        .all()
    )


@router.get("/{project_id}/requirements/{requirement_id}", response_model=RequirementRead)
def get_requirement(project_id: int, requirement_id: int, db: Session = Depends(get_db)):
    requirement = (
        db.query(Requirement)
        .filter(Requirement.id == requirement_id, Requirement.project_id == project_id)
        .first()
    )
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")
    return requirement


@router.put("/{project_id}/requirements/{requirement_id}", response_model=RequirementRead)
def update_requirement(
    project_id: int,
    requirement_id: int,
    payload: RequirementUpdate,
    db: Session = Depends(get_db),
):
    requirement = (
        db.query(Requirement)
        .filter(Requirement.id == requirement_id, Requirement.project_id == project_id)
        .first()
    )
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")
    if payload.source_type not in _VALID_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="invalid source_type, must be one of: {0}".format(", ".join(sorted(_VALID_SOURCE_TYPES))),
        )
    requirement.title = payload.title
    requirement.raw_text = payload.raw_text
    requirement.source_type = SourceType(payload.source_type)
    raw_input = (
        db.query(RequirementInput)
        .filter(
            RequirementInput.requirement_id == requirement_id,
            RequirementInput.input_type == InputType.raw_requirement,
        )
        .order_by(RequirementInput.created_at.asc(), RequirementInput.id.asc())
        .first()
    )
    if raw_input is None:
        db.add(
            RequirementInput(
                requirement_id=requirement_id,
                input_type=InputType.raw_requirement,
                content=payload.raw_text,
                source_label="requirement.raw_text",
            )
        )
    else:
        raw_input.content = payload.raw_text
    db.commit()
    db.refresh(requirement)
    return requirement


@router.delete("/{project_id}/requirements/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requirement(project_id: int, requirement_id: int, db: Session = Depends(get_db)):
    requirement = (
        db.query(Requirement)
        .filter(Requirement.id == requirement_id, Requirement.project_id == project_id)
        .first()
    )
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")
    db.delete(requirement)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_id}/requirements/{requirement_id}/new-version",
    response_model=RequirementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_new_version(project_id: int, requirement_id: int, db: Session = Depends(get_db)):
    requirement = (
        db.query(Requirement)
        .filter(Requirement.id == requirement_id, Requirement.project_id == project_id)
        .first()
    )
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    group_id = requirement.requirement_group_id or requirement.id
    if not requirement.requirement_group_id:
        requirement.requirement_group_id = requirement.id
        db.flush()

    max_version = (
        db.query(func.max(Requirement.version))
        .filter(Requirement.requirement_group_id == group_id)
        .scalar()
    ) or 1

    new_requirement = Requirement(
        project_id=project_id,
        title=requirement.title,
        raw_text=requirement.raw_text,
        source_type=requirement.source_type,
        version=max_version + 1,
        requirement_group_id=group_id,
    )
    db.add(new_requirement)
    db.flush()
    db.add(
        RequirementInput(
            requirement_id=new_requirement.id,
            input_type=InputType.raw_requirement,
            content=new_requirement.raw_text,
            source_label="requirement.raw_text",
        )
    )
    db.commit()
    db.refresh(new_requirement)
    return new_requirement


@router.get(
    "/{project_id}/requirements/{requirement_id}/versions",
    response_model=List[RequirementVersionRead],
)
def list_requirement_versions(project_id: int, requirement_id: int, db: Session = Depends(get_db)):
    requirement = (
        db.query(Requirement)
        .filter(Requirement.id == requirement_id, Requirement.project_id == project_id)
        .first()
    )
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    group_id = requirement.requirement_group_id or requirement.id
    versions = (
        db.query(Requirement)
        .filter(Requirement.requirement_group_id == group_id)
        .order_by(Requirement.version.asc())
        .all()
    )
    if not versions:
        versions = [requirement]

    result = []
    for req in versions:
        node_count = (
            db.query(func.count(RuleNode.id))
            .filter(RuleNode.requirement_id == req.id, RuleNode.status != NodeStatus.deleted)
            .scalar()
        ) or 0
        result.append(
            RequirementVersionRead(
                id=req.id,
                project_id=req.project_id,
                title=req.title,
                raw_text=req.raw_text,
                source_type=req.source_type.value if hasattr(req.source_type, "value") else str(req.source_type),
                version=int(req.version or 1),
                requirement_group_id=req.requirement_group_id,
                rule_node_count=node_count,
            )
        )
    return result
