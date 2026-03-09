import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.entities import (
    NodeStatus,
    NodeType,
    Requirement,
    RiskCategory,
    RiskDecision,
    RiskItem,
    RiskLevel,
    RuleNode,
)
from app.services.llm_client import LLMClient
from app.services.prompts.risk_analysis import (
    RISK_ANALYSIS_SYSTEM_PROMPT,
    RISK_ANALYSIS_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {c.value for c in RiskCategory}
_VALID_RISK_LEVELS = {r.value for r in RiskLevel}
_ANALYSIS_STATE_GUARD = threading.Lock()


@dataclass
class _AnalysisState:
    condition: threading.Condition = field(default_factory=threading.Condition)
    running: bool = False
    error: Optional[Exception] = None


_ANALYSIS_STATES: Dict[int, _AnalysisState] = {}


def analyze_risks(
    db: Session,
    requirement_id: int,
    llm_client: Optional[Any] = None,
) -> List[RiskItem]:
    state, should_wait = _begin_requirement_analysis(requirement_id)
    if should_wait:
        _wait_for_requirement_analysis(state)
        return get_risks_for_requirement(db=db, requirement_id=requirement_id)

    try:
        risk_items = _analyze_risks_once(
            db=db,
            requirement_id=requirement_id,
            llm_client=llm_client,
        )
    except Exception as exc:
        _finish_requirement_analysis(requirement_id=requirement_id, state=state, error=exc)
        raise

    _finish_requirement_analysis(requirement_id=requirement_id, state=state, error=None)
    return risk_items


def _analyze_risks_once(
    db: Session,
    requirement_id: int,
    llm_client: Optional[Any] = None,
) -> List[RiskItem]:
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id == requirement_id, RuleNode.status != NodeStatus.deleted)
        .all()
    )
    if not nodes:
        raise ValueError("no rule nodes found for this requirement")

    tree_nodes_text = "\n".join(
        "- [{id}] ({type}) {content}".format(
            id=n.id,
            type=n.node_type.value if hasattr(n.node_type, "value") else n.node_type,
            content=n.content,
        )
        for n in nodes
    )

    raw_risks = _call_llm_for_risks(
        raw_text=requirement.raw_text,
        tree_nodes_text=tree_nodes_text,
        llm_client=llm_client,
    )

    node_id_set = {n.id for n in nodes}
    risk_items = _save_risks(
        db=db,
        requirement_id=requirement_id,
        raw_risks=raw_risks,
        valid_node_ids=node_id_set,
    )
    return risk_items


def _begin_requirement_analysis(requirement_id: int) -> Tuple[_AnalysisState, bool]:
    with _ANALYSIS_STATE_GUARD:
        state = _ANALYSIS_STATES.get(requirement_id)
        if state is None:
            state = _AnalysisState()
            _ANALYSIS_STATES[requirement_id] = state

    with state.condition:
        if state.running:
            return state, True
        state.running = True
        state.error = None
        return state, False


def _wait_for_requirement_analysis(state: _AnalysisState) -> None:
    with state.condition:
        while state.running:
            state.condition.wait()
        if state.error is not None:
            raise state.error


def _finish_requirement_analysis(requirement_id: int, state: _AnalysisState, error: Optional[Exception]) -> None:
    with state.condition:
        state.running = False
        state.error = error
        state.condition.notify_all()

    with _ANALYSIS_STATE_GUARD:
        current = _ANALYSIS_STATES.get(requirement_id)
        if current is state and not state.running:
            _ANALYSIS_STATES.pop(requirement_id, None)


def save_risks_from_generation(
    db: Session,
    requirement_id: int,
    raw_risks: List[Dict[str, Any]],
    node_id_map: Optional[Dict[str, str]] = None,
) -> List[RiskItem]:
    """Save risks produced during tree generation (architecture / ai-parse).

    node_id_map maps source node IDs (e.g. dt_1) to persisted UUIDs.
    """
    nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id == requirement_id, RuleNode.status != NodeStatus.deleted)
        .all()
    )
    valid_node_ids = {n.id for n in nodes}

    mapped_risks: List[Dict[str, Any]] = []
    for risk in raw_risks:
        mapped = dict(risk)
        related = mapped.get("related_node_id")
        if related and node_id_map and related in node_id_map:
            mapped["related_node_id"] = node_id_map[related]
        mapped_risks.append(mapped)

    return _save_risks(
        db=db,
        requirement_id=requirement_id,
        raw_risks=mapped_risks,
        valid_node_ids=valid_node_ids,
    )


def decide_risk(
    db: Session,
    risk_id: str,
    decision: str,
    reason: str,
) -> RiskItem:
    risk = db.query(RiskItem).filter(RiskItem.id == risk_id).first()
    if not risk:
        raise ValueError("risk item not found")

    risk.decision = RiskDecision(decision)
    risk.decision_reason = reason
    risk.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(risk)
    return risk


