import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import NodeStatus, Requirement, RiskItem, RuleNode, RulePath, TestCase, TestCaseStatus
from app.schemas.rule import RuleNodeCreate, RuleNodeRead, RuleNodeUpdate, RulePathRead, RuleTreeRead
from app.services.impact import analyze_impact
from app.services.rule_path_service import sync_rule_paths

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _assert_parent_chain_no_cycle(
    db: Session,
    requirement_id: int,
    node_id: str,
    parent_id: str,
):
    if parent_id == node_id:
        raise HTTPException(status_code=400, detail="cycle detected in parent chain")

    parent = (
        db.query(RuleNode)
        .filter(
            RuleNode.id == parent_id,
            RuleNode.requirement_id == requirement_id,
            RuleNode.status != NodeStatus.deleted,
        )
        .first()
    )
    if not parent:
        raise HTTPException(status_code=400, detail="invalid parent_id")

    cursor = parent
    visited = set()
    while cursor:
        if cursor.id == node_id or cursor.id in visited:
            raise HTTPException(status_code=400, detail="cycle detected in parent chain")
        visited.add(cursor.id)

        if not cursor.parent_id:
            break

        cursor = (
            db.query(RuleNode)
            .filter(
                RuleNode.id == cursor.parent_id,
                RuleNode.requirement_id == requirement_id,
                RuleNode.status != NodeStatus.deleted,
            )
            .first()
        )


def _regenerate_paths(db: Session, requirement_id: int):
    return sync_rule_paths(db, requirement_id)


def _mark_impacted_cases(db: Session, changed_node_ids, requirement_id: int):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        return {"affected_case_ids": [], "needs_review_case_ids": [], "affected_count": 0}
    cases = db.query(TestCase).filter(TestCase.project_id == requirement.project_id).all()
    all_paths = db.query(RulePath).filter(RulePath.requirement_id == requirement_id).all()

    case_payload = [
        {"id": c.id, "bound_rule_nodes": [n.id for n in c.bound_rule_nodes], "bound_paths": [p.id for p in c.bound_paths]}
        for c in cases
    ]
    path_payload = [p.node_sequence.split(",") if p.node_sequence else [] for p in all_paths]

    impact = analyze_impact(changed_node_ids=changed_node_ids, testcases=case_payload, paths=path_payload)
    if impact["needs_review_case_ids"]:
        (
            db.query(TestCase)
            .filter(TestCase.id.in_(impact["needs_review_case_ids"]))
            .update({"status": TestCaseStatus.needs_review}, synchronize_session=False)
        )
        db.commit()
    return impact


@router.post("/nodes", response_model=RuleNodeRead, status_code=status.HTTP_201_CREATED)
def create_node(payload: RuleNodeCreate, db: Session = Depends(get_db)):
    requirement = db.query(Requirement).filter(Requirement.id == payload.requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    node_id = str(uuid.uuid4())
    if payload.parent_id:
        _assert_parent_chain_no_cycle(
            db=db,
            requirement_id=payload.requirement_id,
            node_id=node_id,
            parent_id=payload.parent_id,
        )

    node = RuleNode(
        id=node_id,
        requirement_id=payload.requirement_id,
        parent_id=payload.parent_id,
        node_type=payload.node_type,
        content=payload.content,
        risk_level=payload.risk_level,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    _regenerate_paths(db, payload.requirement_id)
    return node


@router.get("/requirements/{requirement_id}/tree", response_model=RuleTreeRead)
def get_rule_tree(requirement_id: int, db: Session = Depends(get_db)):
    nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id == requirement_id, RuleNode.status != NodeStatus.deleted)
        .all()
    )
    paths = db.query(RulePath).filter(RulePath.requirement_id == requirement_id).all()

    path_models = [
        RulePathRead(id=p.id, requirement_id=p.requirement_id, node_sequence=p.node_sequence.split(",") if p.node_sequence else [])
        for p in paths
    ]
    return RuleTreeRead(nodes=nodes, paths=path_models)


@router.put("/nodes/{node_id}")
def update_node(node_id: str, payload: RuleNodeUpdate, db: Session = Depends(get_db)):
    node = db.query(RuleNode).filter(RuleNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="node not found")

    provided_fields = set(payload.__fields_set__)

    if "parent_id" in provided_fields and payload.parent_id is not None:
        _assert_parent_chain_no_cycle(
            db=db,
            requirement_id=node.requirement_id,
            node_id=node.id,
            parent_id=payload.parent_id,
        )

    changed_node_ids = [node.id]
    if "parent_id" in provided_fields:
        node.parent_id = payload.parent_id

    for field in ["node_type", "content", "risk_level", "status"]:
        if field in provided_fields:
            setattr(node, field, getattr(payload, field))
    node.version += 1

    db.commit()
    db.refresh(node)

    _regenerate_paths(db, node.requirement_id)
    impact = _mark_impacted_cases(db, changed_node_ids=changed_node_ids, requirement_id=node.requirement_id)

    return {"node": RuleNodeRead.from_orm(node), "impact": impact}


@router.delete("/nodes/{node_id}")
def delete_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(RuleNode).filter(RuleNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="node not found")

    node.status = NodeStatus.deleted
    node.version += 1
    db.query(RiskItem).filter(RiskItem.related_node_id == node_id).delete()
    db.commit()

    _regenerate_paths(db, node.requirement_id)
    impact = _mark_impacted_cases(db, changed_node_ids=[node.id], requirement_id=node.requirement_id)
    return {"ok": True, "impact": impact}


@router.post("/impact")
def impact_preview(payload: dict, db: Session = Depends(get_db)):
    requirement_id = payload.get("requirement_id")
    changed_node_ids = payload.get("changed_node_ids", [])

    paths = db.query(RulePath).filter(RulePath.requirement_id == requirement_id).all()
    cases = db.query(TestCase).all()

    case_payload = [
        {"id": c.id, "bound_rule_nodes": [n.id for n in c.bound_rule_nodes], "bound_paths": [p.id for p in c.bound_paths]}
        for c in cases
    ]
    path_payload = [p.node_sequence.split(",") if p.node_sequence else [] for p in paths]

    return analyze_impact(changed_node_ids=changed_node_ids, testcases=case_payload, paths=path_payload)
