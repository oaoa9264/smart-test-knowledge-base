import json
import logging
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import ClarificationReviewPdfDraft, ClarificationReviewRecord, InputType, Project, Requirement, RequirementInput, SourceType
from app.schemas.clarification_review import ClarificationReviewAnalyzeRequest
from app.services.llm_result_helpers import (
    DEFAULT_LLM_FAILURE_MESSAGE as DEFAULT_LLM_FAILURE_MESSAGE_FALLBACK,
    build_llm_failure_meta,
    build_llm_success_meta,
    classify_llm_exception,
)
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

RESOLUTION_STATUSES = {"pending", "confirmed", "assume_and_proceed", "dismissed"}
RESOLUTION_KEYS = ("resolution_status", "resolution_note", "resolved_by", "resolved_at")


def _copy_resolution_fields(source: Dict[str, Any], target: Dict[str, str]) -> None:
    """Copy resolution tracking fields from source dict to target, if present."""
    status = str(source.get("resolution_status", "") or "").strip()
    if status and status in RESOLUTION_STATUSES:
        target["resolution_status"] = status
        target["resolution_note"] = str(source.get("resolution_note", "") or "")
        target["resolved_by"] = str(source.get("resolved_by", "") or "")
        target["resolved_at"] = str(source.get("resolved_at", "") or "")


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
    empty = _empty_result(configured_roles, result_version=RESULT_VERSION_V2)

    record = ClarificationReviewRecord(
        input_payload_json=json.dumps(input_payload, ensure_ascii=False),
        rule_text=payload.rule_text,
        result_json=json.dumps(empty, ensure_ascii=False),
        llm_status="failed",
        llm_provider=None,
        llm_message=None,
        source_draft_id=payload.source_draft_id,
        source_meta_json=json.dumps(_build_source_meta(db, payload), ensure_ascii=False)
        if payload.source_draft_id is not None
        else None,
        task_status="queued",
        progress_message="已接受追问分析任务，等待开始执行",
        progress_percent=5,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    _launch_analyze_worker(record.id)
    return record


def _launch_analyze_worker(record_id: int) -> None:
    worker = threading.Thread(
        target=_run_analyze_task,
        kwargs={"record_id": record_id},
        daemon=True,
    )
    worker.start()


def _run_analyze_task(record_id: int) -> None:
    db = SessionLocal()
    try:
        record = db.query(ClarificationReviewRecord).filter(ClarificationReviewRecord.id == record_id).first()
        if not record:
            return

        record.task_status = "running"
        record.progress_message = "正在执行追问分析"
        record.progress_percent = 30
        record.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(record)

        payload_dict = json.loads(record.input_payload_json)
        configured_roles = _extract_configured_roles(record.rule_text)
        result = _empty_result(configured_roles, result_version=RESULT_VERSION_V2)
        meta = build_llm_failure_meta()

        if _has_any_input(payload_dict):
            try:
                llm = LLMClient()
                user_prompt = CLARIFICATION_REVIEW_USER_TEMPLATE.format(
                    rule_text=record.rule_text,
                    **payload_dict,
                )
                draft = _get_valid_pdf_draft_or_none(db, record.source_draft_id)
                applied_fields = []
                if record.source_meta_json:
                    source_meta = json.loads(record.source_meta_json)
                    applied_fields = source_meta.get("applied_fields", [])
                pdf_supplement = _build_pdf_supplement(draft=draft, applied_fields=applied_fields)
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
                meta = build_llm_failure_meta(
                    message=str(exc) or DEFAULT_LLM_FAILURE_MESSAGE_FALLBACK,
                    code=classify_llm_exception(exc),
                )

        result = _normalize_result(
            result,
            meta,
            configured_roles,
            force_result_version=RESULT_VERSION_V2,
            allow_pdf_source=record.source_draft_id is not None,
        )
        record.result_json = json.dumps(result, ensure_ascii=False)
        record.llm_status = result["llm_status"]
        record.llm_provider = result["llm_provider"]
        record.llm_message = result["llm_message"]
        record.task_status = "completed"
        record.progress_message = "追问分析完成"
        record.progress_percent = 100
        record.updated_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        record = db.query(ClarificationReviewRecord).filter(ClarificationReviewRecord.id == record_id).first()
        if record:
            record.task_status = "failed"
            record.progress_message = "追问分析执行失败"
            record.progress_percent = 100
            record.llm_message = str(exc)
            record.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


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


class ItemResolutionError(Exception):
    pass


def update_item_resolutions(db: Session, record_id: int, updates: List[Dict[str, Any]]) -> ClarificationReviewRecord:
    record = db.query(ClarificationReviewRecord).filter(ClarificationReviewRecord.id == record_id).first()
    if not record:
        raise ItemResolutionError("record not found")

    result = json.loads(record.result_json) if record.result_json else {}
    now = datetime.utcnow().isoformat()

    for update in updates:
        item_type = update.get("item_type")
        index = update.get("index")
        role = update.get("role")
        status = update.get("resolution_status", "pending")

        if status not in RESOLUTION_STATUSES:
            raise ItemResolutionError("invalid resolution_status: {0}".format(status))

        if item_type == "gap":
            items = result.get("known_requirement_gaps", [])
        elif item_type == "assumption":
            items = result.get("assumption_items", [])
        elif item_type == "question":
            if not role:
                raise ItemResolutionError("role is required for question items")
            role_questions = result.get("priority_questions_by_role", {})
            items = role_questions.get(role, [])
        else:
            raise ItemResolutionError("invalid item_type: {0}".format(item_type))

        if not isinstance(index, int) or index < 0 or index >= len(items):
            raise ItemResolutionError("index {0} out of range for {1}".format(index, item_type))

        items[index]["resolution_status"] = status
        items[index]["resolution_note"] = str(update.get("resolution_note", "") or "")
        items[index]["resolved_by"] = str(update.get("resolved_by", "") or "")
        items[index]["resolved_at"] = now

    record.result_json = json.dumps(result, ensure_ascii=False)
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return record


class CreateRequirementError(Exception):
    pass


def create_requirement_from_review(
    db: Session,
    record_id: int,
    project_id: int,
    title: str = "",
) -> Requirement:
    record = db.query(ClarificationReviewRecord).filter(ClarificationReviewRecord.id == record_id).first()
    if not record:
        raise CreateRequirementError("record not found")
    if record.task_status != "completed":
        raise CreateRequirementError("record task is not completed")
    if record.generated_requirement_id is not None:
        raise CreateRequirementError("requirement already created for this record")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise CreateRequirementError("project not found")

    input_payload = json.loads(record.input_payload_json) if record.input_payload_json else {}
    result = json.loads(record.result_json) if record.result_json else {}

    requirement_text = str(input_payload.get("requirement_text", "") or "")
    current_surface_flow = str(input_payload.get("current_surface_flow", "") or "")
    involved_modules = str(input_payload.get("involved_modules", "") or "")
    known_background = str(input_payload.get("known_background", "") or "")
    unknowns = str(input_payload.get("unknowns", "") or "")

    # Build raw_text sections
    sections = []
    sections.append("## 需求原文\n{0}".format(requirement_text or "（无）"))
    if current_surface_flow.strip():
        sections.append("## 当前表面流程\n{0}".format(current_surface_flow))
    if involved_modules.strip():
        sections.append("## 涉及模块\n{0}".format(involved_modules))
    if known_background.strip():
        sections.append("## 已知背景\n{0}".format(known_background))
    if unknowns.strip():
        sections.append("## 暂时不知道的内容\n{0}".format(unknowns))

    # Inferred items
    inferred_items = result.get("inferred_items", [])
    if inferred_items:
        lines = []
        for item in inferred_items:
            statement = str(item.get("statement", "") or "").strip()
            evidence = str(item.get("evidence", "") or "").strip()
            if statement:
                lines.append("- {0}（依据：{1}）".format(statement, evidence or "无"))
        if lines:
            sections.append("## 合理推断（来自追问分析）\n{0}".format("\n".join(lines)))

    # Collect items by resolution_status
    confirmed_lines = []
    assumption_lines = []
    pending_lines = []

    for gap in result.get("known_requirement_gaps", []):
        status = str(gap.get("resolution_status", "") or "").strip()
        text = str(gap.get("gap", "") or "").strip()
        note = str(gap.get("resolution_note", "") or "").strip()
        label = "缺陷：{0}".format(text)
        if note:
            label = "{0}（备注：{1}）".format(label, note)
        if status == "confirmed":
            confirmed_lines.append("- {0}".format(label))
        elif status == "assume_and_proceed":
            assumption_lines.append("- {0}".format(label))
        elif status == "pending" or not status:
            pending_lines.append("- {0}".format(label))

    for assumption in result.get("assumption_items", []):
        status = str(assumption.get("resolution_status", "") or "").strip()
        text = str(assumption.get("assumption", "") or "").strip()
        note = str(assumption.get("resolution_note", "") or "").strip()
        label = "假设：{0}".format(text)
        if note:
            label = "{0}（备注：{1}）".format(label, note)
        if status == "confirmed":
            confirmed_lines.append("- {0}".format(label))
        elif status == "assume_and_proceed":
            assumption_lines.append("- {0}".format(label))
        elif status == "pending" or not status:
            pending_lines.append("- {0}".format(label))

    for role, questions in result.get("priority_questions_by_role", {}).items():
        for q in questions:
            status = str(q.get("resolution_status", "") or "").strip()
            text = str(q.get("question", "") or "").strip()
            note = str(q.get("resolution_note", "") or "").strip()
            label = "追问（{0}）：{1}".format(role, text)
            if note:
                label = "{0}（备注：{1}）".format(label, note)
            if status == "confirmed":
                confirmed_lines.append("- {0}".format(label))
            elif status == "assume_and_proceed":
                assumption_lines.append("- {0}".format(label))
            elif status == "pending" or not status:
                pending_lines.append("- {0}".format(label))

    if confirmed_lines:
        sections.append("## 已确认的澄清结论\n{0}".format("\n".join(confirmed_lines)))
    if assumption_lines:
        sections.append("## 按假设推进的项目\n{0}".format(
            "\n".join("{0} ⚠️ 假设".format(line) for line in assumption_lines)
        ))

    raw_text = "\n\n".join(sections)

    # Generate title
    if not title.strip():
        title = requirement_text[:60].strip() or "追问分析 #{0}".format(record_id)

    # Create Requirement
    requirement = Requirement(
        project_id=project_id,
        title=title,
        raw_text=raw_text,
        source_type=SourceType.prd,
    )
    db.add(requirement)
    db.flush()

    # Create RequirementInput: raw_requirement
    db.add(RequirementInput(
        requirement_id=requirement.id,
        input_type=InputType.raw_requirement,
        content=raw_text,
        source_label="requirement.raw_text",
    ))

    # Create RequirementInputs by resolution_status
    source_label = "追问分析 #{0}".format(record_id)
    created_by = "system/clarification_review"

    if confirmed_lines:
        db.add(RequirementInput(
            requirement_id=requirement.id,
            input_type=InputType.clarification_confirmed,
            content="\n".join(confirmed_lines),
            source_label=source_label,
            created_by=created_by,
        ))
    if assumption_lines:
        db.add(RequirementInput(
            requirement_id=requirement.id,
            input_type=InputType.clarification_assumption,
            content="\n".join(assumption_lines),
            source_label=source_label,
            created_by=created_by,
        ))
    if pending_lines:
        db.add(RequirementInput(
            requirement_id=requirement.id,
            input_type=InputType.clarification_pending,
            content="\n".join(pending_lines),
            source_label=source_label,
            created_by=created_by,
        ))

    # Link record to requirement
    record.generated_requirement_id = requirement.id
    record.updated_at = datetime.utcnow()

    # Also link the originating PDF draft (if any) so orphan cleanup spares it.
    if record.source_draft_id is not None:
        draft = (
            db.query(ClarificationReviewPdfDraft)
            .filter(ClarificationReviewPdfDraft.id == record.source_draft_id)
            .first()
        )
        if draft is not None:
            draft.generated_requirement_id = requirement.id
            draft.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(requirement)
    return requirement


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
    if not isinstance(payload, list):
        return []
    items = []
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        item = {key: str(raw_item.get(key, "") or "") for key in ("question", "why_ask", "risk_if_unasked", "required_output", "answer_format")}
        answer_format = str(item.get("answer_format", "") or "").strip()
        item["answer_format"] = answer_format if answer_format in QUESTION_ANSWER_FORMATS else "text"
        item["required_output"] = str(item.get("required_output", "") or "")
        _copy_resolution_fields(raw_item, item)
        items.append(item)
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
    if not isinstance(payload, list):
        return []
    normalized: List[Dict[str, str]] = []
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        assumption = str(raw_item.get("assumption", "") or "").strip()
        basis = str(raw_item.get("basis", "") or "").strip()
        risk = str(raw_item.get("risk", "") or "").strip()
        if not any((assumption, basis, risk)):
            continue
        item: Dict[str, str] = {"assumption": assumption, "basis": basis, "risk": risk}
        _copy_resolution_fields(raw_item, item)
        normalized.append(item)
    return normalized


def _normalize_gap_items(payload: Any) -> List[Dict[str, str]]:
    if not isinstance(payload, list):
        return []
    normalized: List[Dict[str, str]] = []
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        gap = str(raw_item.get("gap", "") or "").strip()
        reason = str(raw_item.get("reason", "") or "").strip()
        impact = str(raw_item.get("impact", "") or "").strip()
        if not gap and not reason and not impact:
            continue
        gap_type = str(raw_item.get("gap_type", "") or "").strip()
        if gap_type not in GAP_TYPES:
            gap_type = GAP_FALLBACK_TYPE
        priority = str(raw_item.get("priority", "") or "").strip()
        if priority not in GAP_PRIORITIES:
            priority = "P1"
        blocking_reason = str(raw_item.get("blocking_reason", "") or "").strip()
        if priority == "P0" and (not blocking_reason or len(blocking_reason) < 10 or blocking_reason == reason):
            priority = "P1"
            blocking_reason = ""
        item: Dict[str, str] = {
            "gap": gap,
            "gap_type": gap_type,
            "reason": reason,
            "impact": impact,
            "priority": priority,
            "blocking_reason": blocking_reason,
        }
        _copy_resolution_fields(raw_item, item)
        normalized.append(item)
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
