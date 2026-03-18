# Frontend Enum Localization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Localize all user-facing enum values in the frontend to Chinese without changing backend API values or stored data.

**Architecture:** Extend the existing shared enum label helper module in `frontend/src/utils/enumLabels.ts`, then replace remaining raw enum renders across pages with centralized label helpers. Keep API payload values unchanged and limit the change to display-layer text.

**Tech Stack:** React, TypeScript, Vite, Ant Design

---

### Task 1: Expand shared enum label helpers

**Files:**
- Modify: `frontend/src/utils/enumLabels.ts`

**Step 1: Write the failing test**

Create a lightweight TypeScript verification script or compile check that references the new helper exports and expected labels. The initial run should fail because the helpers do not exist yet.

**Step 2: Run test to verify it fails**

Run: `cd frontend && npx tsc --noEmit`

Expected: FAIL after adding references to missing helpers.

**Step 3: Write minimal implementation**

Add centralized label maps and helper functions for:
- requirement input type
- import analysis mode
- architecture analysis mode
- recommendation mode
- risk analysis task status

**Step 4: Run test to verify it passes**

Run: `cd frontend && npx tsc --noEmit`

Expected: PASS

### Task 2: Replace raw enum displays in user-facing pages

**Files:**
- Modify: `frontend/src/pages/RuleTree/RiskPanel.tsx`
- Modify: `frontend/src/pages/ArchitectureAnalysis/index.tsx`
- Modify: `frontend/src/pages/Recommendation/index.tsx`
- Modify: `frontend/src/pages/TestCases/index.tsx`
- Modify: other frontend pages that still render raw enum strings to users

**Step 1: Write the failing test**

Add or update the same compile-time verification to reference the page-level helper usage, making the build fail until each page imports the shared label helpers correctly.

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm run build`

Expected: FAIL while pages still rely on raw enum labels or missing imports.

**Step 3: Write minimal implementation**

Replace raw user-facing enum output with shared Chinese label helpers. Preserve existing payload values, filters, and request params.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm run build`

Expected: PASS

### Task 3: Verify coverage and fallback behavior

**Files:**
- Modify: `frontend/src/utils/enumLabels.ts`

**Step 1: Write the failing test**

Add final compile-time checks for fallback behavior so unknown values still render the original value instead of crashing.

**Step 2: Run test to verify it fails**

Run: `cd frontend && npx tsc --noEmit`

Expected: FAIL until fallback helpers are complete.

**Step 3: Write minimal implementation**

Ensure all helper functions return `"-"` for empty values and the raw value for unknown values.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npx tsc --noEmit && npm run build`

Expected: PASS
