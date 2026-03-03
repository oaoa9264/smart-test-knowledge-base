import { http } from "./client";
import type { ImportConfirmPayload, ImportConfirmResponse, ImportParseResponse, TestCase } from "../types";

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

export async function parseImportFile(file: File, requirementId: number): Promise<ImportParseResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("requirement_id", String(requirementId));
  const { data } = await http.post<ImportParseResponse>("/api/testcases/import/parse", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
  return data;
}

export async function confirmImport(payload: ImportConfirmPayload): Promise<ImportConfirmResponse> {
  const { data } = await http.post<ImportConfirmResponse>("/api/testcases/import/confirm", payload);
  return data;
}
