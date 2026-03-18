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
    AnalysisStage,
    EvidenceBlock,
    EvidenceCreatedFrom,
    InputType,
    NodeStatus,
    NodeType,
    Project,
    Requirement,
    RequirementInput,
    RiskCategory,
    RiskDecision,
    RiskItem,
    RiskLevel,
    RiskSource,
    RiskValidity,
    RuleNode,
)
from app.services.llm_client import LLMClient
from app.services.product_doc_service import get_relevant_chunks
from app.services.prompts.risk_analysis import (
    RISK_ANALYSIS_SYSTEM_PROMPT,
    RISK_ANALYSIS_USER_TEMPLATE,
    RISK_ANALYSIS_WITH_PRODUCT_SYSTEM_PROMPT,
    RISK_ANALYSIS_WITH_PRODUCT_USER_TEMPLATE,
)
from app.services.requirement_module_analyzer import (
    ModuleAnalysisResult,
    analyze_requirement_modules,
)

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {c.value for c in RiskCategory}
_VALID_RISK_LEVELS = {r.value for r in RiskLevel}
_VALID_RISK_SOURCES = {s.value for s in RiskSource}
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

    module_result = analyze_requirement_modules(db, requirement, llm_client=llm_client)
    product_context = _build_product_context(db, requirement, module_result=module_result)

    raw_risks = _call_llm_for_risks(
        raw_text=requirement.raw_text,
        tree_nodes_text=tree_nodes_text,
        llm_client=llm_client,
        product_context=product_context,
        module_result=module_result,
    )

    node_id_set = {n.id for n in nodes}
    risk_items = _save_risks(
        db=db,
        requirement_id=requirement_id,
        raw_risks=raw_risks,
        valid_node_ids=node_id_set,
    )
    return risk_items


def _build_product_context(
    db: Session,
    requirement: Requirement,
    module_result: Optional[ModuleAnalysisResult] = None,
) -> Optional[str]:
    """Build product context string using hybrid retrieval."""
    project = db.query(Project).filter(Project.id == requirement.project_id).first()
    if not project or not project.product_code:
        return None

    matched = module_result.matched_modules if module_result else None
    related = module_result.related_modules if module_result else None

    chunks = get_relevant_chunks(
        db,
        project.product_code,
        requirement.raw_text,
        max_chunks=5,
        matched_modules=matched,
        related_modules=related,
    )
    if not chunks:
        return None

    sections = []
    for chunk in chunks:
        sections.append("### {title}\n{content}".format(title=chunk.title, content=chunk.content))
    return "\n\n".join(sections)


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


def clarify_risk(
    db: Session,
    risk_id: str,
    clarification_text: str,
    doc_update_needed: bool = False,
) -> RiskItem:
    risk = db.query(RiskItem).filter(RiskItem.id == risk_id).first()
    if not risk:
        raise ValueError("risk item not found")
    risk.clarification_text = clarification_text
    risk.doc_update_needed = doc_update_needed
    source_ref = "risk:{0}".format(risk.id)
    existing_input = (
        db.query(RequirementInput)
        .filter(
            RequirementInput.requirement_id == risk.requirement_id,
            RequirementInput.input_type == InputType.test_clarification,
            RequirementInput.source_label == source_ref,
        )
        .order_by(RequirementInput.id.asc())
        .first()
    )
    if existing_input is None:
        db.add(
            RequirementInput(
                requirement_id=risk.requirement_id,
                input_type=InputType.test_clarification,
                content=clarification_text,
                source_label=source_ref,
            )
        )
    else:
        existing_input.content = clarification_text

    try:
        from app.services.evidence_service import create_evidence_from_clarification

        create_evidence_from_clarification(
            db=db,
            risk_item_id=risk.id,
            statement=clarification_text,
        )
        db.refresh(risk)
        return risk
    except ValueError as exc:
        logger.info("Skip clarification evidence sync for risk %s: %s", risk.id, exc)
    db.commit()
    db.refresh(risk)
    return risk


