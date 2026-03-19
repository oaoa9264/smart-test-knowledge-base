from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.entities import (
    InputType,
    Project,
    Requirement,
    RequirementInput,
    SourceType,
)
from app.services import effective_requirement_service


client = TestClient(app)


def _create_requirement(
    raw_text: str = "用户提交表单并提交申请。",
    extra_inputs=None,
) -> int:
    db = SessionLocal()
    try:
        project = Project(
            name="normalized-{0}".format(uuid4().hex[:8]),
            description="normalized doc test",
        )
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="规范化需求文档测试",
            raw_text=raw_text,
            source_type=SourceType.prd,
        )
        db.add(requirement)
        db.flush()

        if extra_inputs:
            for input_type, content, source_label in extra_inputs:
                db.add(
                    RequirementInput(
                        requirement_id=requirement.id,
                        input_type=InputType(input_type),
                        content=content,
                        source_label=source_label,
                    )
                )

        db.commit()
        return requirement.id
    finally:
        db.close()


def test_preview_without_snapshot_uses_live_inputs_and_pending_note():
    requirement_id = _create_requirement(
        raw_text="用户提交提现申请。",
        extra_inputs=[
            ("pm_addendum", "主流程：用户输入金额后提交申请。", "pm"),
            ("review_note", "约束：单笔提现金额不能超过 5 万。", "review"),
        ],
    )

    class _FakeLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            del system_prompt
            assert "【最新有效需求快照】" not in user_prompt
            return {
                "markdown": "# 规范化需求文档测试\n\n## 1. 需求背景与目标\n\n用户提交提现申请。\n\n## 2. 主流程\n\n用户输入金额后提交申请。\n\n## 3. 异常与边界场景\n\n暂无明确内容。\n\n## 4. 约束与兼容性\n\n单笔提现金额不能超过 5 万。\n\n## 5. 待确认事项\n\n暂无明确内容。\n"
            }

        def get_last_provider(self, method_name=None):
            del method_name
            return "fake"

    old_factory = effective_requirement_service.LLMClient
    try:
        from app.services import normalized_requirement_doc_service as normalized_doc_module
        normalized_doc_module.LLMClient = lambda: _FakeLLMClient()
        resp = client.post("/api/requirements/{0}/normalized-doc/preview".format(requirement_id))
    finally:
        normalized_doc_module.LLMClient = old_factory

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["uses_fresh_snapshot"] is False
    assert payload["snapshot_stale"] is False
    assert payload["llm_status"] == "success"
    assert payload["llm_message"] is None
    assert "## 5. 待确认事项" in payload["markdown"]


def test_preview_with_fresh_snapshot_moves_non_explicit_content_to_pending(monkeypatch):
    requirement_id = _create_requirement(
        raw_text="用户提交提现申请。",
        extra_inputs=[
            ("pm_addendum", "补充：用户提交后可查看处理状态。", "pm"),
        ],
    )

    old_mock = effective_requirement_service._mock_review_analysis

    def custom_mock(raw_text, has_product_context=False):
        del raw_text, has_product_context
        return {
            "summary": "提现需求摘要",
            "fields": [
                {
                    "field_key": "goal",
                    "value": "支持用户发起提现申请，并查看处理结果。",
                    "derivation": "explicit",
                    "confidence": 0.95,
                    "source_refs": "原始需求",
                },
                {
                    "field_key": "main_flow",
                    "value": "1. 用户输入提现金额\n2. 用户提交申请\n3. 系统展示处理状态",
                    "derivation": "explicit",
                    "confidence": 0.92,
                    "source_refs": "原始需求+PM补充",
                },
                {
                    "field_key": "exceptions",
                    "value": "需确认提现失败后的提示方式。",
                    "derivation": "missing",
                    "confidence": 0.0,
                    "source_refs": "需求未提及",
                    "notes": "缺少失败提示和回退动作",
                },
                {
                    "field_key": "constraints",
                    "value": "单笔提现金额不能超过 5 万。",
                    "derivation": "explicit",
                    "confidence": 0.88,
                    "source_refs": "评审备注",
                },
                {
                    "field_key": "compatibility",
                    "value": "推断：移动端和 PC 端应保持一致。",
                    "derivation": "inferred",
                    "confidence": 0.55,
                    "source_refs": "上下文推断",
                },
            ],
            "risks": [],
        }

    db = SessionLocal()
    try:
        effective_requirement_service._mock_review_analysis = custom_mock
        effective_requirement_service.generate_review_snapshot(db=db, requirement_id=requirement_id)
    finally:
        effective_requirement_service._mock_review_analysis = old_mock
        db.close()

    captured_prompt = {}

    class _FakeLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            del system_prompt
            captured_prompt["value"] = user_prompt
            return {
                "markdown": "# 规范化需求文档测试\n\n## 1. 需求背景与目标\n\n支持用户发起提现申请，并查看处理结果。\n\n## 2. 主流程\n\n1. 用户输入提现金额\n2. 用户提交申请\n3. 系统展示处理状态\n\n## 3. 异常与边界场景\n\n暂无明确内容。\n\n## 4. 约束与兼容性\n\n单笔提现金额不能超过 5 万。\n\n## 5. 待确认事项\n\n需确认提现失败后的提示方式。\n\n推断：移动端和 PC 端应保持一致。\n"
            }

        def get_last_provider(self, method_name=None):
            del method_name
            return "fake"

    from app.services import normalized_requirement_doc_service as normalized_doc_module
    monkeypatch.setattr(normalized_doc_module, "LLMClient", lambda: _FakeLLMClient())

    resp = client.post("/api/requirements/{0}/normalized-doc/preview".format(requirement_id))

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["uses_fresh_snapshot"] is True
    assert payload["snapshot_stale"] is False
    assert payload["llm_status"] == "success"
    assert "【最新有效需求快照】" in captured_prompt["value"]
    assert "compatibility" in captured_prompt["value"]
    prefix, pending = payload["markdown"].split("## 5. 待确认事项", 1)
    assert "支持用户发起提现申请，并查看处理结果。" in prefix
    assert "单笔提现金额不能超过 5 万。" in prefix
    assert "需确认提现失败后的提示方式。" not in prefix
    assert "推断：移动端和 PC 端应保持一致。" not in prefix
    assert "需确认提现失败后的提示方式。" in pending
    assert "推断：移动端和 PC 端应保持一致。" in pending


