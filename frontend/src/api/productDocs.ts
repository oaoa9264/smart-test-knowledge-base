import { http } from "./client";
import type { ProductDoc, ProductDocChunk, ProductDocDetail, ProductDocUpdate } from "../types";

export async function importProductDoc(payload: {
  product_code: string;
  name: string;
  description?: string;
  content: string;
}): Promise<ProductDoc> {
  const { data } = await http.post<ProductDoc>("/api/product-docs/import", payload);
  return data;
}

export async function fetchProductDocs(): Promise<ProductDoc[]> {
  const { data } = await http.get<ProductDoc[]>("/api/product-docs");
  return data;
}

export async function fetchProductDoc(productCode: string): Promise<ProductDocDetail> {
  const { data } = await http.get<ProductDocDetail>(`/api/product-docs/${productCode}`);
  return data;
}

export async function updateChunk(
  productCode: string,
  chunkId: number,
  content: string,
): Promise<ProductDocChunk> {
  const { data } = await http.put<ProductDocChunk>(
    `/api/product-docs/${productCode}/chunks/${chunkId}`,
    { content },
  );
  return data;
}

export async function deleteProductDoc(productCode: string): Promise<void> {
  await http.delete(`/api/product-docs/${productCode}`);
}

export async function suggestDocUpdate(payload: {
  product_doc_id: number;
  risk_item_id?: string;
  clarification_text: string;
  supplement_text?: string;
}): Promise<ProductDocUpdate> {
  const { data } = await http.post<ProductDocUpdate>("/api/product-docs/suggest-update", payload);
  return data;
}

export async function fetchDocUpdates(productDocId?: number): Promise<ProductDocUpdate[]> {
  const params = productDocId ? { product_doc_id: productDocId } : {};
  const { data } = await http.get<ProductDocUpdate[]>("/api/product-docs/updates/list", { params });
  return data;
}

export async function applyDocUpdate(updateId: number): Promise<ProductDocUpdate> {
  const { data } = await http.put<ProductDocUpdate>(`/api/product-docs/updates/${updateId}/apply`);
  return data;
}

export async function rejectDocUpdate(updateId: number): Promise<ProductDocUpdate> {
  const { data } = await http.put<ProductDocUpdate>(`/api/product-docs/updates/${updateId}/reject`);
  return data;
}
