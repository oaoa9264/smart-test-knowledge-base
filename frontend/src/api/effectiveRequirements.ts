import { http } from "./client";
import type {
  EffectiveSnapshot,
  PredevAnalysisResponse,
  PrereleaseAuditResponse,
  RequirementInput,
  ReviewSnapshotResponse,
} from "../types";

const LONG_LLM_TIMEOUT_MS = 180000;

export async function createReviewSnapshot(requirementId: number): Promise<ReviewSnapshotResponse> {
  const { data } = await http.post<ReviewSnapshotResponse>(
    `/api/requirements/${requirementId}/snapshots/review`,
  );
  return data;
}

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

export async function runPredevAnalysis(requirementId: number): Promise<PredevAnalysisResponse> {
  const { data } = await http.post<PredevAnalysisResponse>(
    "/api/ai/risks/predev-analyze",
    { requirement_id: requirementId },
    { timeout: LONG_LLM_TIMEOUT_MS },
  );
  return data;
}

export async function runPrereleaseAudit(requirementId: number): Promise<PrereleaseAuditResponse> {
  const { data } = await http.post<PrereleaseAuditResponse>(
    "/api/ai/risks/prerelease-audit",
    { requirement_id: requirementId },
    { timeout: LONG_LLM_TIMEOUT_MS },
  );
  return data;
}
