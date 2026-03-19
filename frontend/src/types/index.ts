export type RiskLevel = "critical" | "high" | "medium" | "low";
export type NodeType = "root" | "condition" | "branch" | "action" | "exception";
export type NodeStatus = "active" | "modified" | "deleted";
export type TestCaseStatus = "active" | "needs_review" | "invalidated";
export type LLMStatus = "success" | "failed";

export interface LLMExecutionMeta {
  llm_status?: LLMStatus | null;
  llm_provider?: string | null;
  llm_message?: string | null;
}

export interface Project {
  id: number;
  name: string;
  description?: string;
  product_code?: string | null;
}

export interface Requirement {
  id: number;
  project_id: number;
  title: string;
  raw_text: string;
  source_type: "prd" | "flowchart" | "api_doc";
  version: number;
  requirement_group_id: number | null;
}

export interface RequirementVersion extends Requirement {
  rule_node_count: number;
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

export interface DiffNodeItem {
  node_id: string;
  node_type: NodeType;
  content: string;
  risk_level: RiskLevel;
  parent_id: string | null;
}

export interface DiffNodeChange {
  status: "added" | "removed" | "modified" | "unchanged";
  current: DiffNodeItem | null;
  previous: DiffNodeItem | null;
  changed_fields: string[] | null;
}

export interface TreeDiffResult {
  base_version: number;
  compare_version: number;
  summary: {
    added: number;
    removed: number;
    modified: number;
    unchanged: number;
  };
  node_changes: DiffNodeChange[];
}

export interface TreeDiffSummaryResult {
  base_version: number;
  compare_version: number;
  summary: string;
}

export interface FlowChange {
  change_type: "added" | "removed" | "modified";
  title?: string | null;
  before?: string | null;
  after?: string | null;
  description: string;
  detail?: string | null;
  impact: "low" | "medium" | "high";
  test_suggestion?: string | null;
}

export interface RiskNote {
  risk: string;
  suggestion: string;
}

export interface SemanticDiffResult {
  base_version: number;
  compare_version: number;
  flow_changes: FlowChange[];
  summary: string;
  key_changes?: string[] | null;
  risk_notes?: string | null;
  risks?: RiskNote[] | null;
}

export interface DiffRecordRead {
  id: number;
  base_requirement_id: number;
  compare_requirement_id: number;
  base_version: number;
  compare_version: number;
  diff_type: string;
  created_at: string;
  result: SemanticDiffResult;
}

export type RuleTreeSessionStatus =
  | "active"
  | "generating"
  | "reviewing"
  | "saving"
  | "completed"
  | "failed"
  | "interrupted"
  | "confirmed"
  | "archived"
  | string;

export type RuleTreeProgressStage =
  | "queued"
  | "generating"
  | "reviewing"
  | "saving"
  | "completed"
  | "failed"
  | "interrupted"
  | string;

export interface RuleTreeSession {
  id: number;
  requirement_id: number;
  title: string;
  status: RuleTreeSessionStatus;
  confirmed_tree_snapshot: string | null;
  requirement_text_snapshot: string | null;
  progress_stage: RuleTreeProgressStage | null;
  progress_message: string | null;
  progress_percent: number | null;
  last_error: string | null;
  generated_tree_snapshot: string | null;
  reviewed_tree_snapshot: string | null;
  current_task_started_at: string | null;
  current_task_finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuleTreeMessage {
  id: number;
  session_id: number;
  role: "system" | "user" | "assistant" | string;
  content: string;
  message_type: string;
  tree_snapshot: string | null;
  created_at: string;
}

export interface RuleTreeSessionDetail {
  session: RuleTreeSession;
  messages: RuleTreeMessage[];
}

export interface RuleTreeSessionGenerateAcceptedResult {
  accepted: boolean;
  session: RuleTreeSession;
}

export interface RuleTreeSessionGenerateResult {
  session: RuleTreeSession;
  generated_tree: { decision_tree: { nodes: DecisionTreeNode[] } };
  reviewed_tree: { decision_tree: { nodes: DecisionTreeNode[] } };
  diff: {
    summary: { added: number; deleted: number; modified: number; unchanged: number };
    node_changes: Array<Record<string, unknown>>;
  };
}

export interface RuleTreeSessionUpdateResult {
  session: RuleTreeSession;
  updated_tree: { decision_tree: { nodes: DecisionTreeNode[] } };
  requirement_diff: string;
  node_diff: {
    summary: { added: number; deleted: number; modified: number; unchanged: number };
    node_changes: Array<Record<string, unknown>>;
  };
}

export interface TestCase {
  id: number;
  project_id: number;
  title: string;
  precondition: string;
  steps: string;
  expected_result: string;
  risk_level: RiskLevel;
  status: TestCaseStatus;
  bound_rule_node_ids: string[];
  bound_path_ids: string[];
}

export type ImportConfidence = "high" | "medium" | "low" | "none";
export type ImportAnalysisMode = "llm" | "mock_fallback" | "llm_failed";

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

export interface ImportParseResponse extends LLMExecutionMeta {
  parsed_cases: ParsedCasePreview[];
  total_cases: number;
  auto_matched: number;
  need_review: number;
  analysis_mode: ImportAnalysisMode;
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
  node_type: NodeType;
  coverable: boolean;
  risk_level: RiskLevel;
  covered_cases: number;
  uncovered_paths: number;
}

export interface CoverageSummary {
  total_nodes: number;
  covered_nodes: number;
  structural_nodes: number;
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

export interface AIParseResult extends LLMExecutionMeta {
  analysis_mode: "llm" | "mock" | "mock_fallback" | "llm_failed";
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

export interface ArchitectureAnalysisResult extends LLMExecutionMeta {
  id: number;
  analysis_mode: "llm" | "mock" | "mock_fallback" | "llm_failed";
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

export type RiskCategory =
  | "input_validation"
  | "flow_gap"
  | "data_integrity"
  | "boundary"
  | "security"
  | "product_knowledge";

export type RiskSource = "rule_tree" | "product_knowledge";

export type RiskDecisionType = "pending" | "accepted" | "ignored";
export type RiskValidity = "active" | "superseded" | "reopened" | "resolved";
export type AnalysisStage = "review" | "pre_dev" | "pre_release";

export interface RiskItem {
  id: string;
  requirement_id: number;
  related_node_id: string | null;
  category: RiskCategory;
  risk_level: RiskLevel;
  description: string;
  suggestion: string;
  decision: RiskDecisionType;
  decision_reason: string | null;
  decided_at: string | null;
  risk_source: RiskSource;
  clarification_text: string | null;
  doc_update_needed: boolean;
  analysis_stage: AnalysisStage | null;
  validity: RiskValidity | null;
  origin_snapshot_id: number | null;
  last_seen_snapshot_id: number | null;
  last_analysis_at: string | null;
  created_at: string | null;
}

export interface RiskListResponse {
  risks: RiskItem[];
  total: number;
  pending: number;
  accepted: number;
  ignored: number;
  active: number;
  superseded: number;
  reopened: number;
  resolved: number;
}

export interface RiskAnalyzeResponse {
  risks: RiskItem[];
  total: number;
}

export interface RequirementInput {
  id: number;
  requirement_id: number;
  input_type: string;
  content: string;
  source_label: string | null;
  created_by: string | null;
  created_at: string | null;
}

export interface EffectiveField {
  id: number;
  snapshot_id: number;
  field_key: string;
  value: string | null;
  derivation: string | null;
  confidence: number | null;
  source_refs: string | null;
  notes: string | null;
  sort_order: number;
}

export interface EffectiveSnapshot {
  id: number;
  requirement_id: number;
  stage: AnalysisStage;
  status: string;
  based_on_input_ids: string | null;
  summary: string | null;
  base_snapshot_id: number | null;
  created_at: string | null;
  fields: EffectiveField[];
}

export interface RiskItemCompact {
  id: string;
  category: string;
  risk_level: string;
  description: string;
  suggestion: string;
  validity: RiskValidity | null;
  analysis_stage: AnalysisStage | null;
}

export interface ConflictItem {
  conflict_type: string;
  description: string;
  source_a: string;
  source_b: string;
}

export interface MatchedEvidence {
  evidence_statement: string;
  related_field_key: string;
  match_type: string;
}

export interface BlockingRisk {
  risk_id: string;
  reason: string;
  severity: string;
}

export interface ReopenedRisk {
  risk_id: string;
  reason: string;
}

export interface ResolvedRisk {
  risk_id: string;
  reason: string;
}

export interface ReviewSnapshotResponse {
  snapshot: EffectiveSnapshot;
  risks: RiskItemCompact[];
  clarification_hints: string[];
}

export interface PredevAnalysisResponse {
  snapshot: EffectiveSnapshot;
  risks: RiskItemCompact[];
  conflicts: ConflictItem[];
  matched_evidence: MatchedEvidence[];
}

export interface PrereleaseAuditResponse {
  closure_summary: string;
  blocking_risks: BlockingRisk[];
  reopened_risks: ReopenedRisk[];
  resolved_risks: ResolvedRisk[];
  audit_notes: string[];
}

export type RiskAnalysisTaskStatus = "queued" | "running" | "completed" | "failed" | "interrupted";

export interface RiskAnalysisTask {
  id: number;
  requirement_id: number;
  stage: AnalysisStage;
  status: RiskAnalysisTaskStatus;
  progress_message: string | null;
  progress_percent: number | null;
  last_error: string | null;
  snapshot_id: number | null;
  result_json: string | null;
  current_task_started_at: string | null;
  current_task_finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RiskAnalysisTaskSummary {
  review: RiskAnalysisTask | null;
  pre_dev: RiskAnalysisTask | null;
  pre_release: RiskAnalysisTask | null;
}

export interface RiskAnalysisTaskStartResponse {
  accepted: boolean;
  task: RiskAnalysisTask;
}

export interface ProductDoc {
  id: number;
  product_code: string;
  name: string;
  description?: string | null;
  file_path?: string | null;
  version: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProductDocChunk {
  id: number;
  product_doc_id: number;
  stage_key: string;
  title: string;
  content: string;
  sort_order: number;
  keywords?: string | null;
}

export interface ProductDocDetail extends ProductDoc {
  chunks: ProductDocChunk[];
}

export interface ProductDocUpdate {
  id: number;
  product_doc_id: number;
  chunk_id?: number | null;
  risk_item_id?: string | null;
  original_content?: string | null;
  suggested_content?: string | null;
  status: "pending" | "approved" | "rejected";
  reviewed_at?: string | null;
  applied_at?: string | null;
  created_at?: string | null;
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

export interface TestPoint {
  id: string;
  name: string;
  description: string;
  type: "normal" | "exception" | "boundary" | string;
  related_node_ids: string[];
  priority: "high" | "medium" | "low" | string;
}

export interface TestPlanResponse extends LLMExecutionMeta {
  markdown: string;
  test_points: TestPoint[];
  session_id?: number | null;
}

export interface GeneratedTestCase {
  title: string;
  preconditions: string[] | string;
  steps: string[] | string;
  expected_result: string[] | string;
  risk_level: string;
  related_node_ids: string[];
}

export interface TestCaseGenRequest {
  requirement_id: number;
  test_plan_markdown: string;
  test_points: TestPoint[];
  session_id?: number | null;
}

export interface TestCaseGenResponse extends LLMExecutionMeta {
  test_cases: GeneratedTestCase[];
  session_id?: number | null;
}

export interface TestCaseConfirmRequest {
  requirement_id: number;
  test_cases: GeneratedTestCase[];
  session_id?: number | null;
}

export interface TestCaseConfirmResponse {
  created_count: number;
  created_case_ids: number[];
}

export type TestPlanSessionStatus =
  | "plan_generating"
  | "plan_generated"
  | "cases_generating"
  | "cases_generated"
  | "confirmed"
  | "archived";

export interface TestPlanSession {
  id: number;
  requirement_id: number;
  status: TestPlanSessionStatus;
  plan_markdown: string | null;
  test_points: TestPoint[] | null;
  generated_cases: GeneratedTestCase[] | null;
  confirmed_case_ids: number[] | null;
  created_at: string;
  updated_at: string;
}

export interface TestPlanSessionListResponse {
  sessions: TestPlanSession[];
}
