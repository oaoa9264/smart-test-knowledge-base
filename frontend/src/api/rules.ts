import { http } from "./client";
import type { AIParseResult, ImpactResult, RuleNode, RuleTree } from "../types";

export async function fetchRuleTree(requirementId: number): Promise<RuleTree> {
  const { data } = await http.get<RuleTree>(`/api/rules/requirements/${requirementId}/tree`);
  return data;
}

export async function createRuleNode(payload: {
  requirement_id: number;
  parent_id: string | null;
  node_type: string;
  content: string;
  risk_level: string;
}): Promise<RuleNode> {
  const { data } = await http.post<RuleNode>("/api/rules/nodes", payload);
  return data;
}

export async function updateRuleNode(
  nodeId: string,
  payload: { parent_id?: string | null; node_type?: string; content?: string; risk_level?: string; status?: string },
): Promise<{ node: RuleNode; impact: ImpactResult }> {
  const { data } = await http.put<{ node: RuleNode; impact: ImpactResult }>(`/api/rules/nodes/${nodeId}`, payload);
  return data;
}

export async function deleteRuleNode(nodeId: string): Promise<{ ok: boolean; impact: ImpactResult }> {
  const { data } = await http.delete<{ ok: boolean; impact: ImpactResult }>(`/api/rules/nodes/${nodeId}`);
  return data;
}

export async function previewImpact(payload: {
  requirement_id: number;
  changed_node_ids: string[];
}): Promise<ImpactResult> {
  const { data } = await http.post<ImpactResult>("/api/rules/impact", payload);
  return data;
}

export async function aiParse(raw_text: string): Promise<AIParseResult> {
  const { data } = await http.post<AIParseResult>("/api/ai/parse", { raw_text });
  return data;
}
