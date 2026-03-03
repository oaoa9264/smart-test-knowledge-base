import logging
import os
from typing import Any, Dict, List, Tuple

from app.services.base_llm_client import BaseLLMClient

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - dependency/runtime environment issue
    OpenAI = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class OpenAIClient(BaseLLMClient):
    provider_name = "openai"

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required")

        if OpenAI is None:
            raise RuntimeError("openai package is required for OpenAIClient")

        self.base_url = self._resolve_base_url()
        api_url = "{0}/chat/completions".format(self.base_url.rstrip("/"))
        text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o")
        vision_model = os.getenv("OPENAI_VISION_MODEL", text_model)

        super().__init__(
            api_key=api_key,
            api_url=api_url,
            text_model=text_model,
            vision_model=vision_model,
            timeout=float(os.getenv("LLM_REQUEST_TIMEOUT", "60")),
            connect_timeout=float(os.getenv("LLM_CONNECT_TIMEOUT", "10")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "6000")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
            seed=self._read_seed_from_env(),
        )
        self._sdk_client = OpenAI(api_key=api_key, base_url=self.base_url)

    @staticmethod
    def _resolve_base_url() -> str:
        # Preferred input for SDK usage.
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        if base_url:
            return base_url.rstrip("/")

        # Backward compatibility with existing OPENAI_API_URL setting.
        api_url = os.getenv("OPENAI_API_URL", "").strip()
        if api_url:
            normalized = api_url.rstrip("/")
            suffix = "/chat/completions"
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
            return normalized

        return "https://api.openai.com/v1"

    def _stream_chat_completion(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        reasoning_acc: List[str] = []
        content_acc: List[str] = []

        request_kwargs = {
            "model": payload["model"],
            "messages": payload["messages"],
            "max_tokens": payload.get("max_tokens"),
            "temperature": payload.get("temperature"),
            "response_format": payload.get("response_format"),
            "stream": True,
            "timeout": self.timeout,
        }
        if payload.get("seed") is not None:
            request_kwargs["seed"] = payload.get("seed")

        stream = self._sdk_client.chat.completions.create(
            **request_kwargs,
        )

        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue

            choice = choices[0]
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue

            reasoning_piece = self._normalize_content(getattr(delta, "reasoning_content", None))
            if reasoning_piece:
                reasoning_acc.append(reasoning_piece)

            content_piece = self._normalize_content(getattr(delta, "content", None))
            if content_piece:
                content_acc.append(content_piece)

            if not content_piece:
                message = getattr(choice, "message", None)
                if message is not None:
                    message_piece = self._normalize_content(getattr(message, "content", None))
                    if message_piece:
                        content_acc.append(message_piece)

        if not content_acc:
            logger.warning(
                "LLM stream completed with empty content (provider=%s, reasoning_len=%d, model=%s)",
                self.provider_name,
                len("".join(reasoning_acc)),
                payload.get("model"),
            )

        return "".join(reasoning_acc), "".join(content_acc)

    @staticmethod
    def _read_seed_from_env():
        seed_text = os.getenv("LLM_SEED", "").strip()
        if not seed_text:
            return None
        return int(seed_text)
