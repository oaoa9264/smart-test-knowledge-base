import { http } from "./client";
import type {
  ClarificationReviewAnalyzeRequest,
  ClarificationReviewPdfDraft,
  ClarificationReviewRecord,
  ClarificationReviewRecordSummary,
} from "../types";

export async function analyzeClarificationReview(
  payload: ClarificationReviewAnalyzeRequest,
): Promise<ClarificationReviewRecord> {
  const { data } = await http.post<ClarificationReviewRecord>("/api/ai/clarification-review/analyze", payload, {
    timeout: 600000,
  });
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
      timeout: 180000,
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
    undefined,
    { timeout: 180000 },
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
