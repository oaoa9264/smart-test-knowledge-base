import { http } from "./client";
import type { SemanticDiffResult } from "../types";

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
