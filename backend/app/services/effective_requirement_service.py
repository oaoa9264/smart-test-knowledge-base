import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    AnalysisStage,
    Derivation,
    EffectiveRequirementField,
    EffectiveRequirementSnapshot,
    InputType,
    Project,
    Requirement,
    RequirementInput,
    SnapshotStatus,
)
from app.services.llm_client import LLMClient
from app.services.product_doc_service import get_relevant_chunks
from app.services.prompts.effective_requirement import (
    REVIEW_ANALYSIS_SYSTEM_PROMPT,
    REVIEW_ANALYSIS_USER_TEMPLATE,
    REVIEW_ANALYSIS_USER_TEMPLATE_NO_PRODUCT,
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


class NoSnapshotError(ValueError):
    pass


class StaleSnapshotError(ValueError):
    pass


def compute_basis_hash(requirement: Requirement, inputs: List[RequirementInput]) -> str:
    serialized_inputs = []
    for inp in sorted(
        inputs,
        key=lambda item: (
            item.created_at.isoformat() if getattr(item, "created_at", None) else "",
            getattr(item, "id", 0) or 0,
        ),
    ):
        input_type = inp.input_type.value if hasattr(inp.input_type, "value") else inp.input_type
        serialized_inputs.append({
            "input_type": input_type,
            "content": inp.content or "",
            "source_label": inp.source_label or "",
        })

    payload = {
        "raw_text": requirement.raw_text or "",
        "inputs": serialized_inputs,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_snapshot_stale(
    requirement: Requirement,
    inputs: List[RequirementInput],
    snapshot: EffectiveRequirementSnapshot,
) -> bool:
    if not snapshot.basis_hash:
        return True
    return compute_basis_hash(requirement, inputs) != snapshot.basis_hash


def list_requirement_inputs(
    db: Session,
    requirement_id: int,
) -> List[RequirementInput]:
    return (
        db.query(RequirementInput)
        .filter(RequirementInput.requirement_id == requirement_id)
        .order_by(RequirementInput.created_at.asc(), RequirementInput.id.asc())
        .all()
    )


def annotate_snapshot_freshness(
    db: Session,
    snapshot: Optional[EffectiveRequirementSnapshot],
    requirement: Optional[Requirement] = None,
    inputs: Optional[List[RequirementInput]] = None,
) -> Optional[EffectiveRequirementSnapshot]:
    if snapshot is None:
        return None

    current_requirement = requirement or (
        db.query(Requirement).filter(Requirement.id == snapshot.requirement_id).first()
    )
    current_inputs = inputs if inputs is not None else list_requirement_inputs(db, snapshot.requirement_id)
    snapshot.is_stale = True if current_requirement is None else is_snapshot_stale(
        current_requirement,
        current_inputs,
        snapshot,
    )
    return snapshot


def generate_review_snapshot(
    db: Session,
    requirement_id: int,
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Generate a review-stage effective requirement snapshot.

    This analyzer works WITHOUT a rule tree.  It takes raw requirement
    text + formal inputs + chunk-level product context and produces
    structured fields, initial risks, and clarification hints.

    Returns a dict with keys: snapshot, risks, clarification_hints.
    """
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    inputs = list_requirement_inputs(db, requirement_id)

    formal_inputs_text = _format_inputs(inputs)
    product_context = _build_review_product_context(db, requirement, llm_client)

    llm_result = _call_llm_for_review(
        raw_text=requirement.raw_text,
        formal_inputs=formal_inputs_text,
        product_context=product_context,
        llm_client=llm_client,
    )

    (
        db.query(EffectiveRequirementSnapshot)
        .filter(
            EffectiveRequirementSnapshot.requirement_id == requirement_id,
            EffectiveRequirementSnapshot.stage == AnalysisStage.review,
            EffectiveRequirementSnapshot.status != SnapshotStatus.superseded,
        )
        .update({"status": SnapshotStatus.superseded}, synchronize_session=False)
    )

    input_ids = ",".join(str(inp.id) for inp in inputs) if inputs else ""
    basis_hash = compute_basis_hash(requirement, inputs)

    snapshot = EffectiveRequirementSnapshot(
        requirement_id=requirement_id,
        stage=AnalysisStage.review,
        status=SnapshotStatus.draft,
        based_on_input_ids=input_ids or None,
        basis_hash=basis_hash,
        summary=llm_result.get("summary", ""),
    )
    db.add(snapshot)
    db.flush()

    fields_data = llm_result.get("fields", [])
    for idx, fd in enumerate(fields_data):
        field_key = fd.get("field_key", "other")
        if field_key not in _VALID_FIELD_KEYS:
            field_key = "other"

        derivation_str = fd.get("derivation")
        derivation_val = Derivation(derivation_str) if derivation_str in _VALID_DERIVATIONS else None

        field = EffectiveRequirementField(
            snapshot_id=snapshot.id,
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

    raw_risks = llm_result.get("risks", [])
    risk_items = save_risks_to_ledger(
        db=db,
        requirement_id=requirement_id,
        raw_risks=raw_risks,
        analysis_stage="review",
        origin_snapshot_id=snapshot.id,
        mark_unseen_superseded=True,
    )

    db.commit()
    db.refresh(snapshot)

    clarification_hints = _extract_clarification_hints(fields_data)

    return {
        "snapshot": snapshot,
        "risks": risk_items,
        "clarification_hints": clarification_hints,
    }


def get_latest_snapshot(
    db: Session,
    requirement_id: int,
    stage: Optional[str] = None,
) -> Optional[EffectiveRequirementSnapshot]:
    query = (
        db.query(EffectiveRequirementSnapshot)
        .filter(EffectiveRequirementSnapshot.requirement_id == requirement_id)
    )
    if stage:
        query = query.filter(EffectiveRequirementSnapshot.stage == AnalysisStage(stage))
    return query.order_by(EffectiveRequirementSnapshot.created_at.desc()).first()


def list_snapshots(
    db: Session,
    requirement_id: int,
) -> List[EffectiveRequirementSnapshot]:
    return (
        db.query(EffectiveRequirementSnapshot)
        .filter(EffectiveRequirementSnapshot.requirement_id == requirement_id)
        .order_by(EffectiveRequirementSnapshot.created_at.desc())
        .all()
    )


def _format_inputs(inputs: List[RequirementInput]) -> str:
    if not inputs:
        return "（暂无正式补充输入）"
    lines = []
    for inp in inputs:
        itype = inp.input_type.value if hasattr(inp.input_type, "value") else inp.input_type
        label = inp.source_label or ""
        label_part = "（来源：{0}）".format(label) if label else ""
        lines.append("- [{type}]{label} {content}".format(
            type=itype,
            label=label_part,
            content=inp.content,
        ))
    return "\n".join(lines)


def _build_review_product_context(
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


def _call_llm_for_review(
    raw_text: str,
    formal_inputs: str,
    product_context: Optional[str],
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider != "llm":
        return _mock_review_analysis(raw_text, has_product_context=bool(product_context))

    try:
        llm = llm_client or LLMClient()
        if product_context:
            user_prompt = REVIEW_ANALYSIS_USER_TEMPLATE.format(
                raw_text=raw_text,
                formal_inputs=formal_inputs,
                product_context=product_context,
            )
        else:
            user_prompt = REVIEW_ANALYSIS_USER_TEMPLATE_NO_PRODUCT.format(
                raw_text=raw_text,
                formal_inputs=formal_inputs,
            )
        payload = llm.chat_with_json(
            system_prompt=REVIEW_ANALYSIS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return _parse_review_payload(payload)
    except Exception as exc:
        logger.warning(
            "Review analysis LLM failed (%s: %s), returning empty result",
            type(exc).__name__, exc,
        )
        return _empty_review_analysis()


def _parse_review_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return _empty_review_analysis()

    summary = str(payload.get("summary", ""))
    fields = payload.get("fields", [])
    if not isinstance(fields, list):
        fields = []
    risks = payload.get("risks", [])
    if not isinstance(risks, list):
        risks = []

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
            "risk_source": "product_knowledge" if r.get("category") == "product_knowledge" else "rule_tree",
        })

    return {"summary": summary, "fields": parsed_fields, "risks": parsed_risks}


def _empty_review_analysis() -> Dict[str, Any]:
    return {"summary": "", "fields": [], "risks": []}


def _mock_review_analysis(raw_text: str, has_product_context: bool = False) -> Dict[str, Any]:
    fields = [
        {
            "field_key": "goal",
            "value": "实现需求描述中的核心功能",
            "derivation": "explicit",
            "confidence": 0.9,
            "source_refs": "原始需求文本",
            "notes": None,
        },
        {
            "field_key": "main_flow",
            "value": "用户执行需求描述中的主要操作流程",
            "derivation": "explicit",
            "confidence": 0.8,
            "source_refs": "原始需求文本",
            "notes": None,
        },
        {
            "field_key": "exceptions",
            "value": "需求未提及异常流程的处理方式",
            "derivation": "missing",
            "confidence": 0.0,
            "source_refs": "原始需求文本中未提及",
            "notes": "建议补充异常场景说明",
        },
        {
            "field_key": "preconditions",
            "value": "需求未明确前置条件",
            "derivation": "missing",
            "confidence": 0.0,
            "source_refs": "原始需求文本中未提及",
            "notes": "建议明确操作的前置条件",
        },
    ]

    risks = [
        {
            "category": "flow_gap",
            "risk_level": "high",
            "description": "需求未说明操作失败时的回退路径，可能导致用户卡在中间状态",
            "suggestion": "补充失败场景的处理流程说明",
            "risk_source": "rule_tree",
        },
        {
            "category": "input_validation",
            "risk_level": "medium",
            "description": "未明确输入为空时的处理逻辑",
            "suggestion": "建议增加空值校验，给出友好提示",
            "risk_source": "rule_tree",
        },
    ]

    if has_product_context:
        risks.append({
            "category": "product_knowledge",
            "risk_level": "high",
            "description": "需求未提及现有产品流程中已有的状态校验约束，可能与现有产品逻辑冲突",
            "suggestion": "核对现有产品文档中的状态流转规则，确认需求是否需要适配",
            "risk_source": "product_knowledge",
        })

    return {
        "summary": "需求描述了核心功能，但缺少异常流程和前置条件的说明。",
        "fields": fields,
        "risks": risks,
    }


def _extract_clarification_hints(fields: List[Dict[str, Any]]) -> List[str]:
    hints = []
    for f in fields:
        derivation = f.get("derivation", "")
        if derivation == "missing":
            key = f.get("field_key", "")
            value = f.get("value", "")
            hints.append("字段「{key}」缺失：{value}".format(key=key, value=value))
        elif derivation == "contradicted":
            key = f.get("field_key", "")
            notes = f.get("notes", "") or f.get("value", "")
            hints.append("字段「{key}」存在矛盾：{notes}".format(key=key, notes=notes))
    return hints