def delete_risk(db: Session, risk_id: str) -> None:
    risk = db.query(RiskItem).filter(RiskItem.id == risk_id).first()
    if not risk:
        raise ValueError("risk item not found")
    source_ref = "risk:{0}".format(risk.id)
    (
        db.query(RequirementInput)
        .filter(
            RequirementInput.requirement_id == risk.requirement_id,
            RequirementInput.input_type == InputType.test_clarification,
            RequirementInput.source_label == source_ref,
        )
        .delete(synchronize_session=False)
    )
    (
        db.query(EvidenceBlock)
        .filter(
            EvidenceBlock.created_from == EvidenceCreatedFrom.risk_clarification,
            EvidenceBlock.source_span == source_ref,
        )
        .delete(synchronize_session=False)
    )
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
    if risk.converted_node_id:
        existing = db.query(RuleNode).filter(RuleNode.id == risk.converted_node_id).first()
        if existing:
            return existing

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
    db.flush()
    risk.converted_node_id = node.id
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
    product_context: Optional[str] = None,
    module_result: Optional[ModuleAnalysisResult] = None,
) -> List[Dict[str, Any]]:
    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider != "llm":
        return _mock_risk_analysis(tree_nodes_text, has_product_context=bool(product_context))

    try:
        llm = llm_client or LLMClient()
        if product_context:
            system_prompt = RISK_ANALYSIS_WITH_PRODUCT_SYSTEM_PROMPT

            module_section = ""
            if module_result and module_result.matched_modules:
                module_section = (
                    "\n\n【需求模块分析】\n"
                    "该需求主要涉及以下模块：{matched}\n"
                    "可能关联的模块：{related}\n"
                    "分析说明：{analysis}"
                ).format(
                    matched="、".join(module_result.matched_modules),
                    related="、".join(module_result.related_modules) if module_result.related_modules else "无",
                    analysis=module_result.module_analysis or "无",
                )

            user_prompt = RISK_ANALYSIS_WITH_PRODUCT_USER_TEMPLATE.format(
                product_context=product_context,
                raw_text=raw_text,
                tree_nodes=tree_nodes_text,
                module_context=module_section,
            )
        else:
            system_prompt = RISK_ANALYSIS_SYSTEM_PROMPT
            user_prompt = RISK_ANALYSIS_USER_TEMPLATE.format(
                raw_text=raw_text,
                tree_nodes=tree_nodes_text,
            )
        payload = llm.chat_with_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return _extract_risks_from_payload(payload)
    except Exception as exc:
        logger.warning("Risk analysis LLM failed, using mock (%s: %s)", type(exc).__name__, exc)
        return _mock_risk_analysis(tree_nodes_text, has_product_context=bool(product_context))


def _mock_risk_analysis(tree_nodes_text: str, has_product_context: bool = False) -> List[Dict[str, Any]]:
    risks = [
        {
            "id": "risk_1",
            "related_node_id": None,
            "category": "input_validation",
            "risk_level": "medium",
            "risk_source": "rule_tree",
            "description": "未明确输入为空时的处理逻辑",
            "suggestion": "建议增加空值校验，给出友好提示",
        },
        {
            "id": "risk_2",
            "related_node_id": None,
            "category": "flow_gap",
            "risk_level": "high",
            "risk_source": "rule_tree",
            "description": "流程中未覆盖前置条件不满足时的回退路径",
            "suggestion": "建议补充前置条件校验和异常流程处理",
        },
    ]
    if has_product_context:
        risks.append({
            "id": "risk_3",
            "related_node_id": None,
            "category": "product_knowledge",
            "risk_level": "high",
            "risk_source": "product_knowledge",
            "description": "需求未提及现有产品流程中已有的状态校验约束，可能与现有产品逻辑冲突",
            "suggestion": "核对现有产品文档中的状态流转规则，确认需求是否需要适配",
        })
    return risks


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

        risk_source = str(item.get("risk_source", "rule_tree"))
        if risk_source not in _VALID_RISK_SOURCES:
            risk_source = "product_knowledge" if category == "product_knowledge" else "rule_tree"

        risks.append({
            "id": risk_id,
            "related_node_id": related_node_id,
            "category": category,
            "risk_level": risk_level,
            "risk_source": risk_source,
            "description": description,
            "suggestion": suggestion,
        })

    return risks


