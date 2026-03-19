import importlib


def _reload_ai_parser_module():
    import app.services.ai_parser as ai_parser_module

    return importlib.reload(ai_parser_module)


class _FakeLLMClient:
    def __init__(self, payload=None, should_raise=False):
        self.payload = payload or {
            "nodes": [
                {"id": "n1", "type": "root", "content": "用户进入充值页", "parent_id": None},
                {"id": "n2", "type": "condition", "content": "选择交易类型", "parent_id": "n1"},
            ]
        }
        self.should_raise = should_raise
        self.calls = []

    def chat_with_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if self.should_raise:
            raise RuntimeError("llm unavailable")
        return self.payload


def test_parse_requirement_text_prefers_llm_output(monkeypatch):
    module = _reload_ai_parser_module()
    fake_client = _FakeLLMClient()
    monkeypatch.setenv("AI_PARSE_PROVIDER", "llm")
    monkeypatch.setattr(module, "LLMClient", lambda: fake_client)

    result = module.parse_requirement_text("充值流程需求")

    assert len(fake_client.calls) == 1
    assert result["analysis_mode"] == "llm"
    assert result["llm_status"] == "success"
    assert result["nodes"][0]["content"] == "用户进入充值页"
    assert result["nodes"][1]["parent_id"] == "n1"


def test_parse_requirement_text_returns_empty_result_when_llm_fails(monkeypatch):
    module = _reload_ai_parser_module()
    monkeypatch.setenv("AI_PARSE_PROVIDER", "llm")
    monkeypatch.setattr(module, "LLMClient", lambda: _FakeLLMClient(should_raise=True))

    result = module.parse_requirement_text("如果用户未实名，则禁止充值")

    assert result["analysis_mode"] == "llm_failed"
    assert result["llm_status"] == "failed"
    assert result["nodes"] == []
    assert result["risks"] == []


def test_parse_requirement_text_accepts_decision_tree_payload_shape(monkeypatch):
    module = _reload_ai_parser_module()
    fake_client = _FakeLLMClient(
        payload={
            "decision_tree": {
                "nodes": [
                    {"nodeId": "root_1", "nodeType": "根节点", "text": "用户进入充值页"},
                    {"nodeId": "c_1", "nodeType": "条件", "text": "用户已实名", "parentId": "root_1"},
                ]
            }
        }
    )
    monkeypatch.setenv("AI_PARSE_PROVIDER", "llm")
    monkeypatch.setattr(module, "LLMClient", lambda: fake_client)

    result = module.parse_requirement_text("充值流程需求")

    assert result["analysis_mode"] == "llm"
    assert result["llm_status"] == "success"
    assert result["nodes"][0]["id"] == "root_1"
    assert result["nodes"][0]["type"] == "root"
    assert result["nodes"][1]["parent_id"] == "root_1"
