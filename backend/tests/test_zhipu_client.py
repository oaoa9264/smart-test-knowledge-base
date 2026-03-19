from app.services.zhipu_client import ZhipuClient


def test_zhipu_client_uses_explicit_constructor_config():
    client = ZhipuClient(
        provider_name="zhipu",
        api_key="zhipu-test-key",
        api_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        text_model="glm-4.7",
        vision_model="glm-4.7v",
        timeout=60,
        connect_timeout=10,
        max_retries=2,
        max_tokens=6000,
        temperature=0.3,
        seed=42,
        thinking_type="disabled",
    )

    assert client.provider_name == "zhipu"
    assert client.api_url == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert client.text_model == "glm-4.7"
    assert client.vision_model == "glm-4.7v"
    assert client.seed == 42
    assert client.thinking_type == "disabled"


def test_zhipu_client_omits_provider_payload_when_thinking_type_empty():
    client = ZhipuClient(
        provider_name="zhipu",
        api_key="zhipu-test-key",
        api_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        text_model="glm-4.7",
        vision_model="glm-4.7",
        timeout=60,
        connect_timeout=10,
        max_retries=2,
        max_tokens=6000,
        temperature=0.3,
        seed=None,
        thinking_type="",
    )

    assert client._provider_payload() == {}
