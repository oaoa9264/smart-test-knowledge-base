/**
 * 轻量的前端 feature flag 管理。
 *
 * 取值优先级（高 → 低）：
 *   1. URL query 参数 `?ff_xxx=1` / `?ff_xxx=0`
 *   2. localStorage (`feature_flag:xxx`)
 *   3. 环境变量 (`VITE_FEATURE_XXX`)
 *   4. 默认值
 */

export type FeatureFlagKey =
  | "oneClickAnalysis"
  | "globalProgressBar"
  | "telemetry";

const DEFAULTS: Record<FeatureFlagKey, boolean> = {
  oneClickAnalysis: false,
  globalProgressBar: true,
  telemetry: false,
};

const ENV_KEYS: Record<FeatureFlagKey, string> = {
  oneClickAnalysis: "VITE_FEATURE_ONE_CLICK_ANALYSIS",
  globalProgressBar: "VITE_FEATURE_GLOBAL_PROGRESS_BAR",
  telemetry: "VITE_FEATURE_TELEMETRY",
};

const QUERY_KEYS: Record<FeatureFlagKey, string> = {
  oneClickAnalysis: "ff_one_click",
  globalProgressBar: "ff_progress",
  telemetry: "ff_telemetry",
};

const STORAGE_PREFIX = "feature_flag:";

function readEnv(key: string): boolean | null {
  // import.meta.env 是字符串或 undefined
  try {
    const raw = (import.meta as unknown as { env?: Record<string, string | undefined> }).env?.[key];
    if (raw === undefined) return null;
    const normalized = String(raw).trim().toLowerCase();
    if (!normalized) return null;
    if (["1", "true", "on", "yes"].includes(normalized)) return true;
    if (["0", "false", "off", "no"].includes(normalized)) return false;
  } catch {
    return null;
  }
  return null;
}

function readQuery(queryKey: string): boolean | null {
  if (typeof window === "undefined") return null;
  try {
    const params = new URLSearchParams(window.location.search);
    const raw = params.get(queryKey);
    if (raw === null) return null;
    const normalized = raw.trim().toLowerCase();
    if (["1", "true", "on", "yes"].includes(normalized)) return true;
    if (["0", "false", "off", "no"].includes(normalized)) return false;
  } catch {
    return null;
  }
  return null;
}

function readStorage(key: FeatureFlagKey): boolean | null {
  if (typeof window === "undefined" || !window.localStorage) return null;
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${key}`);
    if (raw === null) return null;
    const normalized = raw.trim().toLowerCase();
    if (["1", "true", "on", "yes"].includes(normalized)) return true;
    if (["0", "false", "off", "no"].includes(normalized)) return false;
  } catch {
    return null;
  }
  return null;
}

export function isFeatureEnabled(key: FeatureFlagKey): boolean {
  const fromQuery = readQuery(QUERY_KEYS[key]);
  if (fromQuery !== null) {
    // URL 强制指定时同步写入 localStorage，方便后续免带参数
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        window.localStorage.setItem(`${STORAGE_PREFIX}${key}`, fromQuery ? "1" : "0");
      }
    } catch {
      // 忽略存储失败
    }
    return fromQuery;
  }
  const fromStorage = readStorage(key);
  if (fromStorage !== null) return fromStorage;
  const fromEnv = readEnv(ENV_KEYS[key]);
  if (fromEnv !== null) return fromEnv;
  return DEFAULTS[key];
}

export function setFeatureFlag(key: FeatureFlagKey, enabled: boolean | null): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  const storageKey = `${STORAGE_PREFIX}${key}`;
  try {
    if (enabled === null) {
      window.localStorage.removeItem(storageKey);
    } else {
      window.localStorage.setItem(storageKey, enabled ? "1" : "0");
    }
  } catch {
    // 忽略存储失败
  }
}
