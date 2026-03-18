from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import NodeStatus, Project, Requirement, RuleNode, RulePath, TestCase
from app.schemas.testcase import TestCaseCreate, TestCaseRead, TestCaseUpdate

router = APIRouter(prefix="/api/testcases", tags=["testcases"])


def _to_read_model(case: TestCase) -> TestCaseRead:
    risk_value = case.risk_level.value if hasattr(case.risk_level, "value") else str(case.risk_level)
    status_value = case.status.value if hasattr(case.status, "value") else str(case.status)
    return TestCaseRead(
        id=case.id,
        project_id=case.project_id,
        title=case.title,
        precondition=case.precondition or "",
        steps=case.steps,
        expected_result=case.expected_result,
        risk_level=risk_value,
        status=status_value,
        bound_rule_node_ids=[n.id for n in case.bound_rule_nodes],
        bound_path_ids=[p.id for p in case.bound_paths],
    )


def _resolve_case_bindings(
    db: Session,
    project_id: int,
    bound_rule_node_ids: List[str],
    bound_path_ids: List[str],
):
    requested_node_ids = list(dict.fromkeys(bound_rule_node_ids or []))
    requested_path_ids = list(dict.fromkeys(bound_path_ids or []))

    nodes = []
    if requested_node_ids:
        node_rows = (
            db.query(RuleNode)
            .join(Requirement, RuleNode.requirement_id == Requirement.id)
            .filter(
                RuleNode.id.in_(requested_node_ids),
                RuleNode.status != NodeStatus.deleted,
                Requirement.project_id == project_id,
            )
            .all()
        )
        node_map = {node.id: node for node in node_rows}
        if len(node_map) != len(requested_node_ids):
            raise HTTPException(status_code=400, detail="invalid bound_rule_node_ids")
        nodes = [node_map[node_id] for node_id in requested_node_ids]

    paths = []
    if requested_path_ids:
        path_rows = (
            db.query(RulePath)
            .join(Requirement, RulePath.requirement_id == Requirement.id)
            .filter(
                RulePath.id.in_(requested_path_ids),
                Requirement.project_id == project_id,
            )
            .all()
        )
        path_map = {path.id: path for path in path_rows}
        if len(path_map) != len(requested_path_ids):
            raise HTTPException(status_code=400, detail="invalid bound_path_ids")
        paths = [path_map[path_id] for path_id in requested_path_ids]

    return nodes, paths


@router.post("", response_model=TestCaseRead, status_code=status.HTTP_201_CREATED)
def create_testcase(payload: TestCaseCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    case = TestCase(
        project_id=payload.project_id,
        title=payload.title,
        precondition=payload.precondition,
        steps=payload.steps,
        expected_result=payload.expected_result,
        risk_level=payload.risk_level,
        status=payload.status,
    )

    nodes, paths = _resolve_case_bindings(
        db=db,
        project_id=payload.project_id,
        bound_rule_node_ids=payload.bound_rule_node_ids,
        bound_path_ids=payload.bound_path_ids,
    )
    case.bound_rule_nodes = nodes
    case.bound_paths = paths

    db.add(case)
    db.commit()
    db.refresh(case)
    return _to_read_model(case)


@router.get("/projects/{project_id}", response_model=List[TestCaseRead])
def list_testcases(project_id: int, requirement_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(TestCase).filter(TestCase.project_id == project_id)

    if requirement_id is not None:
        requirement = (
            db.query(Requirement)
            .filter(Requirement.id == requirement_id, Requirement.project_id == project_id)
            .first()
        )
        if not requirement:
            raise HTTPException(status_code=404, detail="requirement not found")

        query = (
            query.outerjoin(TestCase.bound_rule_nodes)
            .outerjoin(TestCase.bound_paths)
            .filter(
                or_(
                    RuleNode.requirement_id == requirement_id,
                    RulePath.requirement_id == requirement_id,
                )
            )
            .distinct()
        )

    cases = query.order_by(TestCase.id.desc()).all()
    return [_to_read_model(case) for case in cases]


@router.get("/{case_id}", response_model=TestCaseRead)
def get_testcase(case_id: int, db: Session = Depends(get_db)):
    case = db.query(TestCase).filter(TestCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="testcase not found")
    return _to_read_model(case)


@router.put("/{case_id}", response_model=TestCaseRead)
def update_testcase(case_id: int, payload: TestCaseUpdate, db: Session = Depends(get_db)):
    case = db.query(TestCase).filter(TestCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="testcase not found")

    case.title = payload.title
    case.precondition = payload.precondition
    case.steps = payload.steps
    case.expected_result = payload.expected_result
    case.risk_level = payload.risk_level
    case.status = payload.status

    nodes, paths = _resolve_case_bindings(
        db=db,
        project_id=case.project_id,
        bound_rule_node_ids=payload.bound_rule_node_ids,
        bound_path_ids=payload.bound_path_ids,
    )
    case.bound_rule_nodes = nodes
    case.bound_paths = paths

    db.commit()
    db.refresh(case)
    return _to_read_model(case)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_testcase(case_id: int, db: Session = Depends(get_db)):
    case = db.query(TestCase).filter(TestCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="testcase not found")
    db.delete(case)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batch-delete")
def batch_delete_testcases(payload: dict, db: Session = Depends(get_db)):
    ids: List[int] = payload.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="ids is required")
    cases = db.query(TestCase).filter(TestCase.id.in_(ids)).all()
    deleted_count = len(cases)
    for case in cases:
        db.delete(case)
    db.commit()
    return {"deleted_count": deleted_count}
