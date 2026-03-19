import { http } from "./client";
import type { NormalizedRequirementDocPreview } from "../types";

export async function fetchNormalizedRequirementDocPreview(
  requirementId: number,
): Promise<NormalizedRequirementDocPreview> {
  const { data } = await http.post<NormalizedRequirementDocPreview>(
    `/api/requirements/${requirementId}/normalized-doc/preview`,
  );
  return data;
}
