import { http } from "./client";
import type { RecoRequest, RecoResponse, RecoRun, RecoRunDetail } from "../types";

export async function recommendRegression(payload: RecoRequest): Promise<RecoResponse> {
  const { data } = await http.post<RecoResponse>("/api/reco/regression", payload);
  return data;
}

export async function fetchRecoRuns(requirementId: number): Promise<RecoRun[]> {
  const { data } = await http.get<RecoRun[]>("/api/reco/runs", {
    params: { requirement_id: requirementId },
  });
  return data;
}

export async function fetchRecoRunDetail(runId: number): Promise<RecoRunDetail> {
  const { data } = await http.get<RecoRunDetail>(`/api/reco/runs/${runId}`);
  return data;
}
