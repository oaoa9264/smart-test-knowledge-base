import uuid
from typing import Dict, List

from sqlalchemy.orm import Session

from app.models.entities import NodeStatus, RuleNode, RulePath
from app.services.rule_engine import derive_rule_paths


def sync_rule_paths(db: Session, requirement_id: int) -> List[RulePath]:
    nodes = (
        db.query(RuleNode)
        .filter(
            RuleNode.requirement_id == requirement_id,
            RuleNode.status != NodeStatus.deleted,
        )
        .all()
    )
    node_dicts = [{"id": node.id, "parent_id": node.parent_id} for node in nodes]
    target_sequences = [",".join(path) for path in derive_rule_paths(node_dicts)]

    existing_paths = (
        db.query(RulePath)
        .filter(RulePath.requirement_id == requirement_id)
        .all()
    )

    existing_by_sequence: Dict[str, RulePath] = {}
    duplicate_paths: List[RulePath] = []
    for path in existing_paths:
        if path.node_sequence in existing_by_sequence:
            duplicate_paths.append(path)
            continue
        existing_by_sequence[path.node_sequence] = path

    keep_paths: List[RulePath] = []
    seen_sequences = set()
    for sequence in target_sequences:
        if sequence in seen_sequences:
            continue
        seen_sequences.add(sequence)

        path = existing_by_sequence.pop(sequence, None)
        if path is None:
            path = RulePath(
                id=str(uuid.uuid4()),
                requirement_id=requirement_id,
                node_sequence=sequence,
            )
            db.add(path)
        keep_paths.append(path)

    obsolete_paths = list(existing_by_sequence.values()) + duplicate_paths
    for path in obsolete_paths:
        path.bound_cases = []
        db.flush()
        db.delete(path)

    db.commit()
    return keep_paths
