import importlib

import pytest


class _FakeProvider:
    def __init__(self, provider_name):
        self.provider_name = provider_name


class _FakeFallback:
    last_instance = None

    def __init__(self, clients):
        self.clients = clients
        self.json_calls = []
        self.vision_calls = []
        self.image_calls = []
        _FakeFallback.last_instance = self

    def chat_with_json(self, system_prompt, user_prompt):
        self.json_calls.append((system_prompt, user_prompt))
        return {"ok": True}

    def chat_with_vision(self, system_prompt, user_content):
        self.vision_calls.append((system_prompt, user_content))
        return "vision-ok"

    def image_to_base64_url(self, file_path):
        self.image_calls.append(file_path)
        return "data:image/png;base64,fake"


def _reload_llm_client_module():
    import app.services.llm_client as llm_client_module

    return importlib.reload(llm_client_module)


def test_llm_client_builds_chain_openai_first_then_zhipu(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-key")

    module = _reload_llm_client_module()
    monkeypatch.setattr(module, "OpenAIClient", lambda: _FakeProvider("openai"))
    monkeypatch.setattr(module, "ZhipuClient", lambda: _FakeProvider("zhipu"))
    monkeypatch.setattr(module, "FallbackLLMClient", _FakeFallback)

    module.LLMClient()

    providers = [item.provider_name for item in _FakeFallback.last_instance.clients]
    assert providers == ["openai", "zhipu"]


def test_llm_client_builds_chain_with_single_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-key")

    module = _reload_llm_client_module()
    monkeypatch.setattr(module, "ZhipuClient", lambda: _FakeProvider("zhipu"))
    monkeypatch.setattr(module, "FallbackLLMClient", _FakeFallback)

    module.LLMClient()

    providers = [item.provider_name for item in _FakeFallback.last_instance.clients]
    assert providers == ["zhipu"]


def test_llm_client_requires_any_provider_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)

    module = _reload_llm_client_module()

    with pytest.raises(ValueError, match="OPENAI_API_KEY or ZHIPU_API_KEY"):
        module.LLMClient()


def test_llm_client_delegates_calls_to_fallback(monkeypatch):
    module = _reload_llm_client_module()
    monkeypatch.setattr(module, "FallbackLLMClient", _FakeFallback)

    client = module.LLMClient(clients=[_FakeProvider("openai")])

    assert client.chat_with_json(system_prompt="s", user_prompt="u") == {"ok": True}
    assert client.chat_with_vision(system_prompt="s", user_content=[{"type": "text", "text": "x"}]) == "vision-ok"
    assert client.image_to_base64_url("/tmp/test.png") == "data:image/png;base64,fake"

    assert _FakeFallback.last_instance.json_calls == [("s", "u")]
    assert len(_FakeFallback.last_instance.vision_calls) == 1
    assert _FakeFallback.last_instance.image_calls == ["/tmp/test.png"]
