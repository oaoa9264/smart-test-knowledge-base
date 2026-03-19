import logging
from typing import Any, Dict, List, Optional

from app.services.base_llm_client import BaseLLMClient


logger = logging.getLogger(__name__)


class AllLLMProvidersFailedError(Exception):
    def __init__(self, *, failed_providers: List[str], last_error: Optional[Exception], method_name: str):
        self.failed_providers = failed_providers
        self.last_error = last_error
        self.method_name = method_name
        message = "All LLM providers failed (method={0}, providers={1})".format(
            method_name,
            ",".join(failed_providers),
        )
        super().__init__(message)


class FallbackLLMClient:
    """Sequential provider fallback for JSON and vision calls."""

    def __init__(self, clients: List[BaseLLMClient]):
        self.clients = [client for client in clients if client is not None]
        if not self.clients:
            raise ValueError("FallbackLLMClient requires at least one provider")
        self._last_provider: Optional[str] = None
        self._last_provider_by_method: Dict[str, str] = {}

    def chat_with_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        return self._call_with_fallback("chat_with_json", system_prompt=system_prompt, user_prompt=user_prompt)

    def chat_with_vision(self, system_prompt: str, user_content: List[Dict[str, Any]]) -> str:
        return self._call_with_fallback("chat_with_vision", system_prompt=system_prompt, user_content=user_content)

    def chat_with_messages(self, messages: List[Dict[str, Any]], response_format: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._call_with_fallback("chat_with_messages", messages=messages, response_format=response_format)

    def image_to_base64_url(self, file_path: str) -> str:
        return self.clients[0].image_to_base64_url(file_path)

    def get_last_provider(self, method_name: Optional[str] = None) -> Optional[str]:
        if method_name:
            return self._last_provider_by_method.get(method_name)
        return self._last_provider

    def _call_with_fallback(self, method_name: str, **kwargs: Any) -> Any:
        last_error: Optional[Exception] = None
        failed_providers: List[str] = []

        for idx, client in enumerate(self.clients):
            provider = client.provider_name
            self._last_provider = provider
            self._last_provider_by_method[method_name] = provider
            try:
                result = getattr(client, method_name)(**kwargs)
                logger.info("LLM call succeeded (provider=%s, method=%s)", provider, method_name)
                return result
            except Exception as exc:
                last_error = exc
                failed_providers.append(provider)
                if idx + 1 < len(self.clients):
                    next_provider = self.clients[idx + 1].provider_name
                    logger.warning(
                        "LLM provider failed (provider=%s, fallback_from=%s, fallback_to=%s, method=%s): %s: %s",
                        provider,
                        provider,
                        next_provider,
                        method_name,
                        type(exc).__name__,
                        exc,
                    )
                else:
                    logger.error(
                        "LLM provider failed (provider=%s, fallback_from=%s, method=%s): %s: %s",
                        provider,
                        provider,
                        method_name,
                        type(exc).__name__,
                        exc,
                    )

        logger.error("All LLM providers failed (method=%s)", method_name)
        raise AllLLMProvidersFailedError(
            failed_providers=failed_providers,
            last_error=last_error,
            method_name=method_name,
        )
