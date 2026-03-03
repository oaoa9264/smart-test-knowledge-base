import io
import sys
import types
from uuid import uuid4

import pytest

from app.models.entities import NodeStatus, NodeType, RiskLevel, RuleNode
from app.services.testcase_importer import (
    ParsedTestCase,
    parse_testcases_from_excel,
    parse_testcases_from_upload,
    parse_testcases_from_xmind,
)
from app.services.testcase_matcher import MatchResult, TestCaseMatcher as _TestCaseMatcher


def _build_node(node_id: str, content: str) -> RuleNode:
    return RuleNode(
        id=node_id,
        requirement_id=1,
        parent_id=None,
        node_type=NodeType.condition,
        content=content,
        risk_level=RiskLevel.medium,
        status=NodeStatus.active,
    )


def test_parse_excel_can_detect_header_and_rows():
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["说明", "忽略", "忽略"])
    sheet.append(["用例标题", "执行步骤", "预期结果"])
    sheet.append(["登录成功", "输入正确账号密码", "进入首页"])
    sheet.append(["登录失败", "输入错误密码", "提示错误"])

    output = io.BytesIO()
    workbook.save(output)

    rows = parse_testcases_from_excel(output.getvalue())
    assert len(rows) == 2
    assert rows[0].title == "登录成功"
    assert rows[0].steps == "输入正确账号密码"
    assert rows[0].expected_result == "进入首页"


def test_parse_xmind_supports_nested_topics(monkeypatch):
    fake_module = types.SimpleNamespace(
        xmind_to_dict=lambda _: [
            {
                "topic": {
                    "title": "登录流程",
                    "children": {
                        "attached": [
                            {
                                "title": "账号登录",
                                "children": {
                                    "attached": [
                                        {"title": "登录成功"},
                                        {"title": "步骤：输入账号密码"},
                                        {"title": "预期：进入首页"},
                                    ]
                                },
                            }
                        ]
                    },
                }
            }
        ]
    )
    monkeypatch.setitem(sys.modules, "xmindparser", fake_module)

    rows = parse_testcases_from_xmind(b"fake-xmind")
    assert len(rows) == 3
    assert any(case.title == "账号登录 - 登录成功" for case in rows)


def test_parse_upload_rejects_unsupported_type():
    with pytest.raises(ValueError, match="unsupported file type"):
        parse_testcases_from_upload("cases.txt", b"hello")


class _FakeLLM:
    def __init__(self, payload=None, should_raise=False, provider_name=None):
        self.payload = payload or {"matches": []}
        self.should_raise = should_raise
        self.provider_name = provider_name

    def chat_with_json(self, system_prompt, user_prompt):
        if self.should_raise:
            raise RuntimeError("llm unavailable")
        return self.payload

    def get_last_provider(self, method_name=None):
        if method_name == "chat_with_json":
            return self.provider_name
        return self.provider_name


def test_matcher_uses_llm_and_filters_invalid_ids():
    matcher = _TestCaseMatcher(
        llm_client=_FakeLLM(
            payload={
                "matches": [
                    {
                        "case_index": 0,
                        "matched_node_ids": ["n-1", "invalid"],
                        "confidence": "high",
                        "reason": "命中登录条件",
                    }
                ]
            },
            provider_name="openai",
        )
    )
    cases = [ParsedTestCase(title="登录成功", steps="输入账号", expected_result="进入首页", raw_text="登录成功 输入账号")]
    nodes = [_build_node("n-1", "登录成功")]

    results, mode = matcher.match_cases(parsed_cases=cases, rule_nodes=nodes)
    assert mode == "llm"
    assert len(results) == 1
    assert results[0] == MatchResult(
        case_index=0,
        matched_node_ids=["n-1"],
        confidence="high",
        reason="命中登录条件",
    )
    assert matcher.get_llm_provider() == "openai"


def test_matcher_fallbacks_to_keyword_when_llm_fails():
    matcher = _TestCaseMatcher(llm_client=_FakeLLM(should_raise=True))
    cases = [
        ParsedTestCase(
            title="支付超时重试",
            steps="提交支付并等待返回",
            expected_result="超时后进入重试",
            raw_text="支付 超时 重试",
        )
    ]
    nodes = [_build_node("n-{0}".format(uuid4().hex[:6]), "支付超时触发重试机制")]

    results, mode = matcher.match_cases(parsed_cases=cases, rule_nodes=nodes)
    assert mode == "mock_fallback"
    assert len(results[0].matched_node_ids) == 1
    assert results[0].confidence in ["low", "medium", "high"]
    assert matcher.get_llm_provider() is None
