import { http } from "./client";
import type {
  EffectiveSnapshot,
  RequirementInput,
} from "../types";

export async function listSnapshots(requirementId: number): Promise<EffectiveSnapshot[]> {
  const { data } = await http.get<EffectiveSnapshot[]>(
    `/api/requirements/${requirementId}/snapshots`,
  );
  return data;
}

export async function getLatestSnapshot(
  requirementId: number,
  stage?: string,
): Promise<EffectiveSnapshot | null> {
  const { data } = await http.get<EffectiveSnapshot | null>(
    `/api/requirements/${requirementId}/snapshots/latest`,
    { params: stage ? { stage } : undefined },
  );
  return data;
}

export async function addRequirementInput(
  requirementId: number,
  payload: {
    input_type: string;
    content: string;
    source_label?: string;
    created_by?: string;
  },
): Promise<RequirementInput> {
  const { data } = await http.post<RequirementInput>(
    `/api/requirements/${requirementId}/inputs`,
    payload,
  );
  return data;
}

export async function listRequirementInputs(requirementId: number): Promise<RequirementInput[]> {
  const { data } = await http.get<RequirementInput[]>(
    `/api/requirements/${requirementId}/inputs`,
  );
  return data;
}
