import os
from typing import Any, Dict, List, Optional

from app.services.base_llm_client import BaseLLMClient
from app.services.fallback_llm_client import FallbackLLMClient
from app.services.openai_client import OpenAIClient
from app.services.zhipu_client import ZhipuClient


class LLMClient:
    """Backward-compatible wrapper for multi-provider fallback."""

    def __init__(self, clients: Optional[List[BaseLLMClient]] = None):
        provider_clients = clients if clients is not None else self._build_clients_from_env()
        self._fallback = FallbackLLMClient(provider_clients)

    def _build_clients_from_env(self) -> List[BaseLLMClient]:
        clients: List[BaseLLMClient] = []

        if os.getenv("OPENAI_API_KEY", "").strip():
            clients.append(OpenAIClient())

        if os.getenv("ZHIPU_API_KEY", "").strip():
            clients.append(ZhipuClient())

        if not clients:
            raise ValueError("OPENAI_API_KEY or ZHIPU_API_KEY is required when ANALYZER_PROVIDER=llm")

        return clients

    def chat_with_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        return self._fallback.chat_with_json(system_prompt=system_prompt, user_prompt=user_prompt)

    def chat_with_vision(self, system_prompt: str, user_content: List[Dict[str, Any]]) -> str:
        return self._fallback.chat_with_vision(system_prompt=system_prompt, user_content=user_content)

    def chat_with_messages(self, messages: List[Dict[str, Any]], response_format: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._fallback.chat_with_messages(messages=messages, response_format=response_format)

    def image_to_base64_url(self, file_path: str) -> str:
        return self._fallback.image_to_base64_url(file_path)

    def get_last_provider(self, method_name: Optional[str] = None) -> Optional[str]:
        return self._fallback.get_last_provider(method_name=method_name)
