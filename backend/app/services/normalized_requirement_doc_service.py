import logging
import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.entities import EffectiveRequirementSnapshot, Requirement, RequirementInput
from app.services.effective_requirement_service import (
    annotate_snapshot_freshness,
    compute_basis_hash,
    get_latest_snapshot,
    list_requirement_inputs,
)
from app.services.llm_client import LLMClient
from app.services.llm_result_helpers import build_llm_success_meta
from app.services.prompts.normalized_requirement_doc import (
    NORMALIZED_REQUIREMENT_DOC_SYSTEM_PROMPT,
    NORMALIZED_REQUIREMENT_DOC_USER_TEMPLATE,
    NORMALIZED_REQUIREMENT_DOC_USER_TEMPLATE_NO_SNAPSHOT,
)

logger = logging.getLogger(__name__)

_LLM_FAILURE_MESSAGE = "模型调用失败，未生成规范化需求文档。请稍后重试或检查模型配置。"


class NormalizedRequirementDocGenerationError(RuntimeError):
    pass


def build_normalized_requirement_doc(
    db: Session,
    requirement_id: int,
    llm_client: Optional[Any] = None,
) -> Dict[str, object]:
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    inputs = list_requirement_inputs(db, requirement_id)
    basis_hash = compute_basis_hash(requirement, inputs)
    latest_snapshot = annotate_snapshot_freshness(
        db,
        get_latest_snapshot(db, requirement_id),
        requirement=requirement,
        inputs=inputs,
    )

    uses_fresh_snapshot = bool(latest_snapshot and not latest_snapshot.is_stale)
    snapshot_stale = bool(latest_snapshot and latest_snapshot.is_stale)

    source_payload = build_normalized_requirement_doc_source_payload(requirement, inputs)
    snapshot_payload = serialize_normalized_requirement_snapshot(latest_snapshot) if uses_fresh_snapshot else None

    llm_result = generate_normalized_requirement_doc_from_task_payloads(
        source_payload=source_payload,
        snapshot_payload=snapshot_payload,
        llm_client=llm_client,
    )

    markdown = (llm_result.get("markdown") or "").strip()
    if not markdown:
        raise NormalizedRequirementDocGenerationError(_LLM_FAILURE_MESSAGE)

    return {
        "title": requirement.title,
        "markdown": markdown + "\n",
        "basis_hash": basis_hash,
        "uses_fresh_snapshot": uses_fresh_snapshot,
        "snapshot_stale": snapshot_stale,
        "llm_status": llm_result.get("llm_status"),
        "llm_provider": llm_result.get("llm_provider"),
        "llm_message": llm_result.get("llm_message"),
    }


def build_normalized_requirement_doc_source_payload(
    requirement: Requirement,
    inputs: List[RequirementInput],
) -> Dict[str, Any]:
    return {
        "title": requirement.title or "",
        "raw_text": requirement.raw_text or "",
        "formal_inputs": _serialize_inputs(inputs),
    }


def serialize_normalized_requirement_snapshot(
    snapshot: EffectiveRequirementSnapshot,
) -> Dict[str, Any]:
    fields = []
    for field in sorted(snapshot.fields, key=lambda item: item.sort_order):
        derivation = field.derivation.value if hasattr(field.derivation, "value") and field.derivation else field.derivation
        fields.append(
            {
                "field_key": field.field_key,
                "value": field.value or "",
                "derivation": derivation,
                "confidence": field.confidence,
                "source_refs": field.source_refs or "",
                "notes": field.notes,
            }
        )

    return {
        "id": snapshot.id,
        "stage": snapshot.stage.value if hasattr(snapshot.stage, "value") else snapshot.stage,
        "summary": snapshot.summary or "",
        "fields": fields,
    }


def generate_normalized_requirement_doc_from_task_payloads(
    source_payload: Dict[str, Any],
    snapshot_payload: Optional[Dict[str, Any]],
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    user_prompt = _build_user_prompt(source_payload=source_payload, snapshot_payload=snapshot_payload)

    try:
        llm = llm_client or LLMClient()
        payload = llm.chat_with_json(
            system_prompt=NORMALIZED_REQUIREMENT_DOC_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        logger.warning(
            "Normalized requirement doc generation failed (%s: %s)",
            type(exc).__name__,
            exc,
        )
        raise NormalizedRequirementDocGenerationError(_LLM_FAILURE_MESSAGE)

    markdown = payload.get("markdown", "") if isinstance(payload, dict) else ""
    if not isinstance(markdown, str) or not markdown.strip():
        raise NormalizedRequirementDocGenerationError(_LLM_FAILURE_MESSAGE)

    return {
        "markdown": markdown,
        **build_llm_success_meta(_resolve_provider_from_llm(llm)),
    }


def _build_user_prompt(
    source_payload: Dict[str, Any],
    snapshot_payload: Optional[Dict[str, Any]],
) -> str:
    if snapshot_payload is None:
        return NORMALIZED_REQUIREMENT_DOC_USER_TEMPLATE_NO_SNAPSHOT.format(
            payload_json=json.dumps(source_payload, ensure_ascii=False, indent=2),
        )

    return NORMALIZED_REQUIREMENT_DOC_USER_TEMPLATE.format(
        payload_json=json.dumps(source_payload, ensure_ascii=False, indent=2),
        snapshot_json=json.dumps(snapshot_payload, ensure_ascii=False, indent=2),
    )


def _serialize_inputs(inputs: List[RequirementInput]) -> List[Dict[str, Any]]:
    result = []
    for item in inputs:
        input_type = item.input_type.value if hasattr(item.input_type, "value") else item.input_type
        result.append(
            {
                "id": item.id,
                "input_type": input_type,
                "content": item.content or "",
                "source_label": item.source_label or "",
            }
        )
    return result


def _resolve_provider_from_llm(llm: object) -> Optional[str]:
    getter = getattr(llm, "get_last_provider", None)
    if callable(getter):
        return getter()
    return None
