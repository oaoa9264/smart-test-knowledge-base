import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.entities import ClarificationReviewPdfDraft, ClarificationReviewRecord
from app.schemas.clarification_review import ClarificationReviewAnalyzeRequest
from app.services.llm_result_helpers import build_llm_failure_meta, build_llm_success_meta
from app.services.llm_client import LLMClient
from app.services.pdf_draft_service import PdfDraftNotFoundError, get_pdf_draft
from app.services.prompts.clarification_review import (
    CLARIFICATION_REVIEW_USER_TEMPLATE,
    DEFAULT_CLARIFICATION_REVIEW_ROLES,
    PDF_SUPPLEMENT_SECTION,
    build_clarification_review_system_prompt,
)


logger = logging.getLogger(__name__)

PDF_SUPPLEMENT_MAX_CONFLICTS = 10
PDF_SUPPLEMENT_MAX_STRICT_EVIDENCE_CHARS = 2500
PDF_SUPPLEMENT_MAX_INFERENCE_EVIDENCE_CHARS = 1800
PDF_SUPPLEMENT_MAX_VISION_NOTES_CHARS = 2500
PDF_SUPPLEMENT_MAX_FULL_TEXT_CHARS = 8000

PDF_FIELD_LABELS = {
    "requirement_text": "需求原文",
    "current_surface_flow": "当前表面流程",
    "involved_modules": "涉及模块",
    "known_background": "已知背景",
    "unknowns": "我暂时不知道的内容",
}

ROLE_LINE_RE = re.compile(r"^\s*(?:[-*•]\s*)?问\s*(.+?)\s*$")
ROLE_SUFFIX_RE = re.compile(r"[：:；;，。,.\s]+$")
ROLE_ALIAS_MAP = {
    "产品": "产品",
    "产品经理": "产品",
    "产品侧": "产品",
    "pm": "产品",
    "product": "产品",
    "开发": "开发",
    "开发侧": "开发",
    "研发": "开发",
    "研发侧": "开发",
    "dev": "开发",
    "developer": "开发",
    "development": "开发",
    "测试": "测试",
    "测试侧": "测试",
    "qa": "测试",
    "quality assurance": "测试",
    "testing": "测试",
    "运营/业务": "运营/业务",
    "运营业务": "运营/业务",
    "业务/运营": "运营/业务",
    "运营": "运营/业务",
    "业务": "运营/业务",
    "ops": "运营/业务",
    "operation": "运营/业务",
    "operations": "运营/业务",
}

RESULT_VERSION_V2 = 2
INFERRED_SOURCE_TYPES = {"input_text", "llm_inference", "pdf_draft"}
QUESTION_ANSWER_FORMATS = {"table", "flow", "text"}
GAP_TYPES = {"rule_missing", "logic_gap", "boundary_undefined", "data_missing", "process_gap"}
GAP_FALLBACK_TYPE = "logic_gap"
GAP_PRIORITIES = {"P0", "P1", "P2"}


