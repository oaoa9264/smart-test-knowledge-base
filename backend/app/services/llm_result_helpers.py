DEFAULT_LLM_FAILURE_MESSAGE = "所有模型调用失败，未生成结果。请稍后重试或检查模型配置。"

# Standardized LLM failure error codes. Keep in sync with
# frontend/src/utils/llmErrors.ts so UI can map codes to localized copy.
LLM_FAILURE_CODE_UNKNOWN = "llm_unknown_error"
LLM_FAILURE_CODE_TIMEOUT = "llm_timeout"
LLM_FAILURE_CODE_RATE_LIMIT = "llm_rate_limit"
LLM_FAILURE_CODE_AUTH = "llm_auth_error"
LLM_FAILURE_CODE_INVALID_OUTPUT = "llm_invalid_output"

# Retryable vs. non-retryable error codes (retryable = user can safely click "retry")
_RETRYABLE_CODES = {
    LLM_FAILURE_CODE_UNKNOWN,
    LLM_FAILURE_CODE_TIMEOUT,
    LLM_FAILURE_CODE_RATE_LIMIT,
    LLM_FAILURE_CODE_INVALID_OUTPUT,
}


def build_llm_success_meta(provider=None):
    return {
        "llm_status": "success",
        "llm_provider": provider,
        "llm_message": None,
        "llm_error": None,
    }


def build_llm_failure_meta(
    message: str = DEFAULT_LLM_FAILURE_MESSAGE,
    code: str = LLM_FAILURE_CODE_UNKNOWN,
    retryable=None,
    detail_url=None,
):
    """Build a normalized LLM failure meta payload.

    The shape is intentionally stable so the frontend can render a unified
    failure card with { code, message, retryable, detail_url } semantics.
    """
    resolved_retryable = (code in _RETRYABLE_CODES) if retryable is None else bool(retryable)
    return {
        "llm_status": "failed",
        "llm_provider": None,
        "llm_message": message,
        "llm_error": {
            "code": code,
            "message": message,
            "retryable": resolved_retryable,
            "detail_url": detail_url,
        },
    }


def classify_llm_exception(exc: Exception) -> str:
    """Best-effort mapping from raised exception to our standardized code."""
    name = type(exc).__name__.lower()
    text = (str(exc) or "").lower()
    if "timeout" in name or "timeout" in text or "timed out" in text:
        return LLM_FAILURE_CODE_TIMEOUT
    if "ratelimit" in name or "rate limit" in text or "429" in text:
        return LLM_FAILURE_CODE_RATE_LIMIT
    if "auth" in name or "unauthorized" in text or "invalid api key" in text or "401" in text:
        return LLM_FAILURE_CODE_AUTH
    if "json" in name or "jsondecode" in name or "invalid" in text and "output" in text:
        return LLM_FAILURE_CODE_INVALID_OUTPUT
    return LLM_FAILURE_CODE_UNKNOWN
