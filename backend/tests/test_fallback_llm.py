import logging

import pytest

from app.services.fallback_llm_client import AllLLMProvidersFailedError, FallbackLLMClient


class _FakeProvider:
    def __init__(self, provider_name, *, json_result=None, json_error=None, vision_result=None, vision_error=None):
        self.provider_name = provider_name
        self.json_result = json_result
        self.json_error = json_error
        self.vision_result = vision_result
        self.vision_error = vision_error
        self.json_calls = 0
        self.vision_calls = 0

    def chat_with_json(self, system_prompt, user_prompt):
        self.json_calls += 1
        if self.json_error is not None:
            raise self.json_error
        return self.json_result

    def chat_with_vision(self, system_prompt, user_content):
        self.vision_calls += 1
        if self.vision_error is not None:
            raise self.vision_error
        return self.vision_result

    def image_to_base64_url(self, file_path):
        return "{0}:{1}".format(self.provider_name, file_path)


def test_fallback_uses_first_provider_when_successful():
    openai = _FakeProvider("openai", json_result={"result": "openai"})
    zhipu = _FakeProvider("zhipu", json_result={"result": "zhipu"})

    client = FallbackLLMClient([openai, zhipu])
    result = client.chat_with_json(system_prompt="system", user_prompt="user")

    assert result == {"result": "openai"}
    assert openai.json_calls == 1
    assert zhipu.json_calls == 0
    assert client.get_last_provider() == "openai"
    assert client.get_last_provider("chat_with_json") == "openai"


def test_fallback_moves_to_next_provider_on_error(caplog):
    openai = _FakeProvider("openai", json_error=RuntimeError("timeout"))
    zhipu = _FakeProvider("zhipu", json_result={"result": "zhipu"})

    client = FallbackLLMClient([openai, zhipu])
    with caplog.at_level(logging.WARNING):
        result = client.chat_with_json(system_prompt="system", user_prompt="user")

    assert result == {"result": "zhipu"}
    assert "fallback_from=openai" in caplog.text
    assert openai.json_calls == 1
    assert zhipu.json_calls == 1
    assert client.get_last_provider() == "zhipu"
    assert client.get_last_provider("chat_with_json") == "zhipu"


def test_fallback_raises_all_providers_failed_error_when_all_providers_fail(caplog):
    openai = _FakeProvider("openai", json_error=RuntimeError("openai failed"))
    zhipu = _FakeProvider("zhipu", json_error=ValueError("zhipu failed"))

    client = FallbackLLMClient([openai, zhipu])
    with caplog.at_level(logging.ERROR):
        with pytest.raises(AllLLMProvidersFailedError) as exc:
            client.chat_with_json(system_prompt="system", user_prompt="user")

    assert "All LLM providers failed" in caplog.text
    assert exc.value.failed_providers == ["openai", "zhipu"]
    assert exc.value.method_name == "chat_with_json"
    assert isinstance(exc.value.last_error, ValueError)


def test_image_to_base64_url_uses_first_provider():
    openai = _FakeProvider("openai")
    zhipu = _FakeProvider("zhipu")

    client = FallbackLLMClient([openai, zhipu])

    assert client.image_to_base64_url("/tmp/test.png") == "openai:/tmp/test.png"
