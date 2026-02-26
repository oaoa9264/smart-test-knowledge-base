export type RiskLevel = "critical" | "high" | "medium" | "low";
export type NodeType = "root" | "condition" | "branch" | "action" | "exception";
export type NodeStatus = "active" | "modified" | "deleted";
export type TestCaseStatus = "active" | "needs_review" | "invalidated";

export interface Project {
  id: number;
  name: string;
  description?: string;
}

export interface Requirement {
  id: number;
  project_id: number;
  title: string;
  raw_text: string;
  source_type: "prd" | "flowchart" | "api_doc";
}

export interface RuleNode {
  id: string;
  requirement_id: number;
  parent_id: string | null;
  node_type: NodeType;
  content: string;
  risk_level: RiskLevel;
  version: number;
  status: NodeStatus;
}

export interface RulePath {
  id: string;
  requirement_id: number;
  node_sequence: string[];
}

export interface RuleTree {
  nodes: RuleNode[];
  paths: RulePath[];
}

export interface TestCase {
  id: number;
  project_id: number;
  title: string;
  steps: string;
  expected_result: string;
  risk_level: RiskLevel;
  status: TestCaseStatus;
  bound_rule_node_ids: string[];
  bound_path_ids: string[];
}

export interface CoverageRow {
  node_id: string;
  content: string;
  risk_level: RiskLevel;
  covered_cases: number;
  uncovered_paths: number;
}

export interface CoverageSummary {
  total_nodes: number;
  covered_nodes: number;
  coverage_rate: number;
  uncovered_critical: string[];
  uncovered_paths: string[][];
}

export interface CoverageMatrix {
  rows: CoverageRow[];
  summary: CoverageSummary;
}

export interface AIParseNode {
  id: string;
  type: NodeType;
  content: string;
  parent_id: string | null;
}

export interface AIParseResult {
  nodes: AIParseNode[];
}

export interface ImpactResult {
  affected_case_ids: number[];
  needs_review_case_ids: number[];
  affected_count: number;
}

export interface DecisionTreeNode {
  id: string;
  type: NodeType;
  content: string;
  parent_id: string | null;
  risk_level: RiskLevel;
}

export interface RiskPoint {
  id: string;
  description: string;
  severity: RiskLevel;
  mitigation: string;
  related_node_ids: string[];
}

export interface GeneratedTestCase {
  title: string;
  steps: string;
  expected_result: string;
  risk_level: RiskLevel;
  related_node_ids: string[];
}

export interface ArchitectureAnalysisResult {
  id: number;
  decision_tree: { nodes: DecisionTreeNode[] };
  test_plan: { markdown: string; sections: string[] };
  risk_points: RiskPoint[];
  test_cases: GeneratedTestCase[];
}

export interface ArchitectureAnalysisDetail {
  id: number;
  project_id: number;
  requirement_id: number | null;
  title: string;
  image_path: string | null;
  description_text: string | null;
  status: "pending" | "completed" | "imported";
  created_at: string;
  result: Omit<ArchitectureAnalysisResult, "id"> | null;
}

export interface ArchitectureImportOptions {
  import_decision_tree: boolean;
  import_test_cases: boolean;
  import_risk_points: boolean;
}

export interface ArchitectureImportResult {
  analysis_id: number;
  requirement_id: number | null;
  imported_rule_nodes: number;
  imported_test_cases: number;
  updated_risk_nodes: number;
}