def delete_risk(db: Session, risk_id: str) -> None:
    risk = db.query(RiskItem).filter(RiskItem.id == risk_id).first()
    if not risk:
        raise ValueError("risk item not found")
    db.delete(risk)
    db.commit()


def risk_to_node(
    db: Session,
    risk_id: str,
) -> RuleNode:
    risk = db.query(RiskItem).filter(RiskItem.id == risk_id).first()
    if not risk:
        raise ValueError("risk item not found")
    if risk.decision != RiskDecision.accepted:
        raise ValueError("only accepted risks can be converted to nodes")

    node = RuleNode(
        id=str(uuid.uuid4()),
        requirement_id=risk.requirement_id,
        parent_id=risk.related_node_id,
        node_type=NodeType.exception,
        content="{desc}（建议：{sug}）".format(desc=risk.description, sug=risk.suggestion),
        risk_level=RiskLevel(risk.risk_level.value if hasattr(risk.risk_level, "value") else risk.risk_level),
        status=NodeStatus.active,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def get_risks_for_requirement(db: Session, requirement_id: int) -> List[RiskItem]:
    return (
        db.query(RiskItem)
        .filter(RiskItem.requirement_id == requirement_id)
        .order_by(RiskItem.created_at.desc())
        .all()
    )


def _call_llm_for_risks(
    raw_text: str,
    tree_nodes_text: str,
    llm_client: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider != "llm":
        return _mock_risk_analysis(tree_nodes_text)

    try:
        llm = llm_client or LLMClient()
        payload = llm.chat_with_json(
            system_prompt=RISK_ANALYSIS_SYSTEM_PROMPT,
            user_prompt=RISK_ANALYSIS_USER_TEMPLATE.format(
                raw_text=raw_text,
                tree_nodes=tree_nodes_text,
            ),
        )
        return _extract_risks_from_payload(payload)
    except Exception as exc:
        logger.warning("Risk analysis LLM failed, using mock (%s: %s)", type(exc).__name__, exc)
        return _mock_risk_analysis(tree_nodes_text)


def _mock_risk_analysis(tree_nodes_text: str) -> List[Dict[str, Any]]:
    return [
        {
            "id": "risk_1",
            "related_node_id": None,
            "category": "input_validation",
            "risk_level": "medium",
            "description": "未明确输入为空时的处理逻辑",
            "suggestion": "建议增加空值校验，给出友好提示",
        },
        {
            "id": "risk_2",
            "related_node_id": None,
            "category": "flow_gap",
            "risk_level": "high",
            "description": "流程中未覆盖前置条件不满足时的回退路径",
            "suggestion": "建议补充前置条件校验和异常流程处理",
        },
    ]


def _extract_risks_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    raw_risks = payload.get("risks")
    if not isinstance(raw_risks, list):
        return []

    risks: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_risks, start=1):
        if not isinstance(item, dict):
            continue

        risk_id = str(item.get("id", "risk_{0}".format(index)))
        related_node_id = item.get("related_node_id") or None
        category = str(item.get("category", "flow_gap"))
        if category not in _VALID_CATEGORIES:
            category = "flow_gap"
        risk_level = str(item.get("risk_level", "medium"))
        if risk_level not in _VALID_RISK_LEVELS:
            risk_level = "medium"
        description = str(item.get("description", ""))
        suggestion = str(item.get("suggestion", ""))

        if not description:
            continue

        risks.append({
            "id": risk_id,
            "related_node_id": related_node_id,
            "category": category,
            "risk_level": risk_level,
            "description": description,
            "suggestion": suggestion,
        })

    return risks


def _save_risks(
    db: Session,
    requirement_id: int,
    raw_risks: List[Dict[str, Any]],
    valid_node_ids: Set[str],
) -> List[RiskItem]:
    saved: List[RiskItem] = []
    db.query(RiskItem).filter(RiskItem.requirement_id == requirement_id).delete()
    db.flush()
    for risk_data in raw_risks:
        related_node_id = risk_data.get("related_node_id")
        if related_node_id and related_node_id not in valid_node_ids:
            related_node_id = None

        category_str = risk_data.get("category", "flow_gap")
        if category_str not in _VALID_CATEGORIES:
            category_str = "flow_gap"

        level_str = risk_data.get("risk_level", "medium")
        if level_str not in _VALID_RISK_LEVELS:
            level_str = "medium"

        risk_item = RiskItem(
            id=str(uuid.uuid4()),
            requirement_id=requirement_id,
            related_node_id=related_node_id,
            category=RiskCategory(category_str),
            risk_level=RiskLevel(level_str),
            description=risk_data.get("description", ""),
            suggestion=risk_data.get("suggestion", ""),
        )
        db.add(risk_item)
        saved.append(risk_item)

    db.commit()
    for item in saved:
        db.refresh(item)
    return saved
