import importlib

import pytest


class _FakeDelta:
    def __init__(self, content=None, reasoning_content=None):
        self.content = content
        self.reasoning_content = reasoning_content


class _FakeChoice:
    def __init__(self, delta=None, message=None):
        self.delta = delta
        self.message = message


class _FakeChunk:
    def __init__(self, delta=None, message=None):
        self.choices = [_FakeChoice(delta=delta, message=message)]


class _FakeCompletions:
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        self.parent.calls.append(kwargs)
        if self.parent.raise_in_create is not None:
            raise self.parent.raise_in_create
        return iter(self.parent.chunks)


class _FakeChat:
    def __init__(self, parent):
        self.completions = _FakeCompletions(parent)


class _FakeOpenAI:
    instances = []
    chunks = []
    raise_in_create = None

    def __init__(self, *, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        self.calls = []
        self.chunks = list(_FakeOpenAI.chunks)
        self.raise_in_create = _FakeOpenAI.raise_in_create
        self.chat = _FakeChat(self)
        _FakeOpenAI.instances.append(self)


def _reload_openai_client_module():
    import app.services.openai_client as openai_client_module

    return importlib.reload(openai_client_module)


def test_openai_client_requires_api_key():
    module = _reload_openai_client_module()

    with pytest.raises(ValueError, match="api_key"):
        module.OpenAIClient(
            provider_name="main",
            api_key="",
            base_url="https://api.routin.ai/v1",
            text_model="gpt-4o",
            vision_model="gpt-4o",
            timeout=60,
            connect_timeout=10,
            max_retries=2,
            max_tokens=6000,
            temperature=0.3,
            seed=None,
        )


def test_openai_client_uses_sdk_stream_for_json(monkeypatch):
    _FakeOpenAI.instances = []
    _FakeOpenAI.raise_in_create = None
    _FakeOpenAI.chunks = [
        _FakeChunk(delta=_FakeDelta(content='{"result":"ok",')),
        _FakeChunk(delta=_FakeDelta(content='"count":2}')),
    ]

    module = _reload_openai_client_module()
    monkeypatch.setattr(module, "OpenAI", _FakeOpenAI)
    client = module.OpenAIClient(
        provider_name="main",
        api_key="openai-test-key",
        base_url="https://api.routin.ai/v1",
        text_model="gpt-4o",
        vision_model="gpt-4o",
        timeout=60,
        connect_timeout=10,
        max_retries=2,
        max_tokens=6000,
        temperature=0.3,
        seed=None,
    )

    parsed = client.chat_with_json(system_prompt="system", user_prompt="user")

    assert parsed == {"result": "ok", "count": 2}
    sdk = _FakeOpenAI.instances[0]
    assert sdk.api_key == "openai-test-key"
    assert sdk.base_url == "https://api.routin.ai/v1"

    call = sdk.calls[0]
    assert call["model"] == "gpt-4o"
    assert call["response_format"] == {"type": "json_object"}
    assert call["stream"] is True


def test_openai_client_can_derive_base_url_from_api_url(monkeypatch):
    _FakeOpenAI.instances = []
    _FakeOpenAI.raise_in_create = None
    _FakeOpenAI.chunks = [_FakeChunk(delta=_FakeDelta(content='{"ok":true}'))]

    module = _reload_openai_client_module()
    monkeypatch.setattr(module, "OpenAI", _FakeOpenAI)

    client = module.OpenAIClient(
        provider_name="main",
        api_key="openai-test-key",
        base_url="https://api.routin.ai/v1",
        text_model="gpt-4o",
        vision_model="gpt-4o",
        timeout=60,
        connect_timeout=10,
        max_retries=2,
        max_tokens=6000,
        temperature=0.3,
        seed=None,
    )
    parsed = client.chat_with_json(system_prompt="system", user_prompt="user")

    assert parsed["ok"] is True
    sdk = _FakeOpenAI.instances[0]
    assert sdk.base_url == "https://api.routin.ai/v1"
    assert client.api_url == "https://api.routin.ai/v1/chat/completions"


def test_openai_client_vision_uses_sdk_stream(monkeypatch):
    _FakeOpenAI.instances = []
    _FakeOpenAI.raise_in_create = None
    _FakeOpenAI.chunks = [
        _FakeChunk(delta=_FakeDelta(content="第一段")),
        _FakeChunk(delta=_FakeDelta(content="第二段")),
    ]

    module = _reload_openai_client_module()
    monkeypatch.setattr(module, "OpenAI", _FakeOpenAI)
    client = module.OpenAIClient(
        provider_name="main",
        api_key="openai-test-key",
        base_url="https://api.openai.com/v1",
        text_model="gpt-4o",
        vision_model="gpt-4o",
        timeout=60,
        connect_timeout=10,
        max_retries=2,
        max_tokens=6000,
        temperature=0.3,
        seed=None,
    )

    text = client.chat_with_vision(
        system_prompt="system",
        user_content=[{"type": "text", "text": "analyze"}],
    )

    assert text == "第一段第二段"
    call = _FakeOpenAI.instances[0].calls[0]
    assert call["model"] == "gpt-4o"
    assert call["messages"][1]["content"] == [{"type": "text", "text": "analyze"}]


def test_openai_client_vision_defaults_to_text_model_when_vision_model_unset(monkeypatch):
    _FakeOpenAI.instances = []
    _FakeOpenAI.raise_in_create = None
    _FakeOpenAI.chunks = [_FakeChunk(delta=_FakeDelta(content="ok"))]

    module = _reload_openai_client_module()
    monkeypatch.setattr(module, "OpenAI", _FakeOpenAI)
    client = module.OpenAIClient(
        provider_name="main",
        api_key="openai-test-key",
        base_url="https://api.openai.com/v1",
        text_model="gpt-5.3-codex",
        vision_model="gpt-5.3-codex",
        timeout=60,
        connect_timeout=10,
        max_retries=2,
        max_tokens=6000,
        temperature=0.3,
        seed=None,
    )

    client.chat_with_vision(
        system_prompt="system",
        user_content=[{"type": "text", "text": "analyze"}],
    )

    call = _FakeOpenAI.instances[0].calls[0]
    assert call["model"] == "gpt-5.3-codex"


def test_openai_client_passes_seed_when_configured(monkeypatch):
    _FakeOpenAI.instances = []
    _FakeOpenAI.raise_in_create = None
    _FakeOpenAI.chunks = [_FakeChunk(delta=_FakeDelta(content='{"ok":true}'))]

    module = _reload_openai_client_module()
    monkeypatch.setattr(module, "OpenAI", _FakeOpenAI)
    client = module.OpenAIClient(
        provider_name="main",
        api_key="openai-test-key",
        base_url="https://api.openai.com/v1",
        text_model="gpt-4o",
        vision_model="gpt-4o",
        timeout=60,
        connect_timeout=10,
        max_retries=2,
        max_tokens=6000,
        temperature=0.3,
        seed=42,
    )

    parsed = client.chat_with_json(system_prompt="system", user_prompt="user")

    assert parsed["ok"] is True
    call = _FakeOpenAI.instances[0].calls[0]
    assert call["seed"] == 42
