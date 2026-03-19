import { http } from "./client";
import type {
  NormalizedRequirementDocTask,
  NormalizedRequirementDocTaskStartResponse,
} from "../types";

export async function startNormalizedRequirementDocTask(
  requirementId: number,
): Promise<NormalizedRequirementDocTaskStartResponse> {
  const { data } = await http.post<NormalizedRequirementDocTaskStartResponse>(
    `/api/requirements/${requirementId}/normalized-doc-tasks`,
  );
  return data;
}

export async function fetchLatestNormalizedRequirementDocTask(
  requirementId: number,
): Promise<NormalizedRequirementDocTask | null> {
  const { data } = await http.get<NormalizedRequirementDocTask | null>(
    `/api/requirements/${requirementId}/normalized-doc-tasks/latest`,
  );
  return data;
}
