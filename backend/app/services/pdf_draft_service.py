import json
import logging
import os
import shutil
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import ClarificationReviewPdfDraft
from app.services.llm_client import LLMClient
from app.services.openai_client import OpenAIClient
from app.services.pdf_extraction import (
    compute_page_stats,
    extract_full_text,
    render_pages,
    select_vision_pages,
    validate_pdf_file,
)
from app.services.prompts.pdf_extraction_prompts import (
    INFER_EXTRACTION_SYSTEM_PROMPT,
    INFER_EXTRACTION_USER_TEMPLATE,
    STRICT_EXTRACTION_SYSTEM_PROMPT,
    STRICT_EXTRACTION_USER_TEMPLATE,
    VISION_NOTES_SYSTEM_PROMPT,
)


logger = logging.getLogger(__name__)

PDF_DRAFT_TTL_HOURS = 24
PDF_DRAFT_ORPHAN_TTL_DAYS = 7
PDF_RESULT_FIELDS = (
    "requirement_text",
    "current_surface_flow",
    "involved_modules",
    "known_background",
    "unknowns",
)
PDF_DRAFT_TMP_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".tmp", "pdf_drafts")
)


class PdfDraftNotFoundError(LookupError):
    pass


class PdfDraftInferConflictError(Exception):
    pass


def create_pdf_draft(db: Session, file: Any) -> ClarificationReviewPdfDraft:
    cleanup_expired_drafts(db)
    validated = validate_pdf_file(file)
    now = datetime.utcnow()
    draft = ClarificationReviewPdfDraft(
        file_name=validated["file_name"],
        file_size_bytes=validated["file_size_bytes"],
        page_count=validated["page_count"],
        status="queued",
        llm_status="failed",
        progress_message="已接受 PDF 导入任务，等待开始执行",
        progress_percent=5,
        expires_at=now + timedelta(hours=PDF_DRAFT_TTL_HOURS),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)

    draft_dir = _draft_dir(draft.id)
    os.makedirs(draft_dir, exist_ok=True)
    pdf_path = os.path.join(draft_dir, "source.pdf")
    with open(pdf_path, "wb") as handle:
        handle.write(validated["content"])

    _launch_pdf_draft_worker(draft.id)
    return draft


def _launch_pdf_draft_worker(draft_id: int) -> None:
    worker = threading.Thread(
        target=_run_pdf_draft_task,
        kwargs={"draft_id": draft_id},
        daemon=True,
    )
    worker.start()


