import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.entities import (
    AnalysisStage,
    DocUpdateStatus,
    EffectiveRequirementSnapshot,
    NodeStatus,
    ProductDocUpdate,
    Project,
    Requirement,
    RiskDecision,
    RiskItem,
    RiskValidity,
    RuleNode,
    SnapshotStatus,
)
from app.services.effective_requirement_service import get_latest_snapshot
from app.services.evidence_service import get_relevant_evidence
from app.services.llm_client import LLMClient
from app.services.product_doc_service import get_relevant_chunks
from app.services.prompts.prerelease_auditor import (
    PRERELEASE_AUDIT_SYSTEM_PROMPT,
    PRERELEASE_AUDIT_USER_TEMPLATE,
    PRERELEASE_AUDIT_USER_TEMPLATE_NO_PRODUCT,
)
from app.services.requirement_module_analyzer import analyze_requirement_modules

logger = logging.getLogger(__name__)


def audit_for_prerelease(
    db: Session,
    requirement_id: int,
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run pre-release audit for a requirement.

    Reads the latest snapshot, current rule tree, risk ledger, and applied
    doc updates to produce a closure audit.  Does NOT produce new risks.

    Returns a dict with keys:
        blocking_risks, reopened_risks, resolved_risks,
        closure_summary, audit_notes.
    """
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    latest_snapshot = _get_best_snapshot(db, requirement_id)
    if not latest_snapshot:
        raise ValueError(
            "no effective requirement snapshot found – run review or pre-dev analysis first"
        )

    nodes = (
        db.query(RuleNode)
        .filter(
            RuleNode.requirement_id == requirement_id,
            RuleNode.status != NodeStatus.deleted,
        )
        .all()
    )

    existing_risks = (
        db.query(RiskItem)
        .filter(RiskItem.requirement_id == requirement_id)
        .order_by(RiskItem.created_at.asc())
        .all()
    )
    if not existing_risks:
        return {
            "blocking_risks": [],
            "reopened_risks": [],
            "resolved_risks": [],
            "closure_summary": "该需求尚无风险记录，无审计内容。",
            "audit_notes": [],
        }

    rule_tree_text = _format_rule_tree(nodes)
    snapshot_summary, snapshot_fields_text = _format_snapshot(latest_snapshot)
    risk_ledger_text = _format_risk_ledger(existing_risks)
    doc_updates_text = _format_doc_updates(db, requirement_id)
    product_context = _build_audit_product_context(db, requirement, llm_client)

    llm_result = _call_llm_for_audit(
        snapshot_summary=snapshot_summary,
        snapshot_fields=snapshot_fields_text,
        rule_tree_text=rule_tree_text,
        risk_ledger_text=risk_ledger_text,
        doc_updates_text=doc_updates_text,
        product_context=product_context,
        llm_client=llm_client,
    )

    risk_id_set = {r.id for r in existing_risks}
    _apply_audit_transitions(
        db=db,
        existing_risks=existing_risks,
        risk_id_set=risk_id_set,
        reopened=llm_result.get("reopened_risks", []),
        resolved=llm_result.get("resolved_risks", []),
    )

    db.commit()

    return {
        "blocking_risks": llm_result.get("blocking_risks", []),
        "reopened_risks": llm_result.get("reopened_risks", []),
        "resolved_risks": llm_result.get("resolved_risks", []),
        "closure_summary": llm_result.get("closure_summary", ""),
        "audit_notes": llm_result.get("audit_notes", []),
    }


def _get_best_snapshot(
    db: Session, requirement_id: int,
) -> Optional[EffectiveRequirementSnapshot]:
    """Return the latest non-superseded effective snapshot used for audit."""
    snap = (
        db.query(EffectiveRequirementSnapshot)
        .filter(
            EffectiveRequirementSnapshot.requirement_id == requirement_id,
            EffectiveRequirementSnapshot.stage.in_([AnalysisStage.review, AnalysisStage.pre_dev]),
            EffectiveRequirementSnapshot.status != SnapshotStatus.superseded,
        )
        .order_by(EffectiveRequirementSnapshot.created_at.desc(), EffectiveRequirementSnapshot.id.desc())
        .first()
    )
    if snap:
        return snap

    return (
        db.query(EffectiveRequirementSnapshot)
        .filter(
            EffectiveRequirementSnapshot.requirement_id == requirement_id,
            EffectiveRequirementSnapshot.stage.in_([AnalysisStage.review, AnalysisStage.pre_dev]),
        )
        .order_by(EffectiveRequirementSnapshot.created_at.desc(), EffectiveRequirementSnapshot.id.desc())
        .first()
    )


def _format_rule_tree(nodes: List[RuleNode]) -> str:
    if not nodes:
        return "（暂无规则树）"
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
    return "\n".join(lines)


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


def _format_risk_ledger(risks: List[RiskItem]) -> str:
    if not risks:
        return "（暂无风险记录）"
    lines = []
    for r in risks:
        validity = r.validity.value if hasattr(r.validity, "value") and r.validity else "unknown"
        decision = r.decision.value if hasattr(r.decision, "value") and r.decision else "unknown"
        level = r.risk_level.value if hasattr(r.risk_level, "value") else r.risk_level
        category = r.category.value if hasattr(r.category, "value") else r.category
        stage = r.analysis_stage.value if hasattr(r.analysis_stage, "value") and r.analysis_stage else "N/A"
        node_part = " node={0}".format(r.related_node_id) if r.related_node_id else ""
        lines.append(
            "- [{id}] validity={validity} decision={decision} [{level}][{cat}] "
            "(stage={stage}){node} {desc}".format(
                id=r.id,
                validity=validity,
                decision=decision,
                level=level,
                cat=category,
                stage=stage,
                node=node_part,
                desc=r.description,
            )
        )
        if r.suggestion:
            lines.append("  建议：{0}".format(r.suggestion))
        if r.clarification_text:
            lines.append("  澄清：{0}".format(r.clarification_text))
    return "\n".join(lines)


def _format_doc_updates(db: Session, requirement_id: int) -> str:
    """Collect applied doc updates linked to risks of this requirement."""
    risk_ids = [
        r.id for r in
        db.query(RiskItem.id).filter(RiskItem.requirement_id == requirement_id).all()
    ]
    if not risk_ids:
        return "（无已应用的文档更新）"

    updates = (
        db.query(ProductDocUpdate)
        .filter(
            ProductDocUpdate.risk_item_id.in_(risk_ids),
            ProductDocUpdate.status == DocUpdateStatus.approved,
        )
        .all()
    )
    if not updates:
        return "（无已应用的文档更新）"

    lines = []
    for u in updates:
        lines.append("- [update-{id}] risk={risk_id} 原内容片段：{orig} -> 更新内容：{suggested}".format(
            id=u.id,
            risk_id=u.risk_item_id or "N/A",
            orig=(u.original_content or "")[:80],
            suggested=(u.suggested_content or "")[:80],
        ))
    return "\n".join(lines)


def _build_audit_product_context(
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


def _apply_audit_transitions(
    db: Session,
    existing_risks: List[RiskItem],
    risk_id_set: Set[str],
    reopened: List[Dict[str, Any]],
    resolved: List[Dict[str, Any]],
) -> None:
    """Apply validity transitions based on audit results."""
    now = datetime.utcnow()
    risk_map = {r.id: r for r in existing_risks}

    for item in reopened:
        rid = item.get("risk_id", "")
        if rid not in risk_id_set:
            continue
        risk = risk_map.get(rid)
        if not risk:
            continue
        validity = risk.validity.value if hasattr(risk.validity, "value") else risk.validity
        if validity in (RiskValidity.resolved.value, RiskValidity.superseded.value):
            risk.validity = RiskValidity.reopened
            risk.analysis_stage = AnalysisStage.pre_release
            risk.last_analysis_at = now

    for item in resolved:
        rid = item.get("risk_id", "")
        if rid not in risk_id_set:
            continue
        risk = risk_map.get(rid)
        if not risk:
            continue
        validity = risk.validity.value if hasattr(risk.validity, "value") else risk.validity
        if validity in (RiskValidity.active.value, RiskValidity.reopened.value):
            risk.validity = RiskValidity.resolved
            risk.analysis_stage = AnalysisStage.pre_release
            risk.last_analysis_at = now


def _call_llm_for_audit(
    snapshot_summary: str,
    snapshot_fields: str,
    rule_tree_text: str,
    risk_ledger_text: str,
    doc_updates_text: str,
    product_context: Optional[str],
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider != "llm":
        return _mock_prerelease_audit(
            risk_ledger_text,
            has_product_context=bool(product_context),
        )

    try:
        llm = llm_client or LLMClient()
        if product_context:
            user_prompt = PRERELEASE_AUDIT_USER_TEMPLATE.format(
                snapshot_summary=snapshot_summary,
                snapshot_fields=snapshot_fields,
                rule_tree_text=rule_tree_text,
                risk_ledger_text=risk_ledger_text,
                doc_updates_text=doc_updates_text,
                product_context=product_context,
            )
        else:
            user_prompt = PRERELEASE_AUDIT_USER_TEMPLATE_NO_PRODUCT.format(
                snapshot_summary=snapshot_summary,
                snapshot_fields=snapshot_fields,
                rule_tree_text=rule_tree_text,
                risk_ledger_text=risk_ledger_text,
                doc_updates_text=doc_updates_text,
            )
        payload = llm.chat_with_json(
            system_prompt=PRERELEASE_AUDIT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return _parse_audit_payload(payload)
    except Exception as exc:
        logger.warning(
            "Pre-release audit LLM failed (%s: %s), returning empty result",
            type(exc).__name__, exc,
        )
        return _empty_prerelease_audit()


def _parse_audit_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return _empty_prerelease_audit()

    closure_summary = str(payload.get("closure_summary", ""))

    blocking = payload.get("blocking_risks", [])
    if not isinstance(blocking, list):
        blocking = []
    parsed_blocking = []
    for b in blocking:
        if not isinstance(b, dict):
            continue
        parsed_blocking.append({
            "risk_id": str(b.get("risk_id", "")),
            "reason": str(b.get("reason", "")),
            "severity": str(b.get("severity", "high")),
        })

    reopened = payload.get("reopened_risks", [])
    if not isinstance(reopened, list):
        reopened = []
    parsed_reopened = []
    for r in reopened:
        if not isinstance(r, dict):
            continue
        parsed_reopened.append({
            "risk_id": str(r.get("risk_id", "")),
            "reason": str(r.get("reason", "")),
        })

    resolved = payload.get("resolved_risks", [])
    if not isinstance(resolved, list):
        resolved = []
    parsed_resolved = []
    for r in resolved:
        if not isinstance(r, dict):
            continue
        parsed_resolved.append({
            "risk_id": str(r.get("risk_id", "")),
            "reason": str(r.get("reason", "")),
        })

    audit_notes = payload.get("audit_notes", [])
    if not isinstance(audit_notes, list):
        audit_notes = []
    parsed_notes = [str(n) for n in audit_notes if n]

    return {
        "closure_summary": closure_summary,
        "blocking_risks": parsed_blocking,
        "reopened_risks": parsed_reopened,
        "resolved_risks": parsed_resolved,
        "audit_notes": parsed_notes,
    }


def _empty_prerelease_audit() -> Dict[str, Any]:
    return {
        "closure_summary": "",
        "blocking_risks": [],
        "reopened_risks": [],
        "resolved_risks": [],
        "audit_notes": [],
    }


def _mock_prerelease_audit(
    risk_ledger_text: str,
    has_product_context: bool = False,
) -> Dict[str, Any]:
    """Produce a deterministic mock audit result.

    The mock analyses the *risk_ledger_text* to extract real risk IDs so
    that tests can verify the audit correctly references existing risks.
    """
    risk_ids = _extract_risk_ids_from_ledger(risk_ledger_text)

    blocking: List[Dict[str, Any]] = []
    reopened: List[Dict[str, Any]] = []
    resolved: List[Dict[str, Any]] = []

    if len(risk_ids) >= 1:
        blocking.append({
            "risk_id": risk_ids[0],
            "reason": "该风险为 high/critical 且 decision=pending，规则树中缺少覆盖节点",
            "severity": "high",
        })
    if len(risk_ids) >= 2:
        resolved.append({
            "risk_id": risk_ids[1],
            "reason": "规则树中已有对应节点覆盖该风险场景",
        })

    has_blocking = len(blocking) > 0
    closure_summary = (
        "存在 {0} 项阻塞风险，不建议提测。请先处理阻塞项后重新审计。".format(len(blocking))
        if has_blocking
        else "所有风险均已闭环或为低风险，可以提测。"
    )

    audit_notes = ["mock 审计：基于风险账本中的现有风险进行了模拟审计"]
    if has_product_context:
        audit_notes.append("已参考产品证据进行对照审计")

    return {
        "closure_summary": closure_summary,
        "blocking_risks": blocking,
        "reopened_risks": reopened,
        "resolved_risks": resolved,
        "audit_notes": audit_notes,
    }


def _extract_risk_ids_from_ledger(ledger_text: str) -> List[str]:
    """Extract risk IDs from formatted ledger text."""
    import re
    return re.findall(r"\[([a-f0-9-]{36})\]", ledger_text)
