import os
from typing import Any, Dict, Optional

from app.services.base_llm_client import BaseLLMClient


class ZhipuClient(BaseLLMClient):
    provider_name = "zhipu"

    def __init__(
        self,
        *,
        provider_name: Optional[str] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        text_model: Optional[str] = None,
        vision_model: Optional[str] = None,
        timeout: Optional[float] = None,
        connect_timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
        thinking_type: Optional[str] = None,
    ):
        resolved_api_key = (api_key or os.getenv("ZHIPU_API_KEY", "")).strip()
        if not resolved_api_key:
            raise ValueError("api_key is required")

        self.provider_name = (provider_name or self.provider_name).strip()

        super().__init__(
            api_key=resolved_api_key,
            api_url=(api_url or os.getenv("ZHIPU_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")).strip(),
            text_model=(text_model or os.getenv("ZHIPU_TEXT_MODEL", "glm-4.7")).strip(),
            vision_model=(vision_model or os.getenv("ZHIPU_VISION_MODEL", "glm-4.7")).strip(),
            timeout=float(timeout if timeout is not None else os.getenv("LLM_REQUEST_TIMEOUT", "60")),
            connect_timeout=float(connect_timeout if connect_timeout is not None else os.getenv("LLM_CONNECT_TIMEOUT", "10")),
            max_retries=int(max_retries if max_retries is not None else os.getenv("LLM_MAX_RETRIES", "2")),
            max_tokens=int(max_tokens if max_tokens is not None else os.getenv("LLM_MAX_TOKENS", "6000")),
            temperature=float(temperature if temperature is not None else os.getenv("LLM_TEMPERATURE", "0.3")),
            seed=self._resolve_seed(seed),
        )
        resolved_thinking_type = thinking_type if thinking_type is not None else os.getenv("LLM_THINKING_TYPE", "disabled")
        self.thinking_type = resolved_thinking_type.strip()

    def _provider_payload(self) -> Dict[str, Any]:
        if not self.thinking_type:
            return {}
        return {"thinking": {"type": self.thinking_type}}

    @staticmethod
    def _resolve_seed(seed: Optional[int]) -> Optional[int]:
        if seed is not None:
            return int(seed)
        seed_text = os.getenv("LLM_SEED", "").strip()
        if not seed_text:
            return None
        return int(seed_text)
