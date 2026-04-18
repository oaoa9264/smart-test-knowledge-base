from app.services.llm_result_helpers import (
    LLM_FAILURE_CODE_TIMEOUT,
    LLM_FAILURE_CODE_UNKNOWN,
    build_llm_failure_meta,
    build_llm_success_meta,
    classify_llm_exception,
)


def test_build_llm_success_meta_sets_success_status():
    result = build_llm_success_meta("main")

    assert result["llm_status"] == "success"
    assert result["llm_provider"] == "main"
    assert result["llm_message"] is None
    assert result["llm_error"] is None


def test_build_llm_failure_meta_uses_default_message():
    result = build_llm_failure_meta()

    assert result["llm_status"] == "failed"
    assert result["llm_provider"] is None
    assert "所有模型调用失败" in result["llm_message"]
    assert result["llm_error"]["code"] == LLM_FAILURE_CODE_UNKNOWN
    assert result["llm_error"]["retryable"] is True
    assert result["llm_error"]["detail_url"] is None


def test_build_llm_failure_meta_includes_structured_error():
    result = build_llm_failure_meta(
        message="custom error",
        code=LLM_FAILURE_CODE_TIMEOUT,
        detail_url="https://example.com/docs/llm_timeout",
    )

    assert result["llm_error"] == {
        "code": LLM_FAILURE_CODE_TIMEOUT,
        "message": "custom error",
        "retryable": True,
        "detail_url": "https://example.com/docs/llm_timeout",
    }


def test_classify_llm_exception_maps_timeout_error():
    class _Timeout(TimeoutError):
        pass

    assert classify_llm_exception(_Timeout("request timed out")) == LLM_FAILURE_CODE_TIMEOUT
