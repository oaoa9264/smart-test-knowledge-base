import {
  getArchitectureAnalysisModeLabel,
  getImportAnalysisModeLabel,
  getRecoModeLabel,
  getRequirementInputTypeLabel,
  getRiskAnalysisTaskStatusLabel,
  getTestPointTypeLabel,
} from "./enumLabels";
import type { ArchitectureAnalysisResult, ImportAnalysisMode, ImportParseResponse } from "../types";

const requiredImportMode: ImportAnalysisMode = "llm_failed";
const requiredArchitectureMode: ArchitectureAnalysisResult["analysis_mode"] = "llm_failed";
const requiredImportLlmStatus: NonNullable<ImportParseResponse["llm_status"]> = "failed";
const requiredImportLlmMessage: NonNullable<ImportParseResponse["llm_message"]> =
  "所有模型调用失败，请稍后重试";

const requiredLabels = [
  getRequirementInputTypeLabel("raw_requirement"),
  getRequirementInputTypeLabel("pm_addendum"),
  getImportAnalysisModeLabel("mock_fallback"),
  getImportAnalysisModeLabel(requiredImportMode),
  getArchitectureAnalysisModeLabel("llm"),
  getArchitectureAnalysisModeLabel(requiredArchitectureMode),
  getRecoModeLabel("FULL"),
  getRiskAnalysisTaskStatusLabel("running"),
  getTestPointTypeLabel("exception"),
  requiredImportLlmStatus,
  requiredImportLlmMessage,
];

void requiredLabels;
