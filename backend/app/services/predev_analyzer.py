import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.entities import (
    AnalysisStage,
    Derivation,
    EffectiveRequirementField,
    EffectiveRequirementSnapshot,
    NodeStatus,
    Project,
    Requirement,
    RiskItem,
    RiskValidity,
    RuleNode,
    SnapshotStatus,
)
from app.services.effective_requirement_service import get_latest_snapshot
from app.services.evidence_service import get_relevant_evidence
from app.services.llm_client import LLMClient
from app.services.product_doc_service import get_relevant_chunks
from app.services.prompts.predev_analyzer import (
    PREDEV_ANALYSIS_SYSTEM_PROMPT,
    PREDEV_ANALYSIS_USER_TEMPLATE,
    PREDEV_ANALYSIS_USER_TEMPLATE_NO_PRODUCT,
)
from app.services.requirement_module_analyzer import analyze_requirement_modules
from app.services.risk_service import save_risks_to_ledger

logger = logging.getLogger(__name__)

_VALID_FIELD_KEYS = {
    "goal", "main_flow", "preconditions", "state_changes", "exceptions",
    "constraints", "performance", "compatibility", "integration",
    "rollout_strategy", "other",
}
_VALID_DERIVATIONS = {d.value for d in Derivation}


def analyze_for_predev(
    db: Session,
    requirement_id: int,
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run pre-dev analysis for a requirement.

    Reads the latest review snapshot, current rule tree, and product
    evidence/chunks to produce a pre_dev snapshot with conflict detection
    and enriched risk items.

    Returns a dict with keys: snapshot, risks, conflicts, matched_evidence.
    """
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    base_snapshot = _get_latest_base_snapshot(db, requirement_id)
    if not base_snapshot:
        raise ValueError(
            "no review snapshot found – run review analysis first"
        )

    nodes = (
        db.query(RuleNode)
        .filter(
            RuleNode.requirement_id == requirement_id,
            RuleNode.status != NodeStatus.deleted,
        )
        .all()
    )
    if not nodes:
        raise ValueError("no rule tree nodes found for this requirement")

    rule_tree_text = _format_rule_tree(nodes)
    snapshot_summary, snapshot_fields_text = _format_snapshot(base_snapshot)
    product_context = _build_predev_product_context(db, requirement, llm_client)

    llm_result = _call_llm_for_predev(
        snapshot_summary=snapshot_summary,
        snapshot_fields=snapshot_fields_text,
        rule_tree_text=rule_tree_text,
        product_context=product_context,
        llm_client=llm_client,
    )

    base_snapshot.status = SnapshotStatus.superseded
    db.flush()

    new_snapshot = EffectiveRequirementSnapshot(
        requirement_id=requirement_id,
        stage=AnalysisStage.pre_dev,
        status=SnapshotStatus.draft,
        based_on_input_ids=base_snapshot.based_on_input_ids,
        summary=llm_result.get("summary", ""),
        base_snapshot_id=base_snapshot.id,
    )
    db.add(new_snapshot)
    db.flush()

    fields_data = llm_result.get("fields", [])
    if not fields_data:
        fields_data = _copy_review_fields(base_snapshot)

    for idx, fd in enumerate(fields_data):
        field_key = fd.get("field_key", "other")
        if field_key not in _VALID_FIELD_KEYS:
            field_key = "other"

        derivation_str = fd.get("derivation")
        derivation_val = (
            Derivation(derivation_str) if derivation_str in _VALID_DERIVATIONS else None
        )

        field = EffectiveRequirementField(
            snapshot_id=new_snapshot.id,
            field_key=field_key,
            value=fd.get("value", ""),
            derivation=derivation_val,
            confidence=fd.get("confidence"),
            source_refs=fd.get("source_refs", ""),
            notes=fd.get("notes"),
            sort_order=idx,
        )
        db.add(field)

    db.flush()

    node_id_set = {n.id for n in nodes}
    raw_risks = llm_result.get("risks", [])

    for r in raw_risks:
        nid = r.get("related_node_id")
        if nid and nid not in node_id_set:
            r["related_node_id"] = None

    _handle_risk_ledger_transitions(
        db=db,
        requirement_id=requirement_id,
        new_raw_risks=raw_risks,
        conflicts=llm_result.get("conflicts", []),
    )

    risk_items = save_risks_to_ledger(
        db=db,
        requirement_id=requirement_id,
        raw_risks=raw_risks,
        valid_node_ids=node_id_set,
        analysis_stage="pre_dev",
        origin_snapshot_id=new_snapshot.id,
        mark_unseen_superseded=False,
    )

    db.commit()
    db.refresh(new_snapshot)

    return {
        "snapshot": new_snapshot,
        "risks": risk_items,
        "conflicts": llm_result.get("conflicts", []),
        "matched_evidence": llm_result.get("matched_evidence", []),
    }


def _format_rule_tree(nodes: List[RuleNode]) -> str:
    lines = []
    for n in nodes:
        ntype = n.node_type.value if hasattr(n.node_type, "value") else n.node_type
        parent_part = " (parent: {0})".format(n.parent_id) if n.parent_id else ""
        lines.append("- [{id}] ({type}){parent} {content}".format(
            id=n.id,
            type=ntype,
            parent=parent_part,
            content=n.content,
        ))
    return "\n".join(lines) if lines else "(empty rule tree)"


def _get_latest_base_snapshot(
    db: Session,
    requirement_id: int,
) -> Optional[EffectiveRequirementSnapshot]:
    return (
        db.query(EffectiveRequirementSnapshot)
        .filter(
            EffectiveRequirementSnapshot.requirement_id == requirement_id,
            EffectiveRequirementSnapshot.stage.in_([AnalysisStage.review, AnalysisStage.pre_dev]),
        )
        .order_by(EffectiveRequirementSnapshot.created_at.desc(), EffectiveRequirementSnapshot.id.desc())
        .first()
    )


def _format_snapshot(snapshot: EffectiveRequirementSnapshot) -> tuple:
    summary = snapshot.summary or "(no summary)"

    fields = sorted(snapshot.fields, key=lambda f: f.sort_order)
    field_lines = []
    for f in fields:
        derivation = f.derivation.value if hasattr(f.derivation, "value") and f.derivation else "unknown"
        confidence = f.confidence if f.confidence is not None else "N/A"
        field_lines.append(
            "- [{key}] (derivation={deriv}, confidence={conf}) {value}".format(
                key=f.field_key,
                deriv=derivation,
                conf=confidence,
                value=f.value or "(empty)",
            )
        )
        if f.notes:
            field_lines.append("  注：{0}".format(f.notes))

    fields_text = "\n".join(field_lines) if field_lines else "(no fields)"
    return summary, fields_text


def _copy_review_fields(snapshot: EffectiveRequirementSnapshot) -> List[Dict[str, Any]]:
    """Copy fields from review snapshot as fallback when LLM returns none."""
    result = []
    for f in sorted(snapshot.fields, key=lambda x: x.sort_order):
        derivation = f.derivation.value if hasattr(f.derivation, "value") and f.derivation else None
        result.append({
            "field_key": f.field_key,
            "value": f.value,
            "derivation": derivation,
            "confidence": f.confidence,
            "source_refs": f.source_refs,
            "notes": f.notes,
        })
    return result


def _build_predev_product_context(
    db: Session,
    requirement: Requirement,
    llm_client: Optional[Any] = None,
) -> Optional[str]:
    project = db.query(Project).filter(Project.id == requirement.project_id).first()
    if not project or not project.product_code:
        return None

    module_result = analyze_requirement_modules(db, requirement, llm_client=llm_client)
    matched = module_result.matched_modules if module_result else None
    related = module_result.related_modules if module_result else None

    sections: List[str] = []

    evidence_blocks = get_relevant_evidence(
        db,
        project.product_code,
        requirement.raw_text,
        module_names=matched,
        max_items=8,
    )
    if evidence_blocks:
        ev_lines = []
        for eb in evidence_blocks:
            etype = eb.evidence_type.value if hasattr(eb.evidence_type, "value") else eb.evidence_type
            status = eb.status.value if hasattr(eb.status, "value") else eb.status
            ev_lines.append("- [{type}][{status}] ({module}) {stmt}".format(
                type=etype,
                status=status,
                module=eb.module_name or "unknown",
                stmt=eb.statement,
            ))
        sections.append("【结构化产品证据】\n" + "\n".join(ev_lines))

    chunks = get_relevant_chunks(
        db,
        project.product_code,
        requirement.raw_text,
        max_chunks=4,
        matched_modules=matched,
        related_modules=related,
    )
    if chunks:
        for chunk in chunks:
            sections.append("### {title}\n{content}".format(
                title=chunk.title, content=chunk.content,
            ))

    return "\n\n".join(sections) if sections else None


def _handle_risk_ledger_transitions(
    db: Session,
    requirement_id: int,
    new_raw_risks: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
) -> None:
    """Handle pre_dev specific risk validity transitions.

    - Existing active risks that appear in a conflict as "more severe" get
      reopened (if previously resolved/superseded).
    - Existing resolved risks whose underlying conflict is confirmed
      still open get reopened.
    """
    existing_risks = (
        db.query(RiskItem)
        .filter(RiskItem.requirement_id == requirement_id)
        .all()
    )
    if not existing_risks or not conflicts:
        return

    conflict_descriptions = set()
    for c in conflicts:
        desc = c.get("description", "")
        if desc:
            conflict_descriptions.add(desc.lower())

    now = datetime.utcnow()
    for risk in existing_risks:
        validity = risk.validity.value if hasattr(risk.validity, "value") else risk.validity
        if validity in (RiskValidity.resolved.value, RiskValidity.superseded.value):
            risk_desc_lower = risk.description.lower()
            for cd in conflict_descriptions:
                if _text_overlap(risk_desc_lower, cd) > 0.3:
                    risk.validity = RiskValidity.reopened
                    risk.last_analysis_at = now
                    break


def _text_overlap(a: str, b: str) -> float:
    """Compute simple character-bigram Jaccard overlap between two strings."""
    if not a or not b:
        return 0.0
    bigrams_a = {a[i:i + 2] for i in range(len(a) - 1)}
    bigrams_b = {b[i:i + 2] for i in range(len(b) - 1)}
    if not bigrams_a or not bigrams_b:
        return 0.0
    intersection = len(bigrams_a & bigrams_b)
    union = len(bigrams_a | bigrams_b)
    return intersection / union if union > 0 else 0.0


def _call_llm_for_predev(
    snapshot_summary: str,
    snapshot_fields: str,
    rule_tree_text: str,
    product_context: Optional[str],
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider != "llm":
        return _mock_predev_analysis(
            rule_tree_text,
            has_product_context=bool(product_context),
        )

    try:
        llm = llm_client or LLMClient()
        if product_context:
            user_prompt = PREDEV_ANALYSIS_USER_TEMPLATE.format(
                snapshot_summary=snapshot_summary,
                snapshot_fields=snapshot_fields,
                rule_tree_text=rule_tree_text,
                product_context=product_context,
            )
        else:
            user_prompt = PREDEV_ANALYSIS_USER_TEMPLATE_NO_PRODUCT.format(
                snapshot_summary=snapshot_summary,
                snapshot_fields=snapshot_fields,
                rule_tree_text=rule_tree_text,
            )
        payload = llm.chat_with_json(
            system_prompt=PREDEV_ANALYSIS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return _parse_predev_payload(payload)
    except Exception as exc:
        logger.warning(
            "Pre-dev analysis LLM failed (%s: %s), returning empty result",
            type(exc).__name__, exc,
        )
        return _empty_predev_analysis()


def _parse_predev_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return _empty_predev_analysis()

    summary = str(payload.get("summary", ""))

    matched_evidence = payload.get("matched_evidence", [])
    if not isinstance(matched_evidence, list):
        matched_evidence = []
    parsed_evidence = []
    for me in matched_evidence:
        if not isinstance(me, dict):
            continue
        parsed_evidence.append({
            "evidence_statement": str(me.get("evidence_statement", "")),
            "related_field_key": str(me.get("related_field_key", "")),
            "match_type": str(me.get("match_type", "consistent")),
        })

    conflicts = payload.get("conflicts", [])
    if not isinstance(conflicts, list):
        conflicts = []
    parsed_conflicts = []
    for c in conflicts:
        if not isinstance(c, dict):
            continue
        parsed_conflicts.append({
            "conflict_type": str(c.get("conflict_type", "")),
            "description": str(c.get("description", "")),
            "source_a": str(c.get("source_a", "")),
            "source_b": str(c.get("source_b", "")),
        })

    fields = payload.get("fields", [])
    if not isinstance(fields, list):
        fields = []
    parsed_fields = []
    for f in fields:
        if not isinstance(f, dict):
            continue
        parsed_fields.append({
            "field_key": str(f.get("field_key", "other")),
            "value": str(f.get("value", "")),
            "derivation": str(f.get("derivation", "inferred")),
            "confidence": f.get("confidence"),
            "source_refs": str(f.get("source_refs", "")),
            "notes": f.get("notes"),
        })

    risks = payload.get("risks", [])
    if not isinstance(risks, list):
        risks = []
    parsed_risks = []
    for r in risks:
        if not isinstance(r, dict):
            continue
        desc = str(r.get("description", ""))
        if not desc:
            continue
        parsed_risks.append({
            "category": str(r.get("category", "flow_gap")),
            "risk_level": str(r.get("risk_level", "medium")),
            "description": desc,
            "suggestion": str(r.get("suggestion", "")),
            "risk_source": (
                "product_knowledge" if r.get("category") == "product_knowledge"
                else "rule_tree"
            ),
            "related_node_id": r.get("related_node_id"),
        })

    return {
        "summary": summary,
        "matched_evidence": parsed_evidence,
        "conflicts": parsed_conflicts,
        "fields": parsed_fields,
        "risks": parsed_risks,
    }


def _empty_predev_analysis() -> Dict[str, Any]:
    return {
        "summary": "",
        "matched_evidence": [],
        "conflicts": [],
        "fields": [],
        "risks": [],
    }


def _mock_predev_analysis(
    rule_tree_text: str,
    has_product_context: bool = False,
) -> Dict[str, Any]:
    fields = [
        {
            "field_key": "goal",
            "value": "实现需求描述中的核心功能",
            "derivation": "explicit",
            "confidence": 0.9,
            "source_refs": "review 快照 + 规则树验证",
            "notes": None,
        },
        {
            "field_key": "main_flow",
            "value": "用户执行需求描述中的主要操作流程",
            "derivation": "explicit",
            "confidence": 0.85,
            "source_refs": "review 快照 + 规则树验证",
            "notes": "规则树已覆盖主流程",
        },
        {
            "field_key": "exceptions",
            "value": "规则树中发现异常分支，但需求快照中未提及具体异常处理方式",
            "derivation": "contradicted",
            "confidence": 0.4,
            "source_refs": "规则树异常节点 vs review 快照",
            "notes": "规则树包含异常分支但需求未明确处理策略",
        },
        {
            "field_key": "preconditions",
            "value": "需求未明确前置条件，规则树也未设置前置校验节点",
            "derivation": "missing",
            "confidence": 0.0,
            "source_refs": "规则树 + review 快照均未提及",
            "notes": "建议补充前置条件",
        },
    ]

    matched_evidence = []
    conflicts = [
        {
            "conflict_type": "rule_vs_requirement",
            "description": "规则树包含异常处理分支，但需求快照未定义异常场景的具体处理方式",
            "source_a": "规则树异常节点",
            "source_b": "需求快照 exceptions 字段缺失",
        },
    ]

    risks = [
        {
            "category": "flow_gap",
            "risk_level": "high",
            "description": "规则树中存在异常处理分支，但需求未说明失败时的回退路径，可能导致实现与预期不一致",
            "suggestion": "与产品确认异常场景的处理策略，同步更新需求和规则树",
            "risk_source": "rule_tree",
        },
        {
            "category": "input_validation",
            "risk_level": "medium",
            "description": "规则树中的条件节点校验逻辑与需求描述的验证规则可能存在差异",
            "suggestion": "逐一核对规则树条件节点的校验逻辑是否与需求一致",
            "risk_source": "rule_tree",
        },
    ]

    if has_product_context:
        matched_evidence.append({
            "evidence_statement": "产品文档中存在相关模块的状态流转规则",
            "related_field_key": "state_changes",
            "match_type": "gap",
        })
        conflicts.append({
            "conflict_type": "evidence_vs_requirement",
            "description": "产品证据显示该模块有状态流转约束，但需求快照未提及状态变更规则",
            "source_a": "产品证据：状态流转规则",
            "source_b": "需求快照中 state_changes 字段缺失",
        })
        risks.append({
            "category": "product_knowledge",
            "risk_level": "high",
            "description": "产品证据显示该模块存在状态流转约束，需求和规则树均未涉及，可能导致实现遗漏关键状态校验",
            "suggestion": "核对产品文档中的状态流转规则，将相关约束补充到需求和规则树中",
            "risk_source": "product_knowledge",
        })

    return {
        "summary": "开发前分析发现规则树与需求快照在异常处理方面存在不一致，建议补充异常场景定义。",
        "matched_evidence": matched_evidence,
        "conflicts": conflicts,
        "fields": fields,
        "risks": risks,
    }
