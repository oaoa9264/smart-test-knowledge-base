import { http } from "./client";
import type { TestCase } from "../types";

export async function fetchTestCases(projectId: number, requirementId?: number): Promise<TestCase[]> {
  const { data } = await http.get<TestCase[]>(`/api/testcases/projects/${projectId}`, {
    params: requirementId ? { requirement_id: requirementId } : undefined,
  });
  return data;
}

export async function createTestCase(payload: {
  project_id: number;
  title: string;
  steps: string;
  expected_result: string;
  risk_level: string;
  status: string;
  bound_rule_node_ids: string[];
  bound_path_ids: string[];
}): Promise<TestCase> {
  const { data } = await http.post<TestCase>("/api/testcases", payload);
  return data;
}

export async function updateTestCase(
  caseId: number,
  payload: {
    title: string;
    steps: string;
    expected_result: string;
    risk_level: string;
    status: string;
    bound_rule_node_ids: string[];
    bound_path_ids: string[];
  },
): Promise<TestCase> {
  const { data } = await http.put<TestCase>(`/api/testcases/${caseId}`, payload);
  return data;
}

export async function fetchTestCase(caseId: number): Promise<TestCase> {
  const { data } = await http.get<TestCase>(`/api/testcases/${caseId}`);
  return data;
}

export async function deleteTestCase(caseId: number): Promise<void> {
  await http.delete(`/api/testcases/${caseId}`);
}
