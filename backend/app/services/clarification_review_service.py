import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.entities import ClarificationReviewRecord
from app.schemas.clarification_review import ClarificationReviewAnalyzeRequest
from app.services.llm_result_helpers import build_llm_failure_meta, build_llm_success_meta
from app.services.llm_client import LLMClient
from app.services.prompts.clarification_review import (
    CLARIFICATION_REVIEW_USER_TEMPLATE,
    DEFAULT_CLARIFICATION_REVIEW_ROLES,
    build_clarification_review_system_prompt,
)


logger = logging.getLogger(__name__)

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
    result = _empty_result(configured_roles)
    meta = build_llm_failure_meta()

    if _has_any_input(input_payload):
        try:
            llm = llm_client or LLMClient()
            result = llm.chat_with_json(
                system_prompt=build_clarification_review_system_prompt(configured_roles),
                user_prompt=CLARIFICATION_REVIEW_USER_TEMPLATE.format(
                    rule_text=payload.rule_text,
                    **input_payload,
                ),
            )
            provider = _resolve_provider_from_llm(llm)
            meta = build_llm_success_meta(provider)
        except Exception as exc:
            logger.warning("clarification review llm failed: %s", exc)
            result = _empty_result(configured_roles)
            meta = build_llm_failure_meta(str(exc) or None)

    result = _normalize_result(result, meta, configured_roles)
    record = ClarificationReviewRecord(
        input_payload_json=json.dumps(input_payload, ensure_ascii=False),
        rule_text=payload.rule_text,
        result_json=json.dumps(result, ensure_ascii=False),
        llm_status=result["llm_status"],
        llm_provider=result["llm_provider"],
        llm_message=result["llm_message"],
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


def normalize_clarification_review_result(result: Any, rule_text: str) -> Dict[str, Any]:
    configured_roles = _extract_configured_roles(rule_text)
    return _normalize_result(
        result,
        {
            "llm_status": _extract_meta_field(result, "llm_status"),
            "llm_provider": _extract_meta_field(result, "llm_provider"),
            "llm_message": _extract_meta_field(result, "llm_message"),
        },
        configured_roles,
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


def _empty_result(configured_roles: Optional[List[str]] = None) -> Dict[str, Any]:
    roles = list(configured_roles or DEFAULT_CLARIFICATION_REVIEW_ROLES)
    return {
        "likely_historical_rules": [],
        "missing_critical_rules": [],
        "priority_questions_by_role": {role: [] for role in roles},
        "configured_roles": roles,
        "role_descriptors": [{"key": role, "source": "rule_text"} for role in roles],
        "known_requirement_gaps": [],
        "risk_assumptions": [],
        "summary_markdown": "",
    }


def _normalize_result(result: Any, meta: Dict[str, Any], configured_roles: List[str]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        result = {}
    normalized = _empty_result(configured_roles)
    normalized["likely_historical_rules"] = _normalize_list_of_dicts(result.get("likely_historical_rules"), ("rule", "reason"))
    normalized["missing_critical_rules"] = _normalize_list_of_dicts(
        result.get("missing_critical_rules"),
        ("rule", "why_missing", "impact"),
    )
    normalized["known_requirement_gaps"] = _normalize_list_of_dicts(
        result.get("known_requirement_gaps"),
        ("gap", "reason", "impact"),
    )
    normalized["risk_assumptions"] = _normalize_list_of_dicts(
        result.get("risk_assumptions"),
        ("assumption", "basis", "risk"),
    )
    normalized["priority_questions_by_role"], normalized["role_descriptors"] = _normalize_questions(
        result.get("priority_questions_by_role"),
        configured_roles,
    )
    normalized["configured_roles"] = list(configured_roles)
    summary_markdown = result.get("summary_markdown", "")
    normalized["summary_markdown"] = str(summary_markdown or "")
    normalized.update(meta)
    return normalized


def _normalize_questions(payload: Any, configured_roles: List[str]) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    source = payload if isinstance(payload, dict) else {}
    normalized = {role: [] for role in configured_roles}
    extras: Dict[str, List[Dict[str, str]]] = {}

    for raw_role, raw_items in source.items():
        normalized_role = _normalize_role_name(raw_role)
        items = _normalize_list_of_dicts(raw_items, ("question", "why_ask", "risk_if_unasked"))
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