def _run_pdf_draft_task(draft_id: int) -> None:
    db = SessionLocal()
    try:
        draft = db.query(ClarificationReviewPdfDraft).filter(ClarificationReviewPdfDraft.id == draft_id).first()
        if not draft:
            return

        draft.status = "extracting"
        draft.progress_message = "正在提取 PDF 内容"
        draft.progress_percent = 15
        draft.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(draft)

        pdf_path = os.path.join(_draft_dir(draft.id), "source.pdf")

        pages_text = extract_full_text(pdf_path)
        draft.full_text_json = json.dumps({"pages": pages_text}, ensure_ascii=False)
        page_stats = compute_page_stats(pages_text)
        draft.page_text_stats_json = json.dumps(page_stats, ensure_ascii=False)

        selected_page_indexes = select_vision_pages(page_stats, pages_text, max_pages=10)
        draft.selected_page_indexes_json = json.dumps(selected_page_indexes, ensure_ascii=False)
        draft_dir = _draft_dir(draft.id)
        rendered_page_paths = render_pages(pdf_path, selected_page_indexes, draft_dir, dpi=150) if selected_page_indexes else []
        draft.rendered_page_paths_json = json.dumps(rendered_page_paths, ensure_ascii=False)

        text_extraction_failed = not any(str(page or "").strip() for page in pages_text)
        vision_notes: List[str] = []
        vision_error: Optional[str] = None
        if rendered_page_paths:
            draft.progress_message = "正在进行视觉理解"
            draft.progress_percent = 35
            draft.updated_at = datetime.utcnow()
            db.commit()
            try:
                vision_notes = _run_vision_extraction(rendered_page_paths)
            except Exception as exc:
                vision_error = str(exc) or "vision extraction failed"
                logger.warning("pdf vision extraction failed for draft=%s: %s", draft.id, exc)
        draft.vision_notes_json = json.dumps(vision_notes, ensure_ascii=False)

        draft.progress_message = "正在严格提取结构化信息"
        draft.progress_percent = 65
        draft.updated_at = datetime.utcnow()
        db.commit()

        try:
            strict_result = _run_strict_extraction(
                full_text_pages=pages_text,
                vision_notes=vision_notes,
                text_extraction_failed=text_extraction_failed,
            )
        except Exception as exc:
            draft.status = "failed"
            draft.llm_status = "failed"
            draft.llm_provider = None
            draft.llm_message = str(exc) or "strict extraction failed"
            draft.progress_message = "PDF 提取失败"
            draft.progress_percent = 100
            draft.updated_at = datetime.utcnow()
            db.add(draft)
            db.commit()
            return

        draft.strict_result_json = json.dumps(strict_result, ensure_ascii=False)
        draft.llm_status = "success"
        draft.llm_provider = strict_result.get("_meta", {}).get("provider")
        draft.llm_message = vision_error
        draft.status = _resolve_draft_status(text_extraction_failed=text_extraction_failed, vision_failed=bool(vision_error))
        draft.progress_message = "PDF 草稿已生成"
        draft.progress_percent = 100
        draft.updated_at = datetime.utcnow()
        db.add(draft)
        db.commit()
    except Exception as exc:
        db.rollback()
        draft = db.query(ClarificationReviewPdfDraft).filter(ClarificationReviewPdfDraft.id == draft_id).first()
        if draft:
            draft.status = "failed"
            draft.llm_status = "failed"
            draft.progress_message = "PDF 导入执行失败"
            draft.progress_percent = 100
            draft.llm_message = str(exc)
            draft.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def infer_pdf_draft(db: Session, draft_id: int) -> ClarificationReviewPdfDraft:
    cleanup_expired_drafts(db)
    draft = get_pdf_draft(db, draft_id)
    if draft.status not in {"success", "partial_success"}:
        raise ValueError("pdf draft is not ready for inference")
    if draft.infer_task_status in ("queued", "running"):
        raise PdfDraftInferConflictError("补充推断任务正在进行中，请稍后再试")

    draft.infer_task_status = "queued"
    draft.progress_message = "已接受补充推断任务，等待开始执行"
    draft.progress_percent = 5
    draft.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)

    _launch_infer_worker(draft.id)
    return draft


def _launch_infer_worker(draft_id: int) -> None:
    worker = threading.Thread(
        target=_run_infer_task,
        kwargs={"draft_id": draft_id},
        daemon=True,
    )
    worker.start()


