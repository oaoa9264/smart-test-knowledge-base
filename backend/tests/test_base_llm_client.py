import httpx

from app.services.base_llm_client import BaseLLMClient


class _CaptureClient(BaseLLMClient):
    provider_name = "capture"

    def __init__(self, *, seed=None):
        super().__init__(
            api_key="key",
            api_url="https://example.com/v1/chat/completions",
            text_model="text-model",
            vision_model="vision-model",
            timeout=10,
            connect_timeout=2,
            max_retries=0,
            max_tokens=128,
            temperature=0.2,
            seed=seed,
        )
        self.last_payload = None

    def _stream_chat_completion(self, payload):
        self.last_payload = payload
        return "", '{"ok":true}'


class _ErrorStreamResponse:
    def __init__(self, *, status_code=403, body=b'{"error":"denied"}'):
        self.status_code = status_code
        self._body = body
        self._has_read = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def read(self):
        self._has_read = True
        return self._body

    def json(self):
        if not self._has_read:
            raise httpx.ResponseNotRead()
        return {"error": "denied"}

    @property
    def text(self):
        if not self._has_read:
            raise httpx.ResponseNotRead()
        return self._body.decode("utf-8")

    def iter_lines(self):
        return []


class _ErrorStreamHTTPClient:
    def __init__(self, response):
        self.response = response

    def stream(self, *args, **kwargs):
        return self.response

    def close(self):
        return None


class _RealStreamClient(BaseLLMClient):
    provider_name = "capture"

    def __init__(self):
        super().__init__(
            api_key="key",
            api_url="https://example.com/v1/chat/completions",
            text_model="text-model",
            vision_model="vision-model",
            timeout=10,
            connect_timeout=2,
            max_retries=0,
            max_tokens=128,
            temperature=0.2,
            seed=None,
        )
        self.response = _ErrorStreamResponse()

    def _make_client(self):
        return _ErrorStreamHTTPClient(self.response)


def test_base_llm_client_includes_seed_when_configured():
    client = _CaptureClient(seed=7)

    result = client.chat_with_json(system_prompt="system", user_prompt="user")

    assert result["ok"] is True
    assert client.last_payload["seed"] == 7


def test_base_llm_client_omits_seed_when_not_configured():
    client = _CaptureClient(seed=None)

    result = client.chat_with_json(system_prompt="system", user_prompt="user")

    assert result["ok"] is True
    assert "seed" not in client.last_payload


def test_base_llm_client_non_200_stream_does_not_raise_response_not_read():
    client = _RealStreamClient()

    try:
        client.chat_with_json(system_prompt="system", user_prompt="user")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "HTTP 403" in str(exc)
