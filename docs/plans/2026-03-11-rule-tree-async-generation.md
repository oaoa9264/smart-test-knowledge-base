# Rule Tree Async Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert rule-tree session generation into a persisted async workflow with recoverable progress after refresh/browser reopen.

**Architecture:** Reuse `RuleTreeSession` as the async task carrier. The generate API becomes a task starter, a background worker updates persisted session progress by stage, and the frontend restores state by polling session detail until the task reaches a terminal status.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React, TypeScript, Axios, Ant Design, pytest

---

### Task 1: Add persisted async session fields and startup recovery

**Files:**
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/schemas/rule_tree_session.py`
- Modify: `backend/app/core/schema_migrations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_rule_tree_session_async.py`

**Step 1: Write the failing test**

Add tests that assert:

- `RuleTreeSession` exposes async statuses and progress fields in API schemas.
- startup recovery marks in-progress sessions as `interrupted`.

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_rule_tree_session_async.py -k "startup_recovery or session_schema" -v`
Expected: FAIL because async fields/statuses do not exist.

**Step 3: Write minimal implementation**

Implement:

- new `RuleTreeSessionStatus` members
- new session columns for progress, error, snapshots, task timestamps
- schema migration helper for additive columns
- app startup hook or bootstrap function that marks `generating/reviewing/saving` sessions as `interrupted`
- schema serialization for the new fields

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_rule_tree_session_async.py -k "startup_recovery or session_schema" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/models/entities.py backend/app/schemas/rule_tree_session.py backend/app/core/schema_migrations.py backend/app/main.py backend/tests/test_rule_tree_session_async.py
git commit -m "feat: persist rule tree async session state"
```

### Task 2: Convert generate endpoint to async task starter

**Files:**
- Modify: `backend/app/api/rule_tree_session.py`
- Modify: `backend/app/services/rule_tree_session.py`
- Test: `backend/tests/test_rule_tree_session_async.py`

**Step 1: Write the failing test**

Add tests that assert:

- `POST /api/rules/sessions/{id}/generate` returns immediately with accepted session state
- starting generation on an already running session returns a conflict/error

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_rule_tree_session_async.py -k "generate_returns_immediately or duplicate_generate" -v`
Expected: FAIL because the endpoint is still synchronous.

**Step 3: Write minimal implementation**

Implement:

- a task-start function that stores request inputs on the session
- immediate state transition to `generating`
- duplicate-run guard for in-progress sessions
- API response shape for accepted async start

Keep the actual LLM workflow out of the request thread.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_rule_tree_session_async.py -k "generate_returns_immediately or duplicate_generate" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/api/rule_tree_session.py backend/app/services/rule_tree_session.py backend/tests/test_rule_tree_session_async.py
git commit -m "feat: start rule tree generation asynchronously"
```

### Task 3: Implement background stage execution and terminal state persistence

**Files:**
- Modify: `backend/app/services/rule_tree_session.py`
- Modify: `backend/app/schemas/rule_tree_session.py`
- Test: `backend/tests/test_rule_tree_session_async.py`

**Step 1: Write the failing test**

Add tests that assert:

- background flow advances through `generating -> reviewing -> saving -> completed`
- generated and reviewed snapshots are persisted
- failure writes `failed` and `last_error`

Use a fake LLM client and invoke the worker function directly in tests.

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_rule_tree_session_async.py -k "worker_success or worker_failure" -v`
Expected: FAIL because there is no background worker/state machine.

**Step 3: Write minimal implementation**

Implement:

- worker function for generate + review flow
- per-stage database commits
- snapshot persistence
- terminal success/failure updates
- persisted diff or enough state for frontend recovery

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_rule_tree_session_async.py -k "worker_success or worker_failure" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/rule_tree_session.py backend/app/schemas/rule_tree_session.py backend/tests/test_rule_tree_session_async.py
git commit -m "feat: persist rule tree async progress and results"
```

### Task 4: Update frontend API/types for polling and restored results

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/ruleTreeSession.ts`
- Test: `frontend/src/pages/RuleTree/index.tsx`

**Step 1: Write the failing test**

If a frontend test harness exists, add a focused test for polling state restoration. Otherwise document the manual verification steps in this task and keep code changes minimal and observable.

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --runInBand`
Expected: FAIL or note that no suitable automated test harness exists for this page yet.

**Step 3: Write minimal implementation**

Implement:

- async-start response typing
- expanded session typing for progress fields, snapshots, and terminal states
- polling helper or reuse existing detail fetch API with timer-driven polling

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --runInBand`
Expected: PASS if tests exist; otherwise capture why only manual verification is available.

**Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/ruleTreeSession.ts
git commit -m "feat: add rule tree async session client types"
```

### Task 5: Add progress UI, refresh recovery, and terminal-state UX

**Files:**
- Modify: `frontend/src/pages/RuleTree/index.tsx`
- Test: `frontend/src/pages/RuleTree/index.tsx`

**Step 1: Write the failing test**

If possible, add component-level coverage for:

- progress area shown during in-progress states
- restored completed result after reload
- failed/interrupted alert with retry action

If UI tests are not practical, define exact manual acceptance steps before coding.

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --runInBand`
Expected: FAIL or confirm test gap.

**Step 3: Write minimal implementation**

Implement:

- stage-based progress display
- auto polling while session is in progress
- restoration from fetched session detail after page reload
- completed state hydration into existing result panels
- failed/interrupted messaging and retry entry point

Use stage labels instead of fake fine-grained percentages.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --runInBand`
Expected: PASS if automated tests exist; otherwise complete manual acceptance checks.

**Step 5: Commit**

```bash
git add frontend/src/pages/RuleTree/index.tsx
git commit -m "feat: show recoverable async progress for rule tree generation"
```

### Task 6: Verify end-to-end behavior and update docs

**Files:**
- Modify: `KNOWLEDGE_BASE.md`
- Modify: `docs/联调启动说明.md`
- Test: `backend/tests/test_rule_tree_session_async.py`

**Step 1: Write the failing test**

Document the end-to-end manual checks first:

- start generate, observe immediate return
- see stage progress
- refresh and recover progress
- complete and recover result
- simulate interruption and observe `interrupted`

**Step 2: Run verification commands**

Run: `cd backend && pytest tests/test_rule_tree_session_async.py -v`
Expected: PASS

Run: `cd frontend && npm run build`
Expected: PASS

**Step 3: Write minimal implementation**

Update docs to describe:

- async generate behavior
- progress stages
- interruption semantics after backend restart

**Step 4: Run full verification**

Run: `cd backend && pytest`
Expected: PASS or a concise list of unrelated failures.

Run: `cd frontend && npm run build`
Expected: PASS

**Step 5: Commit**

```bash
git add KNOWLEDGE_BASE.md docs/联调启动说明.md backend/tests/test_rule_tree_session_async.py
git commit -m "docs: describe async rule tree generation workflow"
```
