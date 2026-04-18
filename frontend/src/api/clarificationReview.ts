import { http } from "./client";
import type {
  ClarificationReviewAnalyzeRequest,
  ClarificationReviewPdfDraft,
  ClarificationReviewRecord,
  ClarificationReviewRecordSummary,
  ResolutionStatus,
} from "../types";

export interface ItemResolutionUpdate {
  item_type: "gap" | "assumption" | "question";
  role?: string;
  index: number;
  resolution_status: ResolutionStatus;
  resolution_note?: string;
  resolved_by?: string;
}

export async function analyzeClarificationReview(
  payload: ClarificationReviewAnalyzeRequest,
): Promise<ClarificationReviewRecord> {
  const { data } = await http.post<ClarificationReviewRecord>("/api/ai/clarification-review/analyze", payload);
  return data;
}

export async function createClarificationReviewPdfDraft(file: File): Promise<ClarificationReviewPdfDraft> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await http.post<ClarificationReviewPdfDraft>(
    "/api/ai/clarification-review/pdf-drafts",
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
    },
  );
  return data;
}

export async function fetchClarificationReviewPdfDraft(draftId: number): Promise<ClarificationReviewPdfDraft> {
  const { data } = await http.get<ClarificationReviewPdfDraft>(`/api/ai/clarification-review/pdf-drafts/${draftId}`);
  return data;
}

export async function inferClarificationReviewPdfDraft(draftId: number): Promise<ClarificationReviewPdfDraft> {
  const { data } = await http.post<ClarificationReviewPdfDraft>(
    `/api/ai/clarification-review/pdf-drafts/${draftId}/infer`,
  );
  return data;
}

export async function fetchClarificationReviewRecords(limit: number = 20): Promise<ClarificationReviewRecordSummary[]> {
  const { data } = await http.get<ClarificationReviewRecordSummary[]>("/api/ai/clarification-review/records", {
    params: { limit },
  });
  return data;
}

export async function fetchClarificationReviewRecord(recordId: number): Promise<ClarificationReviewRecord> {
  const { data } = await http.get<ClarificationReviewRecord>(`/api/ai/clarification-review/records/${recordId}`);
  return data;
}

export async function deleteClarificationReviewRecord(recordId: number): Promise<void> {
  await http.delete(`/api/ai/clarification-review/records/${recordId}`);
}

export async function updateClarificationReviewItemResolutions(
  recordId: number,
  updates: ItemResolutionUpdate[],
): Promise<ClarificationReviewRecord> {
  const { data } = await http.patch<ClarificationReviewRecord>(
    `/api/ai/clarification-review/records/${recordId}/items`,
    { updates },
  );
  return data;
}

export interface CreateRequirementFromReviewResponse {
  requirement: { id: number; project_id: number; title: string };
  record: ClarificationReviewRecord;
}

export async function createRequirementFromReview(
  recordId: number,
  projectId: number,
  title?: string,
): Promise<CreateRequirementFromReviewResponse> {
  const { data } = await http.post<CreateRequirementFromReviewResponse>(
    `/api/ai/clarification-review/records/${recordId}/create-requirement`,
    { project_id: projectId, title: title || "" },
  );
  return data;
}
