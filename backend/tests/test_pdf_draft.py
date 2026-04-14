import io
import json
import os
import tempfile
from datetime import datetime, timedelta

from pypdf import PdfWriter
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.entities import ClarificationReviewPdfDraft, ClarificationReviewRecord
from app.services.pdf_extraction import render_pages


client = TestClient(app)


def _build_pdf_bytes(page_count: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _multipart_upload(name: str, content: bytes, content_type: str = "application/pdf"):
    return {"file": (name, content, content_type)}


def test_pdf_draft_rejects_non_pdf_extension():
    resp = client.post(
        "/api/ai/clarification-review/pdf-drafts",
        files=_multipart_upload("notes.txt", b"%PDF-1.4\nfake"),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "only .pdf files are supported"


def test_pdf_draft_rejects_fake_pdf_header():
    resp = client.post(
        "/api/ai/clarification-review/pdf-drafts",
        files=_multipart_upload("fake.pdf", b"not-a-real-pdf"),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid pdf file"


def test_pdf_draft_rejects_too_many_pages():
    resp = client.post(
        "/api/ai/clarification-review/pdf-drafts",
        files=_multipart_upload("oversize.pdf", _build_pdf_bytes(page_count=51)),
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "pdf page count must be <= 50"


def test_render_pages_generates_png_files():
    pdf_path = tempfile.mktemp(suffix=".pdf")
    output_dir = tempfile.mkdtemp()
    with open(pdf_path, "wb") as handle:
        handle.write(_build_pdf_bytes(page_count=1))

    rendered = render_pages(pdf_path, [0], output_dir)

    assert len(rendered) == 1
    assert rendered[0].endswith(".png")
    assert os.path.exists(rendered[0])


def test_pdf_draft_tmp_root_is_outside_backend_dir():
    from app.services import pdf_draft_service

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(pdf_draft_service.__file__), "..", ".."))
    common_path = os.path.commonpath([backend_dir, pdf_draft_service.PDF_DRAFT_TMP_ROOT])

    assert common_path != backend_dir


def test_pdf_draft_create_returns_strict_result(monkeypatch):
    from app.services import pdf_draft_service

    strict_result = {
        "fields": {
            "requirement_text": {"value": "审批通过后推送站内信", "evidence": "第1页"},
            "current_surface_flow": {"value": "提单 -> 审批 -> 通知", "evidence": "第2页"},
            "involved_modules": {"value": "审批中心", "evidence": "第2页"},
            "known_background": {"value": "老项目已运行多年", "evidence": "第3页"},
            "unknowns": {"value": "驳回后通知是否撤回", "evidence": "第3页"},
        },
        "conflicts": [
            {"field": "requirement_text", "description": "50 分与 80 分口径冲突", "evidence": "第4页"}
        ],
    }

    class _FakeDraftService:
        @staticmethod
        def create_pdf_draft(db, file):
            del db, file
            return ClarificationReviewPdfDraft(
                id=1001,
                file_name="clarification.pdf",
                file_size_bytes=12345,
                page_count=7,
                status="success",
                llm_status="success",
                llm_provider="openai",
                llm_message=None,
                infer_llm_status=None,
                infer_llm_provider=None,
                infer_llm_message=None,
                strict_result_json=json.dumps(strict_result, ensure_ascii=False),
                inference_result_json=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=24),
            )

    monkeypatch.setattr(pdf_draft_service, "create_pdf_draft", _FakeDraftService.create_pdf_draft)

    resp = client.post(
        "/api/ai/clarification-review/pdf-drafts",
        files=_multipart_upload("clarification.pdf", _build_pdf_bytes(page_count=2)),
    )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["id"] == 1001
    assert payload["status"] == "success"
    assert payload["strict_result"]["fields"]["requirement_text"]["value"] == "审批通过后推送站内信"
    assert payload["strict_result"]["conflicts"][0]["description"] == "50 分与 80 分口径冲突"
    assert "full_text_json" not in payload
    assert "vision_notes_json" not in payload


def test_pdf_draft_create_degrades_when_vision_fails(monkeypatch):
    from app.services import pdf_draft_service

    strict_result = {
        "fields": {
            "requirement_text": {"value": "仅文本提取成功", "evidence": "第1页"},
            "current_surface_flow": {"value": "", "evidence": ""},
            "involved_modules": {"value": "", "evidence": ""},
            "known_background": {"value": "", "evidence": ""},
            "unknowns": {"value": "", "evidence": ""},
        },
        "conflicts": [],
    }

    def _fake_create(db, file):
        del db, file
        return ClarificationReviewPdfDraft(
            id=1002,
            file_name="partial.pdf",
            file_size_bytes=3456,
            page_count=2,
            status="partial_success",
            llm_status="success",
            llm_provider="zhipu",
            llm_message=None,
            infer_llm_status=None,
            infer_llm_provider=None,
            infer_llm_message=None,
            strict_result_json=json.dumps(strict_result, ensure_ascii=False),
            inference_result_json=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

    monkeypatch.setattr(pdf_draft_service, "create_pdf_draft", _fake_create)

    resp = client.post(
        "/api/ai/clarification-review/pdf-drafts",
        files=_multipart_upload("partial.pdf", _build_pdf_bytes(page_count=2)),
    )

    assert resp.status_code == 201
    assert resp.json()["status"] == "partial_success"
    assert resp.json()["llm_status"] == "success"


def test_pdf_draft_create_returns_503_when_pdf_dependency_is_missing(monkeypatch):
    from app.services import pdf_draft_service

    def _fake_create(db, file):
        del db, file
        raise RuntimeError("pypdf is required for PDF validation")

    monkeypatch.setattr(pdf_draft_service, "create_pdf_draft", _fake_create)

    resp = client.post(
        "/api/ai/clarification-review/pdf-drafts",
        files=_multipart_upload("clarification.pdf", _build_pdf_bytes(page_count=1)),
    )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "pypdf is required for PDF validation"


def test_pdf_draft_infer_returns_inference_result(monkeypatch):
    from app.services import pdf_draft_service

    inference_result = {
        "fields": {
            "requirement_text": {"value": "推断后的需求摘要", "evidence": "综合判断"},
            "current_surface_flow": {"value": "", "evidence": ""},
            "involved_modules": {"value": "", "evidence": ""},
            "known_background": {"value": "", "evidence": ""},
            "unknowns": {"value": "仍需确认审批驳回通知", "evidence": "基于严格提取补充"},
        },
        "conflicts": [],
    }

    def _fake_infer(db, draft_id):
        del db
        return ClarificationReviewPdfDraft(
            id=draft_id,
            file_name="clarification.pdf",
            file_size_bytes=12345,
            page_count=7,
            status="success",
            llm_status="success",
            llm_provider="openai",
            llm_message=None,
            infer_llm_status="success",
            infer_llm_provider="openai",
            infer_llm_message=None,
            strict_result_json=None,
            inference_result_json=json.dumps(inference_result, ensure_ascii=False),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

    monkeypatch.setattr(pdf_draft_service, "infer_pdf_draft", _fake_infer)

    resp = client.post("/api/ai/clarification-review/pdf-drafts/2001/infer")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == 2001
    assert payload["infer_llm_status"] == "success"
    assert payload["inference_result"]["fields"]["unknowns"]["value"] == "仍需确认审批驳回通知"


def test_pdf_draft_get_and_infer_return_404_when_expired():
    db = SessionLocal()
    try:
        draft = ClarificationReviewPdfDraft(
            file_name="expired.pdf",
            file_size_bytes=128,
            page_count=1,
            status="success",
            llm_status="success",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        draft_id = draft.id
    finally:
        db.close()

    get_resp = client.get(f"/api/ai/clarification-review/pdf-drafts/{draft_id}")
    infer_resp = client.post(f"/api/ai/clarification-review/pdf-drafts/{draft_id}/infer")

    assert get_resp.status_code == 404
    assert get_resp.json()["detail"] == "pdf draft not found"
    assert infer_resp.status_code == 404
    assert infer_resp.json()["detail"] == "pdf draft not found"


def test_analyze_accepts_missing_pdf_draft_and_marks_source_meta(monkeypatch):
    from app.services import clarification_review_service

    def _fake_analyze(db, payload, llm_client=None):
        del llm_client
        record = ClarificationReviewRecord(
            input_payload_json=json.dumps(
                {
                    "requirement_text": payload.requirement_text,
                    "current_surface_flow": payload.current_surface_flow,
                    "involved_modules": payload.involved_modules,
                    "known_background": payload.known_background,
                    "unknowns": payload.unknowns,
                },
                ensure_ascii=False,
            ),
            rule_text=payload.rule_text,
            result_json=json.dumps(clarification_review_service._empty_result(), ensure_ascii=False),
            llm_status="failed",
            llm_provider=None,
            llm_message="skip llm",
            source_draft_id=payload.source_draft_id,
            source_meta_json=json.dumps(
                {
                    "source_kind": "pdf_draft",
                    "draft_id": payload.source_draft_id,
                    "file_name": None,
                    "draft_created_at": None,
                    "draft_expired": True,
                    "applied_fields": payload.applied_fields,
                },
                ensure_ascii=False,
            ),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    monkeypatch.setattr(clarification_review_service, "analyze_clarification_review", _fake_analyze)

    resp = client.post(
        "/api/ai/clarification-review/analyze",
        json={
            "requirement_text": "来自 PDF 的需求",
            "current_surface_flow": "",
            "involved_modules": "",
            "known_background": "",
            "unknowns": "",
            "rule_text": "按结构化结果输出",
            "source_draft_id": 987654,
            "applied_fields": ["requirement_text"],
        },
    )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["source_meta"]["source_kind"] == "pdf_draft"
    assert payload["source_meta"]["draft_id"] == 987654
    assert payload["source_meta"]["draft_expired"] is True
    assert payload["source_meta"]["applied_fields"] == ["requirement_text"]
