from app.services.llm_result_helpers import build_llm_failure_meta, build_llm_success_meta


def test_build_llm_success_meta_sets_success_status():
    result = build_llm_success_meta("main")

    assert result == {
        "llm_status": "success",
        "llm_provider": "main",
        "llm_message": None,
    }


def test_build_llm_failure_meta_uses_default_message():
    result = build_llm_failure_meta()

    assert result["llm_status"] == "failed"
    assert result["llm_provider"] is None
    assert "所有模型调用失败" in result["llm_message"]