def _normalize_description(desc: str) -> str:
    """Normalize description for dedup matching: strip whitespace and lowercase."""
    import re
    return re.sub(r"\s+", "", desc).lower()


def save_risks_to_ledger(
    db: Session,
    requirement_id: int,
    raw_risks: List[Dict[str, Any]],
    valid_node_ids: Optional[Set[str]] = None,
    analysis_stage: Optional[str] = None,
    origin_snapshot_id: Optional[int] = None,
    mark_unseen_superseded: bool = False,
) -> List[RiskItem]:
    """Public entry point for writing risks to the continuous ledger.

    When *mark_unseen_superseded* is True, any existing active risk for
    *requirement_id* that was not matched during this round is marked
    ``validity=superseded``.  This is used by the review-stage analyzer
    where a new analysis fully replaces the previous risk picture.
    """
    return _save_risks(
        db=db,
        requirement_id=requirement_id,
        raw_risks=raw_risks,
        valid_node_ids=valid_node_ids or set(),
        analysis_stage=analysis_stage,
        origin_snapshot_id=origin_snapshot_id,
        mark_unseen_superseded=mark_unseen_superseded,
    )


def _save_risks(
    db: Session,
    requirement_id: int,
    raw_risks: List[Dict[str, Any]],
    valid_node_ids: Set[str],
    analysis_stage: Optional[str] = None,
    origin_snapshot_id: Optional[int] = None,
    mark_unseen_superseded: bool = False,
) -> List[RiskItem]:
    existing_risks = (
        db.query(RiskItem)
        .filter(RiskItem.requirement_id == requirement_id)
        .all()
    )
    existing_index: Dict[str, RiskItem] = {}
    for er in existing_risks:
        cat = er.category.value if hasattr(er.category, "value") else er.category
        node_id = er.related_node_id or ""
        norm_desc = _normalize_description(er.description)
        key = "{cat}|{node}|{desc}".format(cat=cat, node=node_id, desc=norm_desc)
        existing_index[key] = er

    now = datetime.utcnow()
    matched_ids: Set[str] = set()
    result: List[RiskItem] = []

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

        source_str = risk_data.get("risk_source", "rule_tree")
        if source_str not in _VALID_RISK_SOURCES:
            source_str = "product_knowledge" if category_str == "product_knowledge" else "rule_tree"

        description = risk_data.get("description", "")
        node_key = related_node_id or ""
        norm_desc = _normalize_description(description)
        dedup_key = "{cat}|{node}|{desc}".format(cat=category_str, node=node_key, desc=norm_desc)

        existing = existing_index.get(dedup_key)
        if existing and existing.id not in matched_ids:
            existing.last_analysis_at = now
            if origin_snapshot_id is not None:
                existing.last_seen_snapshot_id = origin_snapshot_id
            if analysis_stage:
                existing.analysis_stage = AnalysisStage(analysis_stage)
            existing.risk_level = RiskLevel(level_str)
            existing.risk_source = RiskSource(source_str)
            existing.suggestion = risk_data.get("suggestion", "")
            validity = existing.validity.value if hasattr(existing.validity, "value") else existing.validity
            if validity in (RiskValidity.resolved.value, RiskValidity.superseded.value):
                existing.validity = RiskValidity.reopened
            matched_ids.add(existing.id)
            result.append(existing)
        else:
            stage_val = AnalysisStage(analysis_stage) if analysis_stage else None
            risk_item = RiskItem(
                id=str(uuid.uuid4()),
                requirement_id=requirement_id,
                related_node_id=related_node_id,
                category=RiskCategory(category_str),
                risk_level=RiskLevel(level_str),
                risk_source=RiskSource(source_str),
                description=description,
                suggestion=risk_data.get("suggestion", ""),
                validity=RiskValidity.active,
                analysis_stage=stage_val,
                origin_snapshot_id=origin_snapshot_id,
                last_seen_snapshot_id=origin_snapshot_id,
                last_analysis_at=now,
            )
            db.add(risk_item)
            result.append(risk_item)

    if mark_unseen_superseded:
        for er in existing_risks:
            validity = er.validity.value if hasattr(er.validity, "value") else er.validity
            if er.id not in matched_ids and validity in (
                RiskValidity.active.value,
                RiskValidity.reopened.value,
            ):
                er.validity = RiskValidity.superseded
                er.last_analysis_at = now

    db.commit()
    for item in result:
        db.refresh(item)
    return result


