import json

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.core.database import engine
from app.main import app
from app.schemas.clarification_review import ClarificationReviewRecordRead
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