def analyze_clarification_review(
    db: Session,
    payload: ClarificationReviewAnalyzeRequest,
    llm_client: Optional[Any] = None,
) -> ClarificationReviewRecord:
    input_payload = {
        "requirement_text": payload.requirement_text,
        "current_surface_flow": payload.current_surface_flow,
        "involved_modules": payload.involved_modules,
        "known_background": payload.known_background,
        "unknowns": payload.unknowns,
    }
    configured_roles = _extract_configured_roles(payload.rule_text)
    result = _empty_result(configured_roles, result_version=RESULT_VERSION_V2)
    meta = build_llm_failure_meta()

    if _has_any_input(input_payload):
        try:
            llm = llm_client or LLMClient()
            user_prompt = CLARIFICATION_REVIEW_USER_TEMPLATE.format(
                rule_text=payload.rule_text,
                **input_payload,
            )
            draft = _get_valid_pdf_draft_or_none(db, payload.source_draft_id)
            pdf_supplement = _build_pdf_supplement(draft=draft, applied_fields=payload.applied_fields or [])
            if pdf_supplement:
                user_prompt = "{0}\n\n{1}".format(user_prompt, pdf_supplement)
            result = llm.chat_with_json(
                system_prompt=build_clarification_review_system_prompt(configured_roles),
                user_prompt=user_prompt,
            )
            provider = _resolve_provider_from_llm(llm)
            meta = build_llm_success_meta(provider)
        except Exception as exc:
            logger.warning("clarification review llm failed: %s", exc)
            result = _empty_result(configured_roles, result_version=RESULT_VERSION_V2)
            meta = build_llm_failure_meta(str(exc) or None)

    result = _normalize_result(
        result,
        meta,
        configured_roles,
        force_result_version=RESULT_VERSION_V2,
        allow_pdf_source=payload.source_draft_id is not None,
    )
    record = ClarificationReviewRecord(
        input_payload_json=json.dumps(input_payload, ensure_ascii=False),
        rule_text=payload.rule_text,
        result_json=json.dumps(result, ensure_ascii=False),
        llm_status=result["llm_status"],
        llm_provider=result["llm_provider"],
        llm_message=result["llm_message"],
        source_draft_id=payload.source_draft_id,
        source_meta_json=json.dumps(_build_source_meta(db, payload), ensure_ascii=False)
        if payload.source_draft_id is not None
        else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_clarification_review_records(db: Session, limit: int = 20):
    normalized_limit = max(1, min(int(limit or 20), 100))
    return (
        db.query(ClarificationReviewRecord)
        .order_by(ClarificationReviewRecord.created_at.desc(), ClarificationReviewRecord.id.desc())
        .limit(normalized_limit)
        .all()
    )


def get_clarification_review_record(db: Session, record_id: int) -> Optional[ClarificationReviewRecord]:
    return db.query(ClarificationReviewRecord).filter(ClarificationReviewRecord.id == record_id).first()


def delete_clarification_review_record(db: Session, record_id: int) -> bool:
    record = db.query(ClarificationReviewRecord).filter(ClarificationReviewRecord.id == record_id).first()
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True


def normalize_clarification_review_result(result: Any, rule_text: str, allow_pdf_source: bool = False) -> Dict[str, Any]:
    configured_roles = _extract_configured_roles(rule_text)
    force_result_version = RESULT_VERSION_V2 if isinstance(result, dict) and result.get("result_version") == RESULT_VERSION_V2 else None
    return _normalize_result(
        result,
        {
            "llm_status": _extract_meta_field(result, "llm_status"),
            "llm_provider": _extract_meta_field(result, "llm_provider"),
            "llm_message": _extract_meta_field(result, "llm_message"),
        },
        configured_roles,
        force_result_version=force_result_version,
        allow_pdf_source=allow_pdf_source,
    )


def _resolve_provider_from_llm(llm: Any) -> Optional[str]:
    getter = getattr(llm, "get_last_provider", None)
    if not callable(getter):
        return None
    provider = getter(method_name="chat_with_json")
    if not provider:
        return None
    return str(provider).strip().lower() or None


def _extract_meta_field(result: Any, key: str) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    value = result.get(key)
    if value is None:
        return None
    return str(value)


def _has_any_input(input_payload: Dict[str, str]) -> bool:
    return any(str(value or "").strip() for value in input_payload.values())


def _empty_result(configured_roles: Optional[List[str]] = None, result_version: Optional[int] = None) -> Dict[str, Any]:
    roles = list(configured_roles or DEFAULT_CLARIFICATION_REVIEW_ROLES)
    result = {
        "likely_historical_rules": [],
        "missing_critical_rules": [],
        "priority_questions_by_role": {role: [] for role in roles},
        "configured_roles": roles,
        "role_descriptors": [{"key": role, "source": "rule_text"} for role in roles],
        "known_requirement_gaps": [],
        "risk_assumptions": [],
        "summary_markdown": "",
    }
    if result_version == RESULT_VERSION_V2:
        result.update(
            {
                "result_version": RESULT_VERSION_V2,
                "inferred_items": [],
                "assumption_items": [],
            }
        )
    return result


def _normalize_result(
    result: Any,
    meta: Dict[str, Any],
    configured_roles: List[str],
    force_result_version: Optional[int] = None,
    allow_pdf_source: bool = False,
) -> Dict[str, Any]:
    if not isinstance(result, dict):
        result = {}
    if force_result_version == RESULT_VERSION_V2 or _looks_like_v2_result(result):
        normalized = _normalize_v2_result(result, configured_roles, allow_pdf_source=allow_pdf_source)
    else:
        normalized = _normalize_legacy_result(result, configured_roles)
    normalized.update(meta)
    return normalized


def _looks_like_v2_result(result: Dict[str, Any]) -> bool:
    return any(key in result for key in ("result_version", "inferred_items", "assumption_items"))


def _normalize_legacy_result(result: Dict[str, Any], configured_roles: List[str]) -> Dict[str, Any]:
    normalized = _empty_result(configured_roles)
    normalized["likely_historical_rules"] = _normalize_list_of_dicts(result.get("likely_historical_rules"), ("rule", "reason"))
    normalized["missing_critical_rules"] = _normalize_list_of_dicts(
        result.get("missing_critical_rules"),
        ("rule", "why_missing", "impact"),
    )
    normalized["known_requirement_gaps"] = _normalize_gap_items(result.get("known_requirement_gaps"))
    normalized["risk_assumptions"] = _normalize_assumption_items(result.get("risk_assumptions"))
    normalized["priority_questions_by_role"], normalized["role_descriptors"] = _normalize_questions(
        result.get("priority_questions_by_role"),
        configured_roles,
    )
    normalized["configured_roles"] = list(configured_roles)
    normalized["summary_markdown"] = str(result.get("summary_markdown", "") or "")
    return normalized


def _normalize_v2_result(result: Dict[str, Any], configured_roles: List[str], allow_pdf_source: bool) -> Dict[str, Any]:
    normalized = _empty_result(configured_roles, result_version=RESULT_VERSION_V2)
    normalized["priority_questions_by_role"], normalized["role_descriptors"] = _normalize_questions(
        result.get("priority_questions_by_role"),
        configured_roles,
    )
    normalized["configured_roles"] = list(configured_roles)
    normalized["summary_markdown"] = str(result.get("summary_markdown", "") or "")

    legacy_rules = _normalize_list_of_dicts(result.get("likely_historical_rules"), ("rule", "reason"))
    legacy_assumptions = _normalize_assumption_items(result.get("risk_assumptions"))
    legacy_missing_rules = _normalize_list_of_dicts(
        result.get("missing_critical_rules"),
        ("rule", "why_missing", "impact"),
    )
    legacy_gaps = _normalize_gap_items(result.get("known_requirement_gaps"))

    normalized["inferred_items"] = _normalize_inferred_items(result.get("inferred_items"), allow_pdf_source=allow_pdf_source)
    if not normalized["inferred_items"] and legacy_rules:
        normalized["inferred_items"] = [
            {
                "statement": item["rule"],
                "evidence": item["reason"],
                "source_type": "llm_inference",
            }
            for item in legacy_rules
        ]

    normalized["assumption_items"] = _normalize_assumption_items(result.get("assumption_items"))
    if not normalized["assumption_items"] and legacy_assumptions:
        normalized["assumption_items"] = legacy_assumptions

    normalized["known_requirement_gaps"] = _normalize_gap_items(result.get("known_requirement_gaps"))
    if legacy_missing_rules:
        existing_rule_missing = {
            (item["gap"], item["reason"], item["impact"]) for item in normalized["known_requirement_gaps"] if item.get("gap_type") == "rule_missing"
        }
        for item in legacy_missing_rules:
            gap_tuple = (item["rule"], item["why_missing"], item["impact"])
            if gap_tuple in existing_rule_missing:
                continue
            normalized["known_requirement_gaps"].append(
                {
                    "gap": item["rule"],
                    "gap_type": "rule_missing",
                    "reason": item["why_missing"],
                    "impact": item["impact"],
                    "priority": "P1",
                    "blocking_reason": "",
                }
            )

    normalized["known_requirement_gaps"].extend(
        item for item in legacy_gaps if not _gap_exists(normalized["known_requirement_gaps"], item)
    )
    normalized["known_requirement_gaps"] = _rebalance_gap_priorities(normalized["known_requirement_gaps"])

    normalized["likely_historical_rules"] = [
        {"rule": item["statement"], "reason": item["evidence"]} for item in normalized["inferred_items"]
    ]
    normalized["risk_assumptions"] = [
        {"assumption": item["assumption"], "basis": item["basis"], "risk": item["risk"]}
        for item in normalized["assumption_items"]
    ]
    normalized["missing_critical_rules"] = [
        {
            "rule": item["gap"],
            "why_missing": item["reason"],
            "impact": item["impact"],
        }
        for item in normalized["known_requirement_gaps"]
        if item.get("gap_type") == "rule_missing"
    ]
    return normalized


def _normalize_questions(payload: Any, configured_roles: List[str]) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    source = payload if isinstance(payload, dict) else {}
    normalized = {role: [] for role in configured_roles}
    extras: Dict[str, List[Dict[str, str]]] = {}

    for raw_role, raw_items in source.items():
        normalized_role = _normalize_role_name(raw_role)
        items = _normalize_question_items(raw_items)
        if normalized_role in normalized:
            normalized[normalized_role].extend(items)
            continue
        extras.setdefault(normalized_role, []).extend(items)

    ordered = dict(normalized)
    ordered.update(extras)
    role_descriptors = [{"key": role, "source": "rule_text"} for role in configured_roles]
    role_descriptors.extend({"key": role, "source": "llm_extra"} for role in extras.keys())
    return ordered, role_descriptors


def _extract_configured_roles(rule_text: str) -> List[str]:
    roles: List[str] = []
    for line in str(rule_text or "").splitlines():
        match = ROLE_LINE_RE.match(line)
        if not match:
            continue
        role = _normalize_role_name(match.group(1))
        if role and role not in roles:
            roles.append(role)

    if roles:
        return roles

    logger.warning("clarification review role parse failed, fallback to default roles")
    return list(DEFAULT_CLARIFICATION_REVIEW_ROLES)


def _normalize_role_name(value: Any) -> str:
    raw = str(value or "").strip()
    raw = ROLE_SUFFIX_RE.sub("", raw)
    raw = raw.strip().strip("\"'“”‘’`")
    compact = raw.replace(" ", "")
    lower = compact.lower()
    if lower in ROLE_ALIAS_MAP:
        return ROLE_ALIAS_MAP[lower]
    if compact in ROLE_ALIAS_MAP:
        return ROLE_ALIAS_MAP[compact]
    return compact or str(value or "").strip()


def _normalize_list_of_dicts(payload: Any, keys) -> list:
    if not isinstance(payload, list):
        return []
    items = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        items.append({key: str(item.get(key, "") or "") for key in keys})
    return items


def _normalize_question_items(payload: Any) -> List[Dict[str, str]]:
    items = _normalize_list_of_dicts(payload, ("question", "why_ask", "risk_if_unasked", "required_output", "answer_format"))
    for item in items:
        answer_format = str(item.get("answer_format", "") or "").strip()
        item["answer_format"] = answer_format if answer_format in QUESTION_ANSWER_FORMATS else "text"
        item["required_output"] = str(item.get("required_output", "") or "")
    return items


def _normalize_inferred_items(payload: Any, allow_pdf_source: bool) -> List[Dict[str, str]]:
    items = _normalize_list_of_dicts(payload, ("statement", "evidence", "source_type"))
    normalized: List[Dict[str, str]] = []
    for item in items:
        statement = str(item.get("statement", "") or "").strip()
        evidence = str(item.get("evidence", "") or "").strip()
        if not statement and not evidence:
            continue
        source_type = str(item.get("source_type", "") or "").strip()
        if source_type not in INFERRED_SOURCE_TYPES:
            source_type = "llm_inference"
        if source_type == "pdf_draft" and not allow_pdf_source:
            source_type = "llm_inference"
        normalized.append({"statement": statement, "evidence": evidence, "source_type": source_type})
    return normalized


def _normalize_assumption_items(payload: Any) -> List[Dict[str, str]]:
    items = _normalize_list_of_dicts(payload, ("assumption", "basis", "risk"))
    return [
        {
            "assumption": str(item.get("assumption", "") or "").strip(),
            "basis": str(item.get("basis", "") or "").strip(),
            "risk": str(item.get("risk", "") or "").strip(),
        }
        for item in items
        if any(str(item.get(key, "") or "").strip() for key in ("assumption", "basis", "risk"))
    ]


def _normalize_gap_items(payload: Any) -> List[Dict[str, str]]:
    items = _normalize_list_of_dicts(payload, ("gap", "gap_type", "reason", "impact", "priority", "blocking_reason"))
    normalized: List[Dict[str, str]] = []
    for item in items:
        gap = str(item.get("gap", "") or "").strip()
        reason = str(item.get("reason", "") or "").strip()
        impact = str(item.get("impact", "") or "").strip()
        if not gap and not reason and not impact:
            continue
        gap_type = str(item.get("gap_type", "") or "").strip()
        if gap_type not in GAP_TYPES:
            gap_type = GAP_FALLBACK_TYPE
        priority = str(item.get("priority", "") or "").strip()
        if priority not in GAP_PRIORITIES:
            priority = "P1"
        blocking_reason = str(item.get("blocking_reason", "") or "").strip()
        if priority == "P0" and (not blocking_reason or len(blocking_reason) < 10 or blocking_reason == reason):
            priority = "P1"
            blocking_reason = ""
        normalized.append(
            {
                "gap": gap,
                "gap_type": gap_type,
                "reason": reason,
                "impact": impact,
                "priority": priority,
                "blocking_reason": blocking_reason,
            }
        )
    return normalized


def _gap_exists(items: List[Dict[str, str]], candidate: Dict[str, str]) -> bool:
    candidate_key = (candidate.get("gap"), candidate.get("gap_type"), candidate.get("reason"), candidate.get("impact"))
    return any(
        (item.get("gap"), item.get("gap_type"), item.get("reason"), item.get("impact")) == candidate_key
        for item in items
    )


def _rebalance_gap_priorities(gaps: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if len(gaps) <= 2:
        return gaps

    p0_indexes = [index for index, gap in enumerate(gaps) if gap.get("priority") == "P0"]
    if len(gaps) <= 6:
        max_p0 = 1
    else:
        max_p0 = max(1, len(gaps) // 3)

    if len(p0_indexes) <= max_p0:
        return gaps

    for index in p0_indexes[max_p0:]:
        gaps[index]["priority"] = "P1"
        gaps[index]["blocking_reason"] = ""
    return gaps


def _build_pdf_supplement(draft: Optional[ClarificationReviewPdfDraft], applied_fields: List[str]) -> str:
    if draft is None:
        return ""

    strict_result = _decode_json_safely(draft.strict_result_json, {"fields": {}, "conflicts": []})
    inference_result = _decode_json_safely(draft.inference_result_json, {"fields": {}, "conflicts": []})
    vision_notes = _decode_json_safely(draft.vision_notes_json, [])
    full_text_payload = _decode_json_safely(draft.full_text_json, {"pages": []})

    strict_fields = strict_result.get("fields") if isinstance(strict_result, dict) else {}
    strict_conflicts = strict_result.get("conflicts") if isinstance(strict_result, dict) else []
    inference_fields = inference_result.get("fields") if isinstance(inference_result, dict) else {}
    full_text_pages = full_text_payload.get("pages") if isinstance(full_text_payload, dict) else []

    conflicts_text = _format_conflicts(strict_conflicts)
    strict_evidence_text = _format_field_evidence(
        strict_fields,
        applied_fields,
        max_chars=PDF_SUPPLEMENT_MAX_STRICT_EVIDENCE_CHARS,
    )
    inference_evidence_text = _format_field_evidence(
        inference_fields,
        applied_fields,
        max_chars=PDF_SUPPLEMENT_MAX_INFERENCE_EVIDENCE_CHARS,
    )
    vision_notes_text = _format_vision_notes(vision_notes)
    full_text_excerpt = _format_full_text_excerpt(full_text_pages)

    material_signals = [strict_conflicts, strict_fields, inference_fields, vision_notes, full_text_pages]
    if not any(_has_meaningful_pdf_content(item) for item in material_signals):
        return ""

    applied_count = len([field for field in applied_fields if field in PDF_FIELD_LABELS])
    source_note = "当前表单中仍沿用了 {0} 个 PDF 草稿字段；其余内容仅供参考。".format(applied_count)

    return PDF_SUPPLEMENT_SECTION.format(
        source_note=source_note,
        conflicts_text=conflicts_text,
        strict_evidence_text=strict_evidence_text,
        inference_evidence_text=inference_evidence_text,
        vision_notes_text=vision_notes_text,
        full_text_excerpt=full_text_excerpt,
    )


def _get_valid_pdf_draft_or_none(db: Session, draft_id: Optional[int]) -> Optional[ClarificationReviewPdfDraft]:
    if draft_id is None:
        return None
    try:
        return get_pdf_draft(db, int(draft_id))
    except (PdfDraftNotFoundError, ValueError):
        return None


def _decode_json_safely(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _format_conflicts(conflicts: Any) -> str:
    if not isinstance(conflicts, list) or not conflicts:
        return "无明显文档内部冲突"

    lines: List[str] = []
    for item in conflicts[:PDF_SUPPLEMENT_MAX_CONFLICTS]:
        if not isinstance(item, dict):
            continue
        field_label = PDF_FIELD_LABELS.get(str(item.get("field", "") or ""), str(item.get("field", "") or "未指定字段"))
        description = str(item.get("description", "") or "").strip() or "未提供冲突描述"
        evidence = str(item.get("evidence", "") or "").strip() or "未提供冲突证据"
        lines.append("- {0}：{1}；evidence：{2}".format(field_label, description, evidence))

    return "\n".join(lines) if lines else "无明显文档内部冲突"


def _format_field_evidence(fields: Any, applied_fields: List[str], max_chars: int) -> str:
    if not isinstance(fields, dict):
        return "无补充推断依据" if max_chars == PDF_SUPPLEMENT_MAX_INFERENCE_EVIDENCE_CHARS else "无直接字段证据"

    applied_field_set = {str(item or "").strip() for item in applied_fields}
    lines: List[str] = []
    for field_name, field_label in PDF_FIELD_LABELS.items():
        item = fields.get(field_name)
        if not isinstance(item, dict):
            continue
        value = str(item.get("value", "") or "").strip()
        evidence = str(item.get("evidence", "") or "").strip()
        if not value and not evidence:
            continue
        apply_state = "已应用到当前表单" if field_name in applied_field_set else "未应用到当前表单，仅供参考"
        lines.append("- {0}（{1}）".format(field_label, apply_state))
        if value:
            lines.append("  value 摘要：{0}".format(value))
        if evidence:
            lines.append("  evidence：{0}".format(evidence))

    if not lines:
        return "无补充推断依据" if max_chars == PDF_SUPPLEMENT_MAX_INFERENCE_EVIDENCE_CHARS else "无直接字段证据"

    return _truncate_text("\n".join(lines), max_chars, "（字段证据过长，已按预算截断）")


def _format_vision_notes(vision_notes: Any) -> str:
    if not isinstance(vision_notes, list):
        return "无视觉理解笔记"

    lines = ["- {0}".format(str(item).strip()) for item in vision_notes if str(item or "").strip()]
    if not lines:
        return "无视觉理解笔记"
    return _truncate_text("\n".join(lines), PDF_SUPPLEMENT_MAX_VISION_NOTES_CHARS, "（视觉笔记过长，已按预算截断）")


def _format_full_text_excerpt(full_text_pages: Any) -> str:
    if not isinstance(full_text_pages, list):
        return "无可用全文内容"

    chunks: List[str] = []
    for index, page_text in enumerate(full_text_pages, start=1):
        text = str(page_text or "").strip()
        if not text:
            continue
        chunks.append("[第 {0} 页]\n{1}".format(index, text))

    if not chunks:
        return "无可用全文内容"

    return _truncate_text("\n\n".join(chunks), PDF_SUPPLEMENT_MAX_FULL_TEXT_CHARS, "（PDF 原文过长，已按预算截断）")


def _truncate_text(text: str, max_chars: int, suffix: str) -> str:
    normalized = str(text or "")
    if len(normalized) <= max_chars:
        return normalized
    trimmed = normalized[: max(0, max_chars)].rstrip()
    return "{0}\n...{1}".format(trimmed, suffix)


def _has_meaningful_pdf_content(payload: Any) -> bool:
    if isinstance(payload, dict):
        return any(_has_meaningful_pdf_content(value) for value in payload.values())
    if isinstance(payload, list):
        return any(_has_meaningful_pdf_content(value) for value in payload)
    return bool(str(payload or "").strip())


def _build_source_meta(db: Session, payload: ClarificationReviewAnalyzeRequest) -> Dict[str, Any]:
    draft = _get_valid_pdf_draft_or_none(db, payload.source_draft_id)
    return {
        "source_kind": "pdf_draft",
        "draft_id": int(payload.source_draft_id),
        "file_name": draft.file_name if draft else None,
        "draft_created_at": draft.created_at.isoformat() if draft and isinstance(draft.created_at, datetime) else None,
        "draft_expired": draft is None,
        "applied_fields": [str(field or "") for field in payload.applied_fields or []],
    }
