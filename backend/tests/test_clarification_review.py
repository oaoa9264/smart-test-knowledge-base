import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.core.database import SessionLocal, engine
from app.main import app
from app.models.entities import ClarificationReviewPdfDraft
from app.schemas.clarification_review import (
    ClarificationReviewAnalyzeRequest,
    ClarificationReviewRecordRead,
    ClarificationReviewRecordSummaryRead,
)
from app.services import clarification_review_service


client = TestClient(app)


def test_clarification_review_table_exists():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert "clarification_review_records" in table_names


def test_clarification_review_analyze_endpoint_exists():
    resp = client.post(
        "/api/ai/clarification-review/analyze",
        json={
            "requirement_text": "老项目需求原文",
            "current_surface_flow": "",
            "involved_modules": "",
            "known_background": "",
            "unknowns": "",
            "rule_text": "按结构化结果输出",
        },
    )

    assert resp.status_code != 404


def test_clarification_review_records_endpoint_exists():
    resp = client.get("/api/ai/clarification-review/records")

    assert resp.status_code != 404


def test_clarification_review_analyze_requires_rule_text():
    resp = client.post(
        "/api/ai/clarification-review/analyze",
        json={
            "requirement_text": "老项目需求原文",
            "current_surface_flow": "",
            "involved_modules": "",
            "known_background": "",
            "unknowns": "",
            "rule_text": "",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "rule_text is required"


def test_clarification_review_analyze_requires_known_info():
    resp = client.post(
        "/api/ai/clarification-review/analyze",
        json={
            "requirement_text": "",
            "current_surface_flow": "",
            "involved_modules": "",
            "known_background": "",
            "unknowns": "",
            "rule_text": "按结构化结果输出",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "at least one known info field is required"


def test_clarification_review_analyze_persists_structured_result_and_provider(monkeypatch):
    class _FakeLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            assert "严格输出 JSON 对象" in system_prompt
            assert "老项目需求原文" in user_prompt
            return {
                "likely_historical_rules": [{"rule": "状态不可回退", "reason": "老流程常见约束"}],
                "missing_critical_rules": [{"rule": "状态迁移条件", "why_missing": "需求未写", "impact": "无法准确评估"}],
                "priority_questions_by_role": {
                    "product": [{"question": "回退是否允许", "why_ask": "确认核心流程", "risk_if_unasked": "实现偏差"}],
                    "development": [{"question": "是否有旧字段兼容", "why_ask": "避免接口破坏", "risk_if_unasked": "线上回归"}],
                    "testing": [{"question": "是否存在历史灰度开关", "why_ask": "补边界用例", "risk_if_unasked": "漏测"}],
                    "operations": [{"question": "是否依赖运营配置", "why_ask": "确认线上入口", "risk_if_unasked": "发布后不可用"}],
                },
                "known_requirement_gaps": [{"gap": "回滚条件缺失", "reason": "流程描述不完整", "impact": "验收标准不稳定"}],
                "risk_assumptions": [{"assumption": "状态机已存在", "basis": "老项目常见", "risk": "真实实现可能不同"}],
                "summary_markdown": "# 摘要\n\n- 需要优先追问状态规则",
            }

        def get_last_provider(self, method_name=None):
            assert method_name == "chat_with_json"
            return "openai"

    monkeypatch.setattr(clarification_review_service, "LLMClient", lambda: _FakeLLMClient())

    resp = client.post(
        "/api/ai/clarification-review/analyze",
        json={
            "requirement_text": "老项目需求原文",
            "current_surface_flow": "页面提交后进入审核",
            "involved_modules": "审批中心",
            "known_background": "历史项目已运行多年",
            "unknowns": "不知道状态机规则",
            "rule_text": "按结构化结果输出",
        },
    )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["llm_status"] == "success"
    assert payload["llm_provider"] == "openai"
    assert payload["result"]["likely_historical_rules"][0]["rule"] == "状态不可回退"
    assert payload["result"]["priority_questions_by_role"]["开发"][0]["question"] == "是否有旧字段兼容"
    assert payload["result"]["configured_roles"] == ["产品", "开发", "测试", "运营/业务"]
    assert payload["result"]["role_descriptors"][0] == {"key": "产品", "source": "rule_text"}

    list_resp = client.get("/api/ai/clarification-review/records")
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["id"] == payload["id"]
    assert list_resp.json()[0]["requirement_text_preview"] == "老项目需求原文"

    detail_resp = client.get(f"/api/ai/clarification-review/records/{payload['id']}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["input_payload"]["unknowns"] == "不知道状态机规则"
    assert detail_resp.json()["result"]["summary_markdown"].startswith("# 摘要")


def test_clarification_review_analyze_saves_failure_meta(monkeypatch):
    class _FailingLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            del system_prompt, user_prompt
            raise RuntimeError("boom")

    monkeypatch.setattr(clarification_review_service, "LLMClient", lambda: _FailingLLMClient())

    resp = client.post(
        "/api/ai/clarification-review/analyze",
        json={
            "requirement_text": "老项目需求原文",
            "current_surface_flow": "",
            "involved_modules": "",
            "known_background": "",
            "unknowns": "",
            "rule_text": "按结构化结果输出",
        },
    )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["llm_status"] == "failed"
    assert payload["llm_provider"] is None
    assert payload["llm_message"] == "boom"
    assert payload["result"]["likely_historical_rules"] == []
    assert payload["result"]["priority_questions_by_role"]["产品"] == []
    assert payload["result"]["configured_roles"] == ["产品", "开发", "测试", "运营/业务"]


def test_clarification_review_records_respect_limit_and_desc_order(monkeypatch):
    class _FakeLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            del system_prompt, user_prompt
            return {
                "likely_historical_rules": [],
                "missing_critical_rules": [],
                "priority_questions_by_role": {},
                "known_requirement_gaps": [],
                "risk_assumptions": [],
                "summary_markdown": "",
            }

        def get_last_provider(self, method_name=None):
            del method_name
            return "zhipu"

    monkeypatch.setattr(clarification_review_service, "LLMClient", lambda: _FakeLLMClient())

    created_ids = []
    for index in range(3):
        resp = client.post(
            "/api/ai/clarification-review/analyze",
            json={
                "requirement_text": f"需求 {index}",
                "current_surface_flow": "",
                "involved_modules": "",
                "known_background": "",
                "unknowns": "",
                "rule_text": "按结构化结果输出",
            },
        )
        assert resp.status_code == 201
        created_ids.append(resp.json()["id"])

    list_resp = client.get("/api/ai/clarification-review/records?limit=2")
    assert list_resp.status_code == 200
    assert [item["id"] for item in list_resp.json()] == created_ids[::-1][:2]


def test_clarification_review_detail_returns_404_when_missing():
    resp = client.get("/api/ai/clarification-review/records/999")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "record not found"


def test_clarification_review_analyze_uses_rule_text_roles_and_marks_llm_extra(monkeypatch):
    custom_rule_text = """
1. 输出“必须优先确认的问题清单”，并按角色分类：
   - 问产品
   - 问开发
   - 问财务
""".strip()

    class _FakeLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            assert "你必须包含以下角色（即使某角色没有问题，也要返回空数组）：产品、开发、财务" in system_prompt
            assert "只能包含 product、development、testing、operations 四个键" not in system_prompt
            assert custom_rule_text in user_prompt
            return {
                "priority_questions_by_role": {
                    "产品": [{"question": "口径是否变更", "why_ask": "影响范围", "risk_if_unasked": "验收偏差"}],
                    "财务": [{"question": "是否涉及结算", "why_ask": "确认资金链路", "risk_if_unasked": "上线后对账异常"}],
                    "法务": [{"question": "是否有合规要求", "why_ask": "识别监管要求", "risk_if_unasked": "合规风险"}],
                }
            }

        def get_last_provider(self, method_name=None):
            del method_name
            return "openai"

    monkeypatch.setattr(clarification_review_service, "LLMClient", lambda: _FakeLLMClient())

    resp = client.post(
        "/api/ai/clarification-review/analyze",
        json={
            "requirement_text": "涉及付款审批的老项目需求",
            "current_surface_flow": "",
            "involved_modules": "",
            "known_background": "",
            "unknowns": "",
            "rule_text": custom_rule_text,
        },
    )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["result"]["configured_roles"] == ["产品", "开发", "财务"]
    assert payload["result"]["priority_questions_by_role"]["开发"] == []
    assert payload["result"]["priority_questions_by_role"]["财务"][0]["question"] == "是否涉及结算"
    assert payload["result"]["role_descriptors"] == [
        {"key": "产品", "source": "rule_text"},
        {"key": "开发", "source": "rule_text"},
        {"key": "财务", "source": "rule_text"},
        {"key": "法务", "source": "llm_extra"},
    ]


def test_clarification_review_analyze_falls_back_to_default_roles_when_rule_text_unparseable(monkeypatch):
    class _FakeLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            del user_prompt
            assert "你必须包含以下角色（即使某角色没有问题，也要返回空数组）：产品、开发、测试、运营/业务" in system_prompt
            return {"priority_questions_by_role": {}}

        def get_last_provider(self, method_name=None):
            del method_name
            return "zhipu"

    monkeypatch.setattr(clarification_review_service, "LLMClient", lambda: _FakeLLMClient())

    resp = client.post(
        "/api/ai/clarification-review/analyze",
        json={
            "requirement_text": "老项目需求原文",
            "current_surface_flow": "",
            "involved_modules": "",
            "known_background": "",
            "unknowns": "",
            "rule_text": "请给我一些追问建议，但我没有按固定格式写角色。",
        },
    )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["result"]["configured_roles"] == ["产品", "开发", "测试", "运营/业务"]
    assert [item["key"] for item in payload["result"]["role_descriptors"]] == ["产品", "开发", "测试", "运营/业务"]
    assert payload["result"]["priority_questions_by_role"]["测试"] == []


def test_clarification_review_schema_parses_json_strings():
    record = ClarificationReviewRecordRead(
        id=1,
        input_payload=json.dumps(
            {
                "requirement_text": "老项目需求原文",
                "current_surface_flow": "",
                "involved_modules": "",
                "known_background": "",
                "unknowns": "状态机未知",
            },
            ensure_ascii=False,
        ),
        rule_text="按结构化结果输出",
        result=json.dumps(
            {
                "likely_historical_rules": [{"rule": "状态不可回退", "reason": "老流程常见约束"}],
                "missing_critical_rules": [],
                "priority_questions_by_role": {
                    "产品": [],
                    "开发": [],
                    "测试": [],
                    "运营/业务": [],
                },
                "configured_roles": ["产品", "开发", "测试", "运营/业务"],
                "role_descriptors": [
                    {"key": "产品", "source": "rule_text"},
                    {"key": "开发", "source": "rule_text"},
                    {"key": "测试", "source": "rule_text"},
                    {"key": "运营/业务", "source": "rule_text"},
                ],
                "known_requirement_gaps": [],
                "risk_assumptions": [],
                "summary_markdown": "",
                "llm_status": "success",
                "llm_provider": "openai",
                "llm_message": None,
            },
            ensure_ascii=False,
        ),
        llm_status="success",
        llm_provider="openai",
        llm_message=None,
        created_at="2026-04-10T00:00:00",
    )

    assert record.input_payload.unknowns == "状态机未知"
    assert record.result.likely_historical_rules[0].rule == "状态不可回退"
    assert record.result.configured_roles == ["产品", "开发", "测试", "运营/业务"]


def test_clarification_review_summary_schema_parses_source_meta_json_string():
    record = ClarificationReviewRecordSummaryRead(
        id=2,
        llm_status="success",
        llm_provider="openai",
        created_at="2026-04-10T00:00:00",
        requirement_text_preview="老项目需求原文",
        source_meta=json.dumps(
            {
                "source_kind": "pdf_draft",
                "draft_id": 123,
                "file_name": "clarification.pdf",
                "draft_created_at": "2026-04-10T00:00:00",
                "draft_expired": False,
                "applied_fields": ["requirement_text"],
            },
            ensure_ascii=False,
        ),
    )

    assert record.source_meta is not None
    assert record.source_meta.draft_id == 123
    assert record.source_meta.applied_fields == ["requirement_text"]


def test_build_pdf_supplement_formats_applied_fields_and_evidence_sources():
    draft = ClarificationReviewPdfDraft(
        id=2001,
        file_name="clarification.pdf",
        file_size_bytes=12345,
        page_count=2,
        status="success",
        llm_status="success",
        full_text_json=json.dumps({"pages": ["第一页原文", "第二页原文"]}, ensure_ascii=False),
        vision_notes_json=json.dumps(["图里有审批分支", "表格里有金额阈值"], ensure_ascii=False),
        strict_result_json=json.dumps(
            {
                "fields": {
                    "requirement_text": {"value": "审批通过后发送通知", "evidence": "第 1 页写明审批通过后通知"},
                    "unknowns": {"value": "驳回是否通知", "evidence": "第 2 页未写驳回通知"},
                },
                "conflicts": [
                    {"field": "current_surface_flow", "description": "流程图显示驳回回退，但正文未说明", "evidence": "流程图与正文不一致"}
                ],
            },
            ensure_ascii=False,
        ),
        inference_result_json=json.dumps(
            {
                "fields": {
                    "unknowns": {"value": "可能需要短信撤回", "evidence": "基于通知流程归纳，需进一步确认"}
                },
                "conflicts": [],
            },
            ensure_ascii=False,
        ),
        expires_at=datetime.utcnow() + timedelta(hours=24),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    supplement = clarification_review_service._build_pdf_supplement(
        draft=draft,
        applied_fields=["requirement_text"],
    )

    assert "【PDF 补充参考材料】" in supplement
    assert "文档内部冲突（strict extraction）" in supplement
    assert "字段直接证据（strict extraction）" in supplement
    assert "字段补充推断依据（inference extraction，仅供参考）" in supplement
    assert "需求原文（已应用到当前表单）" in supplement
    assert "我暂时不知道的内容（未应用到当前表单，仅供参考）" in supplement
    assert "图里有审批分支" in supplement
    assert "[第 1 页]" in supplement
    assert "基于通知流程归纳，需进一步确认" in supplement


def test_clarification_review_analyze_appends_pdf_supplement_for_valid_draft(monkeypatch):
    db = SessionLocal()
    try:
        draft = ClarificationReviewPdfDraft(
            file_name="clarification.pdf",
            file_size_bytes=12345,
            page_count=1,
            status="success",
            llm_status="success",
            full_text_json=json.dumps({"pages": ["这里是 PDF 原文"]}, ensure_ascii=False),
            vision_notes_json=json.dumps(["流程图显示审批后发站内信"], ensure_ascii=False),
            strict_result_json=json.dumps(
                {
                    "fields": {
                        "requirement_text": {"value": "审批通过后发送通知", "evidence": "第 1 页正文明确描述"}
                    },
                    "conflicts": [],
                },
                ensure_ascii=False,
            ),
            inference_result_json=json.dumps(
                {
                    "fields": {
                        "unknowns": {"value": "驳回通知待确认", "evidence": "基于审批流归纳"}
                    },
                    "conflicts": [],
                },
                ensure_ascii=False,
            ),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        class _FakeLLMClient:
            def chat_with_json(self, system_prompt, user_prompt):
                assert "如果输入包含「PDF 补充参考材料」" in system_prompt
                assert "【PDF 补充参考材料】" in user_prompt
                assert "流程图显示审批后发站内信" in user_prompt
                assert "字段直接证据（strict extraction）" in user_prompt
                return {"priority_questions_by_role": {}}

            def get_last_provider(self, method_name=None):
                del method_name
                return "openai"

        record = clarification_review_service.analyze_clarification_review(
            db=db,
            payload=ClarificationReviewAnalyzeRequest(
                requirement_text="表单里的最终需求",
                current_surface_flow="提交后审核",
                involved_modules="审批中心",
                known_background="老项目",
                unknowns="驳回通知未知",
                rule_text="按结构化结果输出",
                source_draft_id=draft.id,
                applied_fields=["requirement_text"],
            ),
            llm_client=_FakeLLMClient(),
        )

        assert record.llm_status == "success"
    finally:
        db.close()


def test_clarification_review_detail_preserves_pdf_draft_source_for_v2_records(monkeypatch):
    db = SessionLocal()
    try:
        draft = ClarificationReviewPdfDraft(
            file_name="clarification.pdf",
            file_size_bytes=1024,
            page_count=1,
            status="success",
            llm_status="success",
            expires_at=datetime.utcnow() + timedelta(hours=24),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
    finally:
        db.close()

    class _FakeLLMClient:
        def chat_with_json(self, system_prompt, user_prompt):
            del system_prompt, user_prompt
            return {
                "result_version": 2,
                "inferred_items": [
                    {
                        "statement": "短信模板可能来自 PDF 草稿",
                        "evidence": "PDF 草稿里明确提到了旧模板编号",
                        "source_type": "pdf_draft",
                    }
                ],
                "assumption_items": [],
                "priority_questions_by_role": {},
                "known_requirement_gaps": [],
                "summary_markdown": "## 摘要\n\n- 需要确认短信模板规则",
            }

        def get_last_provider(self, method_name=None):
            del method_name
            return "openai"

    monkeypatch.setattr(clarification_review_service, "LLMClient", lambda: _FakeLLMClient())

    analyze_resp = client.post(
        "/api/ai/clarification-review/analyze",
        json={
            "requirement_text": "涉及短信通知的审批需求",
            "current_surface_flow": "",
            "involved_modules": "",
            "known_background": "",
            "unknowns": "",
            "rule_text": "按结构化结果输出",
            "source_draft_id": draft.id,
            "applied_fields": [],
        },
    )

    assert analyze_resp.status_code == 201
    payload = analyze_resp.json()
    assert payload["result"]["result_version"] == 2
    assert payload["result"]["inferred_items"][0]["source_type"] == "pdf_draft"

    detail_resp = client.get(f"/api/ai/clarification-review/records/{payload['id']}")

    assert detail_resp.status_code == 200
    assert detail_resp.json()["result"]["inferred_items"][0]["source_type"] == "pdf_draft"


def test_build_source_meta_marks_expired_pdf_draft_as_expired():
    db = SessionLocal()
    try:
        draft = ClarificationReviewPdfDraft(
            file_name="expired.pdf",
            file_size_bytes=100,
            page_count=1,
            status="success",
            llm_status="success",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            created_at=datetime.utcnow() - timedelta(hours=1),
            updated_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        meta = clarification_review_service._build_source_meta(
            db,
            ClarificationReviewAnalyzeRequest(
                requirement_text="老项目需求原文",
                current_surface_flow="",
                involved_modules="",
                known_background="",
                unknowns="",
                rule_text="按结构化结果输出",
                source_draft_id=draft.id,
                applied_fields=["requirement_text"],
            ),
        )

        assert meta["draft_expired"] is True
        assert meta["file_name"] is None
    finally:
        db.close()


def test_normalize_clarification_review_result_v2_derives_legacy_fields():
    normalized = clarification_review_service.normalize_clarification_review_result(
        {
            "result_version": 2,
            "inferred_items": [
                {
                    "statement": "审批流可能存在金额阈值分级",
                    "evidence": "审批中心老项目通常按金额区间走不同审批层级",
                    "source_type": "input_text",
                }
            ],
            "assumption_items": [
                {
                    "assumption": "驳回后已发通知需要撤回",
                    "basis": "输入只描述了通过通知，未覆盖驳回场景",
                    "risk": "若不撤回会出现错误通知",
                }
            ],
            "priority_questions_by_role": {
                "产品": [
                    {
                        "question": "驳回后通知如何处理？",
                        "why_ask": "关系到主流程状态一致性",
                        "risk_if_unasked": "开发无法确定驳回分支处理",
                        "required_output": "请给出驳回通知处理规则表",
                        "answer_format": "table",
                    }
                ]
            },
            "known_requirement_gaps": [
                {
                    "gap": "驳回后的通知处理规则缺失",
                    "gap_type": "rule_missing",
                    "reason": "需求没有定义驳回后已发通知是否撤回",
                    "impact": "开发和测试无法确认驳回链路",
                    "priority": "P0",
                    "blocking_reason": "驳回是主流程分支，不确认通知策略无法实现",
                }
            ],
            "summary_markdown": "## 摘要\n\n- 需要先确认驳回通知规则",
        },
        "1. 输出\"必须优先确认的问题清单\"\n   - 问产品\n   - 问开发",
    )

    assert normalized["result_version"] == 2
    assert normalized["inferred_items"][0]["source_type"] == "input_text"
    assert normalized["likely_historical_rules"][0] == {
        "rule": "审批流可能存在金额阈值分级",
        "reason": "审批中心老项目通常按金额区间走不同审批层级",
    }
    assert normalized["risk_assumptions"][0]["assumption"] == "驳回后已发通知需要撤回"
    assert normalized["missing_critical_rules"][0] == {
        "rule": "驳回后的通知处理规则缺失",
        "why_missing": "需求没有定义驳回后已发通知是否撤回",
        "impact": "开发和测试无法确认驳回链路",
    }
    assert normalized["priority_questions_by_role"]["产品"][0]["required_output"] == "请给出驳回通知处理规则表"
    assert normalized["priority_questions_by_role"]["产品"][0]["answer_format"] == "table"


def test_normalize_clarification_review_result_v2_rebalances_priorities_and_validates_fields():
    normalized = clarification_review_service.normalize_clarification_review_result(
        {
            "result_version": 2,
            "inferred_items": [
                {
                    "statement": "可能沿用老的短信模板体系",
                    "evidence": "通知模块仍然是旧系统",
                    "source_type": "pdf_draft",
                }
            ],
            "assumption_items": [],
            "priority_questions_by_role": {
                "产品": [
                    {
                        "question": "最终展示文案如何映射？",
                        "why_ask": "影响状态文案输出",
                        "risk_if_unasked": "前端展示与审核动作不一致",
                        "required_output": "请给出状态映射说明",
                        "answer_format": "matrix",
                    }
                ]
            },
            "known_requirement_gaps": [
                {
                    "gap": "缺陷1",
                    "gap_type": "rule_missing",
                    "reason": "原因1",
                    "impact": "影响1",
                    "priority": "P0",
                    "blocking_reason": "原因1",
                },
                {
                    "gap": "缺陷2",
                    "gap_type": "bad_type",
                    "reason": "原因2",
                    "impact": "影响2",
                    "priority": "P0",
                    "blocking_reason": "这是一个足够长的阻塞说明",
                },
                {
                    "gap": "缺陷3",
                    "gap_type": "process_gap",
                    "reason": "原因3",
                    "impact": "影响3",
                    "priority": "P0",
                    "blocking_reason": "这是另一个足够长的阻塞说明",
                },
                {
                    "gap": "缺陷4",
                    "gap_type": "process_gap",
                    "reason": "原因4",
                    "impact": "影响4",
                    "priority": "oops",
                    "blocking_reason": "这条不会被使用",
                },
            ],
            "summary_markdown": "",
        },
        "1. 输出\"必须优先确认的问题清单\"\n   - 问产品",
    )

    assert normalized["inferred_items"][0]["source_type"] == "llm_inference"
    assert normalized["priority_questions_by_role"]["产品"][0]["answer_format"] == "text"
    assert normalized["known_requirement_gaps"][0]["priority"] == "P1"
    assert normalized["known_requirement_gaps"][1]["gap_type"] == "logic_gap"
    assert [item["priority"] for item in normalized["known_requirement_gaps"]] == ["P1", "P0", "P1", "P1"]
