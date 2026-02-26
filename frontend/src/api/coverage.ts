import { http } from "./client";
import type { CoverageMatrix } from "../types";

export async function fetchCoverage(projectId: number, requirementId: number): Promise<CoverageMatrix> {
  const { data } = await http.get<CoverageMatrix>(`/api/coverage/projects/${projectId}/requirements/${requirementId}`);
  return data;
}
