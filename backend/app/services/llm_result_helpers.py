DEFAULT_LLM_FAILURE_MESSAGE = "所有模型调用失败，未生成结果。请稍后重试或检查模型配置。"


def build_llm_success_meta(provider=None):
    return {
        "llm_status": "success",
        "llm_provider": provider,
        "llm_message": None,
    }


def build_llm_failure_meta(message: str = DEFAULT_LLM_FAILURE_MESSAGE):
    return {
        "llm_status": "failed",
        "llm_provider": None,
        "llm_message": message,
    }
