import {
  getArchitectureAnalysisModeLabel,
  getImportAnalysisModeLabel,
  getRecoModeLabel,
  getRequirementInputTypeLabel,
  getRiskAnalysisTaskStatusLabel,
  getTestPointTypeLabel,
} from "./enumLabels";

const requiredLabels = [
  getRequirementInputTypeLabel("raw_requirement"),
  getRequirementInputTypeLabel("pm_addendum"),
  getImportAnalysisModeLabel("mock_fallback"),
  getArchitectureAnalysisModeLabel("llm"),
  getRecoModeLabel("FULL"),
  getRiskAnalysisTaskStatusLabel("running"),
  getTestPointTypeLabel("exception"),
];

void requiredLabels;