# ---------------------------------------------------------------------------
# Clarification question generation
# ---------------------------------------------------------------------------

def generate_clarification_questions(
    db: Session,
    requirement_id: int,
    llm_client: Optional[Any] = None,
) -> List[Dict[str, str]]:
    """Generate structured clarification questions for a requirement.

    Uses the module analysis result and existing risk items to ask LLM
    for targeted clarification questions.
    """
    from app.services.prompts.clarification import (
        CLARIFICATION_SYSTEM_PROMPT,
        CLARIFICATION_USER_TEMPLATE,
    )

    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    module_result = analyze_requirement_modules(db, requirement, llm_client=llm_client)

    risks = get_risks_for_requirement(db=db, requirement_id=requirement_id)
    risk_lines = []
    for r in risks:
        level = r.risk_level.value if hasattr(r.risk_level, "value") else r.risk_level
        cat = r.category.value if hasattr(r.category, "value") else r.category
        risk_lines.append("- [{level}][{cat}] {desc}".format(
            level=level, cat=cat, desc=r.description,
        ))
    risk_items_text = "\n".join(risk_lines) if risk_lines else "(no risks identified yet)"

    matched_str = "、".join(module_result.matched_modules) if module_result and module_result.matched_modules else "未识别"
    related_str = "、".join(module_result.related_modules) if module_result and module_result.related_modules else "无"
    analysis_str = module_result.module_analysis if module_result and module_result.module_analysis else "无"

    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider != "llm":
        return _mock_clarification_questions(matched_str, risks)

    try:
        llm = llm_client or LLMClient()
        user_prompt = CLARIFICATION_USER_TEMPLATE.format(
            requirement_text=requirement.raw_text,
            matched_modules=matched_str,
            related_modules=related_str,
            module_analysis=analysis_str,
            risk_items_text=risk_items_text,
        )
        payload = llm.chat_with_json(
            system_prompt=CLARIFICATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return _parse_clarification_payload(payload)
    except Exception as exc:
        logger.warning("Clarification LLM failed (%s: %s), using mock", type(exc).__name__, exc)
        return _mock_clarification_questions(matched_str, risks)


def _parse_clarification_payload(payload: Any) -> List[Dict[str, str]]:
    if not isinstance(payload, dict):
        return []
    questions = payload.get("questions", [])
    if not isinstance(questions, list):
        return []
    result = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        result.append({
            "module": str(q.get("module", "")),
            "question": str(q.get("question", "")),
            "context": str(q.get("context", "")),
        })
    return result


def _mock_clarification_questions(
    matched_modules_str: str,
    risks: List[RiskItem],
) -> List[Dict[str, str]]:
    questions = [
        {
            "module": matched_modules_str.split("、")[0] if matched_modules_str != "未识别" else "全局",
            "question": "本次需求的改动范围是否仅限于描述中提到的场景？是否还有其他未提及的关联场景需要一并考虑？",
            "context": "需求描述可能未覆盖所有受影响的业务场景",
        },
    ]
    for r in risks[:2]:
        cat = r.category.value if hasattr(r.category, "value") else r.category
        if cat == "product_knowledge":
            questions.append({
                "module": matched_modules_str.split("、")[0] if matched_modules_str != "未识别" else "全局",
                "question": "风险「{desc}」涉及现有产品流程，请确认需求是否需要适配现有逻辑？".format(desc=r.description),
                "context": r.suggestion or "需要确认与现有产品流程的兼容性",
            })
    return questions
