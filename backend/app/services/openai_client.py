import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from app.services.base_llm_client import BaseLLMClient

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - dependency/runtime environment issue
    OpenAI = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class OpenAIClient(BaseLLMClient):
    provider_name = "openai"

    def __init__(
        self,
        *,
        provider_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        text_model: Optional[str] = None,
        vision_model: Optional[str] = None,
        timeout: Optional[float] = None,
        connect_timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
    ):
        resolved_api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        if not resolved_api_key:
            raise ValueError("api_key is required")

        if OpenAI is None:
            raise RuntimeError("openai package is required for OpenAIClient")

        self.provider_name = (provider_name or self.provider_name).strip()
        self.base_url = self._resolve_base_url(base_url=base_url)
        api_url = "{0}/chat/completions".format(self.base_url.rstrip("/"))
        resolved_text_model = (text_model or os.getenv("OPENAI_TEXT_MODEL", "gpt-4o")).strip()
        resolved_vision_model = (vision_model or os.getenv("OPENAI_VISION_MODEL", resolved_text_model)).strip()

        super().__init__(
            api_key=resolved_api_key,
            api_url=api_url,
            text_model=resolved_text_model,
            vision_model=resolved_vision_model,
            timeout=float(timeout if timeout is not None else os.getenv("LLM_REQUEST_TIMEOUT", "60")),
            connect_timeout=float(connect_timeout if connect_timeout is not None else os.getenv("LLM_CONNECT_TIMEOUT", "10")),
            max_retries=int(max_retries if max_retries is not None else os.getenv("LLM_MAX_RETRIES", "2")),
            max_tokens=int(max_tokens if max_tokens is not None else os.getenv("LLM_MAX_TOKENS", "6000")),
            temperature=float(temperature if temperature is not None else os.getenv("LLM_TEMPERATURE", "0.3")),
            seed=self._resolve_seed(seed),
        )
        self._sdk_client = OpenAI(api_key=resolved_api_key, base_url=self.base_url)

    @staticmethod
    def _resolve_base_url(*, base_url: Optional[str] = None) -> str:
        resolved_base_url = (base_url or os.getenv("OPENAI_BASE_URL", "")).strip()
        if resolved_base_url:
            return resolved_base_url.rstrip("/")

        # Backward compatibility with existing OPENAI_API_URL setting.
        api_url = os.getenv("OPENAI_API_URL", "").strip()
        if api_url:
            normalized = api_url.rstrip("/")
            suffix = "/chat/completions"
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
            return normalized

        return "https://api.openai.com/v1"

    @staticmethod
    def _resolve_seed(seed: Optional[int]) -> Optional[int]:
        if seed is not None:
            return int(seed)
        seed_text = os.getenv("LLM_SEED", "").strip()
        if not seed_text:
            return None
        return int(seed_text)

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
