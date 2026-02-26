import { http } from "./client";
import type { Project, Requirement } from "../types";

export async function fetchProjects(): Promise<Project[]> {
  const { data } = await http.get<Project[]>("/api/projects");
  return data;
}

export async function createProject(payload: { name: string; description?: string }): Promise<Project> {
  const { data } = await http.post<Project>("/api/projects", payload);
  return data;
}

export async function updateProject(projectId: number, payload: { name: string; description?: string }): Promise<Project> {
  const { data } = await http.put<Project>(`/api/projects/${projectId}`, payload);
  return data;
}

export async function deleteProject(projectId: number): Promise<void> {
  await http.delete(`/api/projects/${projectId}`);
}

export async function fetchRequirements(projectId: number): Promise<Requirement[]> {
  const { data } = await http.get<Requirement[]>(`/api/projects/${projectId}/requirements`);
  return data;
}

export async function createRequirement(
  projectId: number,
  payload: { title: string; raw_text: string; source_type: "prd" | "flowchart" | "api_doc" },
): Promise<Requirement> {
  const { data } = await http.post<Requirement>(`/api/projects/${projectId}/requirements`, payload);
  return data;
}

export async function updateRequirement(
  projectId: number,
  requirementId: number,
  payload: { title: string; raw_text: string; source_type: "prd" | "flowchart" | "api_doc" },
): Promise<Requirement> {
  const { data } = await http.put<Requirement>(`/api/projects/${projectId}/requirements/${requirementId}`, payload);
  return data;
}

export async function deleteRequirement(projectId: number, requirementId: number): Promise<void> {
  await http.delete(`/api/projects/${projectId}/requirements/${requirementId}`);
}
