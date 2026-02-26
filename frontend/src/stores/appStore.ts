import { create } from "zustand";
import type { Project, Requirement } from "../types";

interface AppStore {
  projects: Project[];
  requirements: Requirement[];
  selectedProjectId: number | null;
  selectedRequirementId: number | null;
  setProjects: (projects: Project[]) => void;
  setRequirements: (requirements: Requirement[]) => void;
  setSelectedProjectId: (id: number | null) => void;
  setSelectedRequirementId: (id: number | null) => void;
}

export const useAppStore = create<AppStore>((set) => ({
  projects: [],
  requirements: [],
  selectedProjectId: null,
  selectedRequirementId: null,
  setProjects: (projects) => set({ projects }),
  setRequirements: (requirements) => set({ requirements }),
  setSelectedProjectId: (id) => set({ selectedProjectId: id, selectedRequirementId: null }),
  setSelectedRequirementId: (id) => set({ selectedRequirementId: id }),
}));
