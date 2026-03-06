import { http } from "./client";
import type { RiskAnalyzeResponse, RiskItem, RiskListResponse, RuleNode } from "../types";

export async function analyzeRisks(requirementId: number): Promise<RiskAnalyzeResponse> {
  const { data } = await http.post<RiskAnalyzeResponse>("/api/ai/risks/analyze", {
    requirement_id: requirementId,
  });
  return data;
}

export async function fetchRisks(requirementId: number): Promise<RiskListResponse> {
  const { data } = await http.get<RiskListResponse>(
    `/api/rules/requirements/${requirementId}/risks`,
  );
  return data;
}

export async function decideRisk(
  riskId: string,
  decision: "accepted" | "ignored",
  reason: string,
  autoCreateNode = false,
): Promise<RiskItem> {
  const { data } = await http.put<RiskItem>(`/api/rules/risks/${riskId}/decision`, {
    decision,
    reason,
    auto_create_node: autoCreateNode,
  });
  return data;
}

export async function riskToNode(riskId: string): Promise<RuleNode> {
  const { data } = await http.post<RuleNode>(`/api/rules/risks/${riskId}/to-node`);
  return data;
}
