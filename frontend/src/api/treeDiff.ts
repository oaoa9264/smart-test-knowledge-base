import { http } from "./client";
import type { DiffRecordRead, SemanticDiffResult } from "../types";

export async function fetchSemanticDiff(
  baseRequirementId: number,
  compareRequirementId: number,
): Promise<SemanticDiffResult> {
  const { data } = await http.get<SemanticDiffResult>("/api/rules/diff", {
    params: { base_requirement_id: baseRequirementId, compare_requirement_id: compareRequirementId },
    timeout: 360000,
  });
  return data;
}

export async function fetchDiffHistory(
  projectId: number,
  requirementGroupId?: number,
): Promise<DiffRecordRead[]> {
  const { data } = await http.get<DiffRecordRead[]>("/api/rules/diff/history", {
    params: {
      project_id: projectId,
      ...(requirementGroupId != null ? { requirement_group_id: requirementGroupId } : {}),
    },
  });
  return data;
}

export async function fetchDiffRecord(recordId: number): Promise<DiffRecordRead> {
  const { data } = await http.get<DiffRecordRead>(`/api/rules/diff/history/${recordId}`);
  return data;
}

export async function deleteDiffRecord(recordId: number): Promise<void> {
  await http.delete(`/api/rules/diff/history/${recordId}`);
}
