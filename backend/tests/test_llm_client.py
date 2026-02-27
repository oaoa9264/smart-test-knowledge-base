import importlib

import pytest


class _FakeResponse:
    def __init__(self, *, status_code=200, lines=None, json_payload=None, text=""):
        self.status_code = status_code
        self._lines = lines or []
        self._json_payload = json_payload
        self.text = text

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line

    def json(self):
        if self._json_payload is None:
            raise ValueError("no json body")
        return self._json_payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def stream(self, method, url, headers, json, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return self.response

    def close(self):
        return None


def _reload_llm_client_module():
    import app.services.llm_client as llm_client_module

    return importlib.reload(llm_client_module)


def test_chat_with_json_uses_sse_payload_and_parses_response(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    module = _reload_llm_client_module()
    client = module.LLMClient()

    response = _FakeResponse(
        lines=[
            'data: {"choices":[{"delta":{"content":"{\\"result\\":\\"ok\\","}}]}',
            'data: {"choices":[{"delta":{"content":"\\"count\\":2}"}}]}',
            "data: [DONE]",
        ]
    )
    fake_session = _FakeSession(response)
    monkeypatch.setattr(client, "_make_client", lambda: fake_session)

    parsed = client.chat_with_json(system_prompt="system", user_prompt="user")

    assert parsed == {"result": "ok", "count": 2}
    assert len(fake_session.calls) == 1
    payload = fake_session.calls[0]["json"]
    assert fake_session.calls[0]["method"] == "POST"
    assert payload["model"] == "glm-4.7"
    assert payload["max_tokens"] == 6000
    assert payload["temperature"] == 0.3
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    assert fake_session.calls[0]["headers"]["Authorization"] == "Bearer test-key"


def test_chat_with_json_can_extract_json_from_wrapped_text(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    module = _reload_llm_client_module()
    client = module.LLMClient()

    response = _FakeResponse(
        lines=[
            'data: {"choices":[{"delta":{"content":"模型输出如下：\\n```json\\n{\\"result\\":\\"ok\\",\\"count\\":2}\\n```"}}]}',
            "data: [DONE]",
        ]
    )
    fake_session = _FakeSession(response)
    monkeypatch.setattr(client, "_make_client", lambda: fake_session)

    parsed = client.chat_with_json(system_prompt="system", user_prompt="user")

    assert parsed["result"] == "ok"
    assert parsed["count"] == 2


def test_chat_with_vision_returns_joined_stream_text(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    module = _reload_llm_client_module()
    client = module.LLMClient()

    response = _FakeResponse(
        lines=[
            'data: {"choices":[{"delta":{"content":"第一段"}}]}',
            'data: {"choices":[{"delta":{"content":"第二段"}}]}',
            "data: [DONE]",
        ]
    )
    fake_session = _FakeSession(response)
    monkeypatch.setattr(client, "_make_client", lambda: fake_session)

    text = client.chat_with_vision(
        system_prompt="system",
        user_content=[{"type": "text", "text": "analyze"}],
    )

    assert text == "第一段第二段"


def test_sse_http_error_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    module = _reload_llm_client_module()
    client = module.LLMClient()

    response = _FakeResponse(
        status_code=401,
        json_payload={"error": {"message": "invalid key"}},
    )
    fake_session = _FakeSession(response)
    monkeypatch.setattr(client, "_make_client", lambda: fake_session)

    with pytest.raises(RuntimeError, match="HTTP 401"):
        client.chat_with_json(system_prompt="system", user_prompt="user")