def _run_infer_task(draft_id: int) -> None:
    db = SessionLocal()
    try:
        draft = db.query(ClarificationReviewPdfDraft).filter(ClarificationReviewPdfDraft.id == draft_id).first()
        if not draft or draft.expires_at < datetime.utcnow():
            return

        draft.infer_task_status = "running"
        draft.progress_message = "正在执行 LLM 补充推断"
        draft.progress_percent = 30
        draft.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(draft)

        full_text_pages = _decode_pages(draft.full_text_json)
        vision_notes = _decode_list(draft.vision_notes_json)
        strict_result = _decode_json(draft.strict_result_json, _empty_pdf_result())

        llm = LLMClient()
        payload = llm.chat_with_json(
            system_prompt=INFER_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=INFER_EXTRACTION_USER_TEMPLATE.format(
                strict_result=json.dumps(strict_result, ensure_ascii=False),
                full_text="\n\n".join(full_text_pages) or "无全文内容",
                vision_notes="\n".join(vision_notes) or "无视觉笔记",
            ),
        )
        normalized = _normalize_pdf_result(payload, allow_conflicts=False)
        provider = _resolve_provider_from_llm(llm, "chat_with_json")

        draft.inference_result_json = json.dumps(normalized, ensure_ascii=False)
        draft.infer_llm_status = "success"
        draft.infer_llm_provider = provider
        draft.infer_llm_message = None
        draft.infer_task_status = "completed"
        draft.progress_message = "补充推断已完成"
        draft.progress_percent = 100
        draft.updated_at = datetime.utcnow()
        db.add(draft)
        db.commit()
    except Exception as exc:
        db.rollback()
        draft = db.query(ClarificationReviewPdfDraft).filter(ClarificationReviewPdfDraft.id == draft_id).first()
        if draft:
            draft.infer_task_status = "failed"
            draft.infer_llm_status = "failed"
            draft.infer_llm_message = str(exc)
            draft.progress_message = "补充推断执行失败"
            draft.progress_percent = 100
            draft.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def get_pdf_draft(db: Session, draft_id: int) -> ClarificationReviewPdfDraft:
    draft = db.query(ClarificationReviewPdfDraft).filter(ClarificationReviewPdfDraft.id == draft_id).first()
    if not draft or draft.expires_at < datetime.utcnow():
        raise PdfDraftNotFoundError("pdf draft not found")
    return draft


def cleanup_expired_drafts(db: Session) -> int:
    """Remove drafts whose `expires_at` has passed.

    Note: This only removes drafts that never got linked to a requirement.
    Successfully-consumed drafts (generated_requirement_id IS NOT NULL) are kept
    until the orphan sweeper runs after the longer retention window.
    """
    expired = (
        db.query(ClarificationReviewPdfDraft)
        .filter(
            ClarificationReviewPdfDraft.expires_at < datetime.utcnow(),
            ClarificationReviewPdfDraft.generated_requirement_id.is_(None),
        )
        .all()
    )
    if not expired:
        return 0

    for draft in expired:
        shutil.rmtree(_draft_dir(draft.id), ignore_errors=True)
        db.delete(draft)
    db.commit()
    return len(expired)


def cleanup_orphan_drafts(db: Session, ttl_days: int = PDF_DRAFT_ORPHAN_TTL_DAYS) -> int:
    """Sweep drafts older than ttl_days that never got linked to a requirement.

    Mirrors the scheduled cleanup described in the Batch 4 plan: only drafts
    whose `generated_requirement_id IS NULL` and whose `created_at` is older
    than `ttl_days` will be removed.
    """
    cutoff = datetime.utcnow() - timedelta(days=ttl_days)
    orphans = (
        db.query(ClarificationReviewPdfDraft)
        .filter(
            ClarificationReviewPdfDraft.generated_requirement_id.is_(None),
            ClarificationReviewPdfDraft.created_at < cutoff,
        )
        .all()
    )
    if not orphans:
        return 0

    for draft in orphans:
        shutil.rmtree(_draft_dir(draft.id), ignore_errors=True)
        db.delete(draft)
    db.commit()
    logger.info("Cleaned up %d orphan pdf drafts older than %d days", len(orphans), ttl_days)
    return len(orphans)


def _run_vision_extraction(rendered_page_paths: List[str]) -> List[str]:
    if not rendered_page_paths:
        return []

    client = OpenAIClient()
    try:
        return _run_single_vision_call(client, rendered_page_paths)
    except Exception:
        if len(rendered_page_paths) <= 5:
            raise
        notes: List[str] = []
        first = _run_single_vision_call(client, rendered_page_paths[:5])
        second = _run_single_vision_call(client, rendered_page_paths[5:10])
        notes.extend(first)
        notes.extend(second)
        return notes


