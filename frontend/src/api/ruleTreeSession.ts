import { http } from "./client";
import type {
  RuleTreeSession,
  RuleTreeSessionDetail,
  RuleTreeSessionGenerateResult,
  RuleTreeSessionUpdateResult,
} from "../types";

const LONG_LLM_TIMEOUT_MS = 180000;

export async function createRuleTreeSession(requirementId: number, title: string): Promise<RuleTreeSession> {
  const { data } = await http.post<RuleTreeSession>("/api/rules/sessions", {
    requirement_id: requirementId,
    title,
  });
  return data;
}

export async function fetchRuleTreeSessions(requirementId: number): Promise<RuleTreeSession[]> {
  const { data } = await http.get<RuleTreeSession[]>("/api/rules/sessions", {
    params: { requirement_id: requirementId },
  });
  return data;
}

export async function fetchRuleTreeSessionDetail(sessionId: number): Promise<RuleTreeSessionDetail> {
  const { data } = await http.get<RuleTreeSessionDetail>(`/api/rules/sessions/${sessionId}`);
  return data;
}

export async function generateRuleTreeSession(
  sessionId: number,
  payload: { requirement_text: string; title?: string },
): Promise<RuleTreeSessionGenerateResult> {
  const { data } = await http.post<RuleTreeSessionGenerateResult>(`/api/rules/sessions/${sessionId}/generate`, payload, {
    timeout: LONG_LLM_TIMEOUT_MS,
  });
  return data;
}

export async function updateRuleTreeSession(
  sessionId: number,
  payload: { new_requirement_text: string },
): Promise<RuleTreeSessionUpdateResult> {
  const { data } = await http.post<RuleTreeSessionUpdateResult>(`/api/rules/sessions/${sessionId}/update`, payload, {
    timeout: LONG_LLM_TIMEOUT_MS,
  });
  return data;
}

export async function confirmRuleTreeSession(
  sessionId: number,
  payload: { tree_json: Record<string, unknown>; requirement_text: string },
): Promise<{ ok: boolean; imported_nodes: number; session: RuleTreeSession }> {
  const { data } = await http.post<{ ok: boolean; imported_nodes: number; session: RuleTreeSession }>(
    `/api/rules/sessions/${sessionId}/confirm`,
    payload,
  );
  return data;
}
