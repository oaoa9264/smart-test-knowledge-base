import type { NodeType, RiskLevel, TestCaseStatus } from "../types";

export const riskLevelLabels: Record<RiskLevel, string> = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
};

export const nodeTypeLabels: Record<NodeType, string> = {
  root: "根节点",
  condition: "条件",
  branch: "分支",
  action: "动作",
  exception: "异常",
};

export const testCaseStatusLabels: Record<TestCaseStatus, string> = {
  active: "有效",
  needs_review: "待复核",
  invalidated: "已失效",
};

export const sourceTypeLabels: Record<"prd" | "flowchart" | "api_doc", string> = {
  prd: "需求文档",
  flowchart: "流程图",
  api_doc: "接口文档",
};

export function getRiskLevelLabel(value?: string): string {
  if (!value) return "-";
  return riskLevelLabels[value as RiskLevel] || value;
}

export function getNodeTypeLabel(value?: string): string {
  if (!value) return "-";
  return nodeTypeLabels[value as NodeType] || value;
}

export function getTestCaseStatusLabel(value?: string): string {
  if (!value) return "-";
  return testCaseStatusLabels[value as TestCaseStatus] || value;
}

export function getSourceTypeLabel(value?: string): string {
  if (!value) return "-";
  return sourceTypeLabels[value as "prd" | "flowchart" | "api_doc"] || value;
}
