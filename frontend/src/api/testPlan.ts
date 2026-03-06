import { http } from "./client";
import type {
  GeneratedTestCase,
  TestPoint,
  TestPlanResponse,
  TestPlanSession,
  TestPlanSessionListResponse,
  TestCaseGenRequest,
  TestCaseGenResponse,
  TestCaseConfirmRequest,
  TestCaseConfirmResponse,
} from "../types";

const LONG_LLM_TIMEOUT_MS = 180000;

// ===================== Session APIs =====================

export async function getTestPlanSessions(requirementId: number): Promise<TestPlanSessionListResponse> {
  const { data } = await http.get<TestPlanSessionListResponse>(
    "/api/test-plan/sessions",
    { params: { requirement_id: requirementId } },
  );
  return data;
}

export async function getTestPlanSession(sessionId: number): Promise<TestPlanSession> {
  const { data } = await http.get<TestPlanSession>(
    `/api/test-plan/sessions/${sessionId}`,
  );
  return data;
}

export async function createTestPlanSession(requirementId: number): Promise<TestPlanSession> {
  const { data } = await http.post<TestPlanSession>(
    "/api/test-plan/sessions",
    { requirement_id: requirementId },
  );
  return data;
}

export async function archiveTestPlanSession(sessionId: number): Promise<TestPlanSession> {
  const { data } = await http.put<TestPlanSession>(
    `/api/test-plan/sessions/${sessionId}/archive`,
  );
  return data;
}

export async function updateSessionCases(sessionId: number, cases: GeneratedTestCase[]): Promise<TestPlanSession> {
  const { data } = await http.put<TestPlanSession>(
    `/api/test-plan/sessions/${sessionId}/cases`,
    cases,
  );
  return data;
}

export async function updateTestPlan(
  sessionId: number,
  data: { plan_markdown: string; test_points: TestPoint[] },
): Promise<TestPlanSession> {
  const { data: resp } = await http.put<TestPlanSession>(
    `/api/test-plan/sessions/${sessionId}/plan`,
    data,
  );
  return resp;
}

// ===================== Generate / Confirm APIs =====================

export async function generateTestPlan(
  requirementId: number,
  sessionId?: number | null,
): Promise<TestPlanResponse> {
  const { data } = await http.post<TestPlanResponse>(
    "/api/test-plan/generate",
    { requirement_id: requirementId, session_id: sessionId ?? undefined },
    { timeout: LONG_LLM_TIMEOUT_MS },
  );
  return data;
}

export async function generateTestCases(payload: TestCaseGenRequest): Promise<TestCaseGenResponse> {
  const { data } = await http.post<TestCaseGenResponse>(
    "/api/test-plan/generate-cases",
    payload,
    { timeout: LONG_LLM_TIMEOUT_MS },
  );
  return data;
}

export async function confirmTestCases(payload: TestCaseConfirmRequest): Promise<TestCaseConfirmResponse> {
  const { data } = await http.post<TestCaseConfirmResponse>(
    "/api/test-plan/confirm-cases",
    payload,
  );
  return data;
}