def _run_single_vision_call(client: OpenAIClient, rendered_page_paths: List[str]) -> List[str]:
    user_content: List[Dict[str, Any]] = [
        {"type": "text", "text": "请总结这些 PDF 页面里的流程、表格、模块和关键约束。"}
    ]
    for path in rendered_page_paths:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": client.image_to_base64_url(path)},
            }
        )
    response_text = client.chat_with_vision(
        system_prompt=VISION_NOTES_SYSTEM_PROMPT,
        user_content=user_content,
    )
    return [line.strip() for line in str(response_text or "").splitlines() if line.strip()]


def _run_strict_extraction(
    *,
    full_text_pages: List[str],
    vision_notes: List[str],
    text_extraction_failed: bool,
) -> Dict[str, Any]:
    if text_extraction_failed and not vision_notes:
        raise ValueError("pdf extraction did not produce usable content")

    llm = LLMClient()
    payload = llm.chat_with_json(
        system_prompt=STRICT_EXTRACTION_SYSTEM_PROMPT,
        user_prompt=STRICT_EXTRACTION_USER_TEMPLATE.format(
            full_text="\n\n".join(full_text_pages) or "无全文内容",
            vision_notes="\n".join(vision_notes) or "无视觉笔记",
            text_extraction_failed="true" if text_extraction_failed else "false",
        ),
    )
    normalized = _normalize_pdf_result(payload, allow_conflicts=True)
    normalized["_meta"] = {"provider": _resolve_provider_from_llm(llm, "chat_with_json")}
    return normalized


def _resolve_draft_status(*, text_extraction_failed: bool, vision_failed: bool) -> str:
    if text_extraction_failed or vision_failed:
        return "partial_success"
    return "success"


def _normalize_pdf_result(payload: Any, *, allow_conflicts: bool) -> Dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}

    normalized_fields = {}
    for field_name in PDF_RESULT_FIELDS:
        value = fields.get(field_name) if isinstance(fields, dict) else None
        if isinstance(value, dict):
            normalized_fields[field_name] = {
                "value": str(value.get("value", "") or ""),
                "evidence": str(value.get("evidence", "") or ""),
            }
        else:
            normalized_fields[field_name] = {"value": "", "evidence": ""}

    normalized_conflicts: List[Dict[str, str]] = []
    if allow_conflicts and isinstance(raw.get("conflicts"), list):
        for item in raw["conflicts"]:
            if not isinstance(item, dict):
                continue
            normalized_conflicts.append(
                {
                    "field": str(item.get("field", "") or ""),
                    "description": str(item.get("description", "") or ""),
                    "evidence": str(item.get("evidence", "") or ""),
                }
            )

    return {
        "fields": normalized_fields,
        "conflicts": normalized_conflicts,
    }


def _empty_pdf_result() -> Dict[str, Any]:
    return {
        "fields": {
            field_name: {"value": "", "evidence": ""}
            for field_name in PDF_RESULT_FIELDS
        },
        "conflicts": [],
    }


def _decode_json(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _decode_list(value: Optional[str]) -> List[str]:
    parsed = _decode_json(value, [])
    if not isinstance(parsed, list):
        return []
    return [str(item or "") for item in parsed]


def _decode_pages(value: Optional[str]) -> List[str]:
    parsed = _decode_json(value, {})
    if isinstance(parsed, dict) and isinstance(parsed.get("pages"), list):
        return [str(item or "") for item in parsed["pages"]]
    return []


def _resolve_provider_from_llm(llm: Any, method_name: str) -> Optional[str]:
    getter = getattr(llm, "get_last_provider", None)
    if not callable(getter):
        return None
    provider = getter(method_name=method_name)
    if not provider:
        return None
    return str(provider).strip().lower() or None


def _draft_dir(draft_id: int) -> str:
    return os.path.join(PDF_DRAFT_TMP_ROOT, str(draft_id))
