import { http } from "./client";
import type {
  RuleTreeSession,
  RuleTreeSessionDetail,
  RuleTreeSessionGenerateAcceptedResult,
  RuleTreeSessionGenerateResult,
  RuleTreeSessionUpdateResult,
} from "../types";

const LONG_LLM_TIMEOUT_MS = 180000;

export const RULE_TREE_IN_PROGRESS_STATUSES = ["generating", "reviewing", "saving"] as const;

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
  payload: { requirement_text: string; title?: string; image?: File },
): Promise<RuleTreeSessionGenerateAcceptedResult> {
  const formData = new FormData();
  formData.append("requirement_text", payload.requirement_text);
  if (payload.title) {
    formData.append("title", payload.title);
  }
  if (payload.image) {
    formData.append("image", payload.image);
  }
  const { data } = await http.post<RuleTreeSessionGenerateAcceptedResult>(
    `/api/rules/sessions/${sessionId}/generate`,
    formData,
  );
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

export function isRuleTreeSessionInProgress(session?: RuleTreeSession | null): boolean {
  if (!session) return false;
  return RULE_TREE_IN_PROGRESS_STATUSES.includes(session.status as (typeof RULE_TREE_IN_PROGRESS_STATUSES)[number]);
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