def test_preview_with_stale_snapshot_falls_back_to_live_inputs():
    requirement_id = _create_requirement(
        raw_text="用户提交提现申请。",
        extra_inputs=[("pm_addendum", "主流程：用户输入金额后提交申请。", "pm")],
    )

    db = SessionLocal()
    try:
        effective_requirement_service.generate_review_snapshot(db=db, requirement_id=requirement_id)
        requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
        requirement.raw_text = "用户提交提现申请，系统需要展示提交结果。"
        db.commit()
    finally:
        db.close()

    captured_prompt = {}

    class _FakeLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            del system_prompt
            captured_prompt["value"] = user_prompt
            return {
                "markdown": "# 规范化需求文档测试\n\n## 1. 需求背景与目标\n\n用户提交提现申请，系统需要展示提交结果。\n\n## 2. 主流程\n\n主流程：用户输入金额后提交申请。\n\n## 3. 异常与边界场景\n\n暂无明确内容。\n\n## 4. 约束与兼容性\n\n暂无明确内容。\n\n## 5. 待确认事项\n\n暂无明确内容。\n"
            }

        def get_last_provider(self, method_name=None):
            del method_name
            return "fake"

    old_factory = effective_requirement_service.LLMClient
    try:
        from app.services import normalized_requirement_doc_service as normalized_doc_module
        normalized_doc_module.LLMClient = lambda: _FakeLLMClient()
        resp = client.post("/api/requirements/{0}/normalized-doc/preview".format(requirement_id))
    finally:
        normalized_doc_module.LLMClient = old_factory

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["uses_fresh_snapshot"] is False
    assert payload["snapshot_stale"] is True
    assert "【最新有效需求快照】" not in captured_prompt["value"]


def test_preview_endpoint_requires_post():
    requirement_id = _create_requirement(raw_text="用户提交提现申请。")

    resp = client.get("/api/requirements/{0}/normalized-doc/preview".format(requirement_id))

    assert resp.status_code == 405


def test_preview_returns_error_when_llm_fails(monkeypatch):
    requirement_id = _create_requirement(raw_text="用户提交提现申请。")

    class _FailingLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            del system_prompt, user_prompt
            raise RuntimeError("boom")

    from app.services import normalized_requirement_doc_service as normalized_doc_module
    monkeypatch.setattr(normalized_doc_module, "LLMClient", lambda: _FailingLLMClient())

    resp = client.post("/api/requirements/{0}/normalized-doc/preview".format(requirement_id))

    assert resp.status_code == 502
    assert "模型调用失败" in resp.json()["detail"]


def test_export_markdown_endpoint_removed():
    requirement_id = _create_requirement(raw_text="用户提交提现申请。")

    resp = client.get("/api/requirements/{0}/normalized-doc/export.md".format(requirement_id))

    assert resp.status_code == 404
