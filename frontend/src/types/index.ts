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

export type ImportConfidence = "high" | "medium" | "low" | "none";
export type ImportAnalysisMode = "llm" | "mock_fallback";

export interface ParsedCasePreview {
  index: number;
  title: string;
  steps: string;
  expected_result: string;
  matched_node_ids: string[];
  matched_node_contents: string[];
  suggested_risk_level?: RiskLevel;
  confidence: ImportConfidence;
  match_reason: string;
}

export interface ImportParseResponse {
  parsed_cases: ParsedCasePreview[];
  total_cases: number;
  auto_matched: number;
  need_review: number;
  analysis_mode: ImportAnalysisMode;
  llm_provider?: "openai" | "zhipu" | string | null;
}

export interface ImportConfirmCasePayload {
  title: string;
  steps: string;
  expected_result: string;
  risk_level: RiskLevel;
  bound_rule_node_ids: string[];
  bound_path_ids: string[];
  skip_import?: boolean;
}

export interface ImportConfirmPayload {
  requirement_id: number;
  project_id: number;
  cases: ImportConfirmCasePayload[];
}

export interface ImportConfirmResponse {
  imported_count: number;
  bound_count: number;
  skipped_count: number;
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
  analysis_mode: "llm" | "mock" | "mock_fallback";
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

export interface ArchitectureAnalysisResult {
  id: number;
  analysis_mode: "llm" | "mock" | "mock_fallback";
  llm_provider?: "openai" | "zhipu" | string | null;
  decision_tree: { nodes: DecisionTreeNode[] };
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
}

export interface ArchitectureImportResult {
  analysis_id: number;
  requirement_id: number | null;
  imported_rule_nodes: number;
}

export type RecoMode = "FULL" | "CHANGE";

export interface RecoContributor {
  node_id: string;
  risk: number;
}

export interface RecoCaseResult {
  rank: number;
  case_id: number;
  gain_risk: number;
  gain_nodes: string[];
  top_contributors: RecoContributor[];
  why_selected: string;
}

export interface RecoSummary {
  k: number;
  picked: number;
  covered_risk: number;
  total_target_risk: number;
  coverage_ratio: number;
}

export interface RecoGap {
  node_id: string;
  risk: number;
}

export interface RecoResponse {
  run_id: number;
  summary: RecoSummary;
  cases: RecoCaseResult[];
  remaining_high_risk_gaps: RecoGap[];
}

export interface RecoRun {
  id: number;
  requirement_id: number;
  mode: RecoMode;
  k: number;
  input_changed_node_ids: string[];
  total_target_risk: number;
  covered_risk: number;
  coverage_ratio: number;
  created_at: string;
}

export interface RecoResultRow {
  id: number;
  run_id: number;
  rank: number;
  case_id: number;
  gain_risk: number;
  gain_node_ids: string[];
  top_contributors: RecoContributor[];
  why_selected: string;
}

export interface RecoRunDetail {
  run: RecoRun;
  results: RecoResultRow[];
}

export interface RecoCaseFilter {
  status_in?: TestCaseStatus[];
  case_ids?: number[];
}

export interface RecoRequest {
  requirement_id: number;
  mode: RecoMode;
  k: number;
  changed_node_ids?: string[];
  case_filter?: RecoCaseFilter;
  cost_mode?: "UNIT" | "TIME";
}
