import { http } from "./client";
import type {
  ArchitectureAnalysisDetail,
  ArchitectureAnalysisResult,
  ArchitectureImportOptions,
  ArchitectureImportResult,
} from "../types";

export async function analyzeArchitecture(formData: FormData): Promise<ArchitectureAnalysisResult> {
  const { data } = await http.post<ArchitectureAnalysisResult>("/api/ai/architecture/analyze", formData, {
    timeout: 120000,
  });
  return data;
}

export async function getArchitectureAnalysis(id: number): Promise<ArchitectureAnalysisDetail> {
  const { data } = await http.get<ArchitectureAnalysisDetail>(`/api/ai/architecture/${id}`);
  return data;
}

export async function importArchitectureAnalysis(
  id: number,
  options: ArchitectureImportOptions,
): Promise<ArchitectureImportResult> {
  const { data } = await http.post<ArchitectureImportResult>(`/api/ai/architecture/${id}/import`, options);
  return data;
}
