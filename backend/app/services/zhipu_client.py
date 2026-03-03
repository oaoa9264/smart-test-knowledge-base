import os
from typing import Any, Dict

from app.services.base_llm_client import BaseLLMClient


class ZhipuClient(BaseLLMClient):
    provider_name = "zhipu"

    def __init__(self):
        api_key = os.getenv("ZHIPU_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ZHIPU_API_KEY is required")

        super().__init__(
            api_key=api_key,
            api_url=os.getenv("ZHIPU_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
            text_model=os.getenv("ZHIPU_TEXT_MODEL", "glm-4.7"),
            vision_model=os.getenv("ZHIPU_VISION_MODEL", "glm-4.7"),
            timeout=float(os.getenv("LLM_REQUEST_TIMEOUT", "60")),
            connect_timeout=float(os.getenv("LLM_CONNECT_TIMEOUT", "10")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "6000")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
            seed=self._read_seed_from_env(),
        )
        self.thinking_type = os.getenv("LLM_THINKING_TYPE", "disabled").strip()

    def _provider_payload(self) -> Dict[str, Any]:
        if not self.thinking_type:
            return {}
        return {"thinking": {"type": self.thinking_type}}

    @staticmethod
    def _read_seed_from_env():
        seed_text = os.getenv("LLM_SEED", "").strip()
        if not seed_text:
            return None
        return int(seed_text)
