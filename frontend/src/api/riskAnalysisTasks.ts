import { http } from "./client";
import type { AnalysisStage, RiskAnalysisTask, RiskAnalysisTaskStartResponse, RiskAnalysisTaskSummary } from "../types";

export async function startRiskAnalysisTask(
  requirementId: number,
  stage: AnalysisStage,
): Promise<RiskAnalysisTaskStartResponse> {
  const { data } = await http.post<RiskAnalysisTaskStartResponse>(
    `/api/requirements/${requirementId}/analysis-tasks/${stage}`,
  );
  return data;
}

export async function fetchRiskAnalysisTask(
  requirementId: number,
  stage: AnalysisStage,
): Promise<RiskAnalysisTask | null> {
  const { data } = await http.get<RiskAnalysisTask | null>(
    `/api/requirements/${requirementId}/analysis-tasks/${stage}`,
  );
  return data;
}

export async function fetchRiskAnalysisTaskSummary(
  requirementId: number,
): Promise<RiskAnalysisTaskSummary> {
  const { data } = await http.get<RiskAnalysisTaskSummary>(
    `/api/requirements/${requirementId}/analysis-tasks`,
  );
  return data;
}
