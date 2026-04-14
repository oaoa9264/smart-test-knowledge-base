import os
from typing import Optional

from app.services.base_llm_client import BaseLLMClient
from app.services.openai_client import OpenAIClient
from app.services.zhipu_client import ZhipuClient


class LLMProviderFactory:
    @staticmethod
    def build(alias: str) -> BaseLLMClient:
        normalized_alias = BaseLLMClient._normalize_config_text(alias)
        if not normalized_alias:
            raise ValueError("provider alias is required")

        prefix = "LLM_PROVIDER_{0}".format(normalized_alias.upper())
        provider_type = BaseLLMClient._normalize_config_text(os.getenv("{0}_TYPE".format(prefix), "")).lower()
        if not provider_type:
            raise ValueError("{0}_TYPE is required".format(prefix))

        if provider_type == "openai_compatible":
            return OpenAIClient(
                provider_name=normalized_alias,
                api_key=LLMProviderFactory._require(prefix, "API_KEY"),
                base_url=BaseLLMClient._normalize_config_text(os.getenv("{0}_BASE_URL".format(prefix), "https://api.openai.com/v1")),
                text_model=BaseLLMClient._normalize_config_text(os.getenv("{0}_TEXT_MODEL".format(prefix), "gpt-4o")),
                vision_model=BaseLLMClient._normalize_config_text(
                    os.getenv("{0}_VISION_MODEL".format(prefix), os.getenv("{0}_TEXT_MODEL".format(prefix), "gpt-4o"))
                ),
                timeout=LLMProviderFactory._read_float(prefix, "REQUEST_TIMEOUT", "LLM_REQUEST_TIMEOUT", 60.0),
                connect_timeout=LLMProviderFactory._read_float(prefix, "CONNECT_TIMEOUT", "LLM_CONNECT_TIMEOUT", 10.0),
                max_retries=LLMProviderFactory._read_int(prefix, "MAX_RETRIES", "LLM_MAX_RETRIES", 2),
                max_tokens=LLMProviderFactory._read_int(prefix, "MAX_TOKENS", "LLM_MAX_TOKENS", 6000),
                temperature=LLMProviderFactory._read_float(prefix, "TEMPERATURE", "LLM_TEMPERATURE", 0.3),
                seed=LLMProviderFactory._read_optional_int(prefix, "SEED", "LLM_SEED"),
            )

        if provider_type == "zhipu":
            text_model = BaseLLMClient._normalize_config_text(os.getenv("{0}_TEXT_MODEL".format(prefix), "glm-4.7"))
            return ZhipuClient(
                provider_name=normalized_alias,
                api_key=LLMProviderFactory._require(prefix, "API_KEY"),
                api_url=BaseLLMClient._normalize_config_text(
                    os.getenv("{0}_API_URL".format(prefix), "https://open.bigmodel.cn/api/paas/v4/chat/completions")
                ),
                text_model=text_model,
                vision_model=BaseLLMClient._normalize_config_text(os.getenv("{0}_VISION_MODEL".format(prefix), text_model)),
                timeout=LLMProviderFactory._read_float(prefix, "REQUEST_TIMEOUT", "LLM_REQUEST_TIMEOUT", 60.0),
                connect_timeout=LLMProviderFactory._read_float(prefix, "CONNECT_TIMEOUT", "LLM_CONNECT_TIMEOUT", 10.0),
                max_retries=LLMProviderFactory._read_int(prefix, "MAX_RETRIES", "LLM_MAX_RETRIES", 2),
                max_tokens=LLMProviderFactory._read_int(prefix, "MAX_TOKENS", "LLM_MAX_TOKENS", 6000),
                temperature=LLMProviderFactory._read_float(prefix, "TEMPERATURE", "LLM_TEMPERATURE", 0.3),
                seed=LLMProviderFactory._read_optional_int(prefix, "SEED", "LLM_SEED"),
                thinking_type=BaseLLMClient._normalize_config_text(
                    os.getenv("{0}_THINKING_TYPE".format(prefix), os.getenv("LLM_THINKING_TYPE", "disabled"))
                ),
            )

        raise ValueError("Unsupported provider type: {0}".format(provider_type))

    @staticmethod
    def _require(prefix: str, suffix: str) -> str:
        value = BaseLLMClient._normalize_config_text(os.getenv("{0}_{1}".format(prefix, suffix), ""))
        if not value:
            raise ValueError("{0}_{1} is required".format(prefix, suffix))
        return value

    @staticmethod
    def _read_float(prefix: str, suffix: str, global_name: str, default: float) -> float:
        value = os.getenv("{0}_{1}".format(prefix, suffix), os.getenv(global_name, "")).strip()
        if not value:
            return float(default)
        return float(value)

    @staticmethod
    def _read_int(prefix: str, suffix: str, global_name: str, default: int) -> int:
        value = os.getenv("{0}_{1}".format(prefix, suffix), os.getenv(global_name, "")).strip()
        if not value:
            return int(default)
        return int(value)

    @staticmethod
    def _read_optional_int(prefix: str, suffix: str, global_name: str) -> Optional[int]:
        value = os.getenv("{0}_{1}".format(prefix, suffix), os.getenv(global_name, "")).strip()
        if not value:
            return None
        return int(value)
