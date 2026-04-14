import { http } from "./client";
import type {
  ClarificationReviewAnalyzeRequest,
  ClarificationReviewRecord,
  ClarificationReviewRecordSummary,
} from "../types";

export async function analyzeClarificationReview(
  payload: ClarificationReviewAnalyzeRequest,
): Promise<ClarificationReviewRecord> {
  const { data } = await http.post<ClarificationReviewRecord>("/api/ai/clarification-review/analyze", payload, {
    timeout: 120000,
  });
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

