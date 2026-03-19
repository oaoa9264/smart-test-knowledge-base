import type {
  ImportAnalysisMode,
  NodeType,
  RecoMode,
  RiskAnalysisTaskStatus,
  RiskLevel,
  TestCaseStatus,
} from "../types";

type RequirementInputType = "raw_requirement" | "pm_addendum" | "test_clarification" | "review_note";
type ArchitectureAnalysisMode = "llm" | "mock" | "mock_fallback" | "llm_failed";
type TestPointType = "normal" | "exception" | "boundary";

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

export const requirementInputTypeLabels: Record<RequirementInputType, string> = {
  raw_requirement: "原始需求",
  pm_addendum: "PM 补充",
  test_clarification: "测试澄清",
  review_note: "评审备注",
};

export const importAnalysisModeLabels: Record<ImportAnalysisMode, string> = {
  llm: "大模型解析",
  mock_fallback: "关键词兜底",
  llm_failed: "模型调用失败",
};

export const architectureAnalysisModeLabels: Record<ArchitectureAnalysisMode, string> = {
  llm: "大模型分析",
  mock: "规则模板分析",
  mock_fallback: "模板降级分析",
  llm_failed: "模型调用失败",
};

export const recoModeLabels: Record<RecoMode, string> = {
  FULL: "全量回归",
  CHANGE: "变更回归",
};

export const riskAnalysisTaskStatusLabels: Record<RiskAnalysisTaskStatus, string> = {
  queued: "排队中",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  interrupted: "已中断",
};

export const testPointTypeLabels: Record<TestPointType, string> = {
  normal: "普通",
  exception: "异常",
  boundary: "边界",
};

function getMappedLabel<T extends string>(labels: Record<T, string>, value?: string): string {
  if (!value) return "-";
  return labels[value as T] || value;
}

export function getRiskLevelLabel(value?: string): string {
  return getMappedLabel(riskLevelLabels, value);
}

export function getNodeTypeLabel(value?: string): string {
  return getMappedLabel(nodeTypeLabels, value);
}

export function getTestCaseStatusLabel(value?: string): string {
  return getMappedLabel(testCaseStatusLabels, value);
}

export function getSourceTypeLabel(value?: string): string {
  return getMappedLabel(sourceTypeLabels, value);
}

export function getRequirementInputTypeLabel(value?: string): string {
  return getMappedLabel(requirementInputTypeLabels, value);
}

export function getImportAnalysisModeLabel(value?: string): string {
  return getMappedLabel(importAnalysisModeLabels, value);
}

export function getArchitectureAnalysisModeLabel(value?: string): string {
  return getMappedLabel(architectureAnalysisModeLabels, value);
}

export function getRecoModeLabel(value?: string): string {
  return getMappedLabel(recoModeLabels, value);
}

export function getRiskAnalysisTaskStatusLabel(value?: string): string {
  return getMappedLabel(riskAnalysisTaskStatusLabels, value);
}

export function getTestPointTypeLabel(value?: string): string {
  return getMappedLabel(testPointTypeLabels, value);
}
