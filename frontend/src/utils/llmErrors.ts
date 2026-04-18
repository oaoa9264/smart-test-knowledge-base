import type { LLMErrorDetail } from "../types";

/**
 * Canonical LLM failure codes. Keep in sync with
 * backend/app/services/llm_result_helpers.py
 */
export const LLM_ERROR_CODES = {
  UNKNOWN: "llm_unknown_error",
  TIMEOUT: "llm_timeout",
  RATE_LIMIT: "llm_rate_limit",
  AUTH: "llm_auth_error",
  INVALID_OUTPUT: "llm_invalid_output",
} as const;

const RETRYABLE_BY_DEFAULT = new Set<string>([
  LLM_ERROR_CODES.UNKNOWN,
  LLM_ERROR_CODES.TIMEOUT,
  LLM_ERROR_CODES.RATE_LIMIT,
  LLM_ERROR_CODES.INVALID_OUTPUT,
]);

const FRIENDLY_COPY: Record<string, string> = {
  [LLM_ERROR_CODES.UNKNOWN]: "模型调用失败，你可以稍后重试或调整输入。",
  [LLM_ERROR_CODES.TIMEOUT]: "模型响应超时，建议简化输入或稍后重试。",
  [LLM_ERROR_CODES.RATE_LIMIT]: "模型调用触发了限流，稍等片刻再试。",
  [LLM_ERROR_CODES.AUTH]: "模型鉴权失败，请联系管理员检查配置。",
  [LLM_ERROR_CODES.INVALID_OUTPUT]: "模型输出格式异常，已为你保留输入，可点击重试。",
};

export function getFriendlyLLMErrorCopy(error?: LLMErrorDetail | null, fallback?: string): string {
  if (!error) return fallback || FRIENDLY_COPY[LLM_ERROR_CODES.UNKNOWN];
  return FRIENDLY_COPY[error.code] || error.message || fallback || FRIENDLY_COPY[LLM_ERROR_CODES.UNKNOWN];
}

export function isRetryableLLMError(error?: LLMErrorDetail | null): boolean {
  if (!error) return true;
  if (typeof error.retryable === "boolean") return error.retryable;
  return RETRYABLE_BY_DEFAULT.has(error.code);
}

/**
 * Wrap a fetch-like promise with a timeout that aborts after `timeoutMs`.
 * Used on the client side to enforce the plan's 180s LLM abort contract.
 */
export function withLLMTimeout<T>(
  run: (signal: AbortSignal) => Promise<T>,
  timeoutMs: number = 180_000,
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  return run(controller.signal).finally(() => window.clearTimeout(timer));
}
