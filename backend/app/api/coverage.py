from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import NodeStatus, Project, Requirement, RuleNode, RulePath, TestCase
from app.services.coverage import build_coverage_matrix

router = APIRouter(prefix="/api/coverage", tags=["coverage"])


def _empty_coverage():
    return {"rows": [], "summary": {"total_nodes": 0, "covered_nodes": 0, "coverage_rate": 0, "uncovered_critical": [], "uncovered_paths": []}}


def _build_requirement_coverage(project_id: int, requirement_id: int, db: Session):
    requirement = (
        db.query(Requirement)
        .filter(Requirement.id == requirement_id, Requirement.project_id == project_id)
        .first()
    )
    if not requirement:
        return _empty_coverage()

    requirement_ids = [requirement.id]
    nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id.in_(requirement_ids), RuleNode.status != NodeStatus.deleted)
        .all()
    )
    paths = db.query(RulePath).filter(RulePath.requirement_id.in_(requirement_ids)).all()
    cases = db.query(TestCase).filter(TestCase.project_id == project_id).all()

    node_payload = [
        {
            "id": n.id,
            "content": n.content,
            "risk_level": n.risk_level.value if hasattr(n.risk_level, "value") else str(n.risk_level),
        }
        for n in nodes
    ]
    case_payload = [
        {"id": c.id, "bound_rule_nodes": [n.id for n in c.bound_rule_nodes], "bound_paths": [p.id for p in c.bound_paths]}
        for c in cases
    ]
    path_payload = [p.node_sequence.split(",") if p.node_sequence else [] for p in paths]

    return build_coverage_matrix(nodes=node_payload, testcases=case_payload, paths=path_payload)


@router.get("/projects/{project_id}")
def coverage_by_project(project_id: int, requirement_id: Optional[int] = None, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return _empty_coverage()

    if requirement_id is not None:
        return _build_requirement_coverage(project_id=project_id, requirement_id=requirement_id, db=db)

    requirements = db.query(Requirement).filter(Requirement.project_id == project_id).all()
    requirement_ids = [r.id for r in requirements]

    nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id.in_(requirement_ids), RuleNode.status != NodeStatus.deleted)
        .all()
        if requirement_ids
        else []
    )
    paths = db.query(RulePath).filter(RulePath.requirement_id.in_(requirement_ids)).all() if requirement_ids else []
    cases = db.query(TestCase).filter(TestCase.project_id == project_id).all()

    node_payload = [
        {
            "id": n.id,
            "content": n.content,
            "risk_level": n.risk_level.value if hasattr(n.risk_level, "value") else str(n.risk_level),
        }
        for n in nodes
    ]
    case_payload = [
        {"id": c.id, "bound_rule_nodes": [n.id for n in c.bound_rule_nodes], "bound_paths": [p.id for p in c.bound_paths]}
        for c in cases
    ]
    path_payload = [p.node_sequence.split(",") if p.node_sequence else [] for p in paths]

    return build_coverage_matrix(nodes=node_payload, testcases=case_payload, paths=path_payload)


@router.get("/projects/{project_id}/requirements/{requirement_id}")
def coverage_by_requirement(project_id: int, requirement_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return _empty_coverage()
    return _build_requirement_coverage(project_id=project_id, requirement_id=requirement_id, db=db)
