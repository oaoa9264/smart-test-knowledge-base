/**
 * 轻量级前端埋点。
 * - 默认关闭（通过 `telemetry` feature flag 控制）
 * - 开启后，事件会写入浏览器控制台 + 最近 200 条内存缓冲区 + localStorage 汇总计数
 * - 通过 `window.__telemetry__` 供人工排查使用
 *
 * 埋点的目标是在不引入外部依赖、不破坏隐私的前提下，
 * 帮助我们快速确认关键路径（追问分析、风险分析、规则树生成、
 * 一键分析）是否被用户实际使用、是否在哪一步失败。
 */

import { isFeatureEnabled } from "./featureFlags";

export type TelemetryEventName =
  | "clarification.analyze.submit"
  | "clarification.analyze.success"
  | "clarification.analyze.failure"
  | "clarification.oneclick.start"
  | "clarification.oneclick.stage"
  | "clarification.oneclick.complete"
  | "clarification.oneclick.failure"
  | "clarification.create_requirement.submit"
  | "clarification.create_requirement.success"
  | "clarification.create_requirement.failure"
  | "clarification.pdf.upload.start"
  | "clarification.pdf.upload.success"
  | "clarification.pdf.upload.failure"
  | "clarification.pdf.infer.start"
  | "clarification.pdf.infer.success"
  | "clarification.pdf.infer.failure"
  | "clarification.pdf.apply"
  | "risk.analysis.start"
  | "risk.analysis.complete"
  | "risk.analysis.failure"
  | "ruletree.generate.start"
  | "ruletree.generate.complete"
  | "ruletree.generate.failure"
  | "page.view";

export interface TelemetryEvent {
  name: TelemetryEventName;
  at: string;
  payload?: Record<string, unknown>;
}

const BUFFER_LIMIT = 200;
const STORAGE_COUNTER_KEY = "telemetry:counters";

const memoryBuffer: TelemetryEvent[] = [];

function readCounters(): Record<string, number> {
  if (typeof window === "undefined" || !window.localStorage) return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_COUNTER_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") return parsed as Record<string, number>;
  } catch {
    return {};
  }
  return {};
}

function writeCounters(counters: Record<string, number>): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(STORAGE_COUNTER_KEY, JSON.stringify(counters));
  } catch {
    // 忽略
  }
}

export function trackEvent(name: TelemetryEventName, payload?: Record<string, unknown>): void {
  if (!isFeatureEnabled("telemetry")) return;

  const event: TelemetryEvent = {
    name,
    at: new Date().toISOString(),
    payload,
  };

  memoryBuffer.push(event);
  while (memoryBuffer.length > BUFFER_LIMIT) {
    memoryBuffer.shift();
  }

  const counters = readCounters();
  counters[name] = (counters[name] || 0) + 1;
  writeCounters(counters);

  // 在控制台打印一份便于排查。避免覆盖全局 console 行为。
  // 仅在浏览器环境且存在 console 时输出。
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[telemetry]", name, payload || {});
  }

  if (typeof window !== "undefined") {
    (window as unknown as { __telemetry__?: { events: TelemetryEvent[]; counters: Record<string, number> } }).__telemetry__ = {
      events: [...memoryBuffer],
      counters,
    };
  }
}

export function getTelemetryBuffer(): TelemetryEvent[] {
  return [...memoryBuffer];
}

export function getTelemetryCounters(): Record<string, number> {
  return { ...readCounters() };
}

export function clearTelemetry(): void {
  memoryBuffer.length = 0;
  writeCounters({});
  if (typeof window !== "undefined") {
    (window as unknown as { __telemetry__?: unknown }).__telemetry__ = { events: [], counters: {} };
  }
}

/**
 * Wrap an async operation and emit start/success/failure events
 * with start/end timestamps and duration. Returns the original result.
 */
export async function withTelemetryTimer<T>(
  baseName: string,
  run: () => Promise<T>,
  payload?: Record<string, unknown>,
): Promise<T> {
  const startTs = Date.now();
  trackEvent(`${baseName}.start` as TelemetryEventName, { ...payload, start_ts: startTs });
  try {
    const result = await run();
    const endTs = Date.now();
    trackEvent(`${baseName}.success` as TelemetryEventName, {
      ...payload,
      start_ts: startTs,
      end_ts: endTs,
      duration_ms: endTs - startTs,
    });
    return result;
  } catch (err) {
    const endTs = Date.now();
    trackEvent(`${baseName}.failure` as TelemetryEventName, {
      ...payload,
      start_ts: startTs,
      end_ts: endTs,
      duration_ms: endTs - startTs,
      message: err instanceof Error ? err.message : String(err),
    });
    throw err;
  }
}
