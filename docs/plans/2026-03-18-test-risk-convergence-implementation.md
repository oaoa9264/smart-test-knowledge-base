# Risk Convergence Async Tasks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert review, pre-dev, and pre-release analysis in the risk panel into persisted async tasks with recoverable progress and retained last-success results.

**Architecture:** Add a dedicated `risk_analysis_tasks` persistence model instead of reusing rule-tree sessions. The backend will expose stage-based async task APIs, run the existing synchronous analyzers in background workers, and persist result payloads plus optional snapshot references. The frontend `RiskPanel` will switch from direct long-running requests to task start, status restore, stage polling, and result hydration.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React, TypeScript, Axios, Ant Design, pytest, Vite

---

### Task 1: Add the persisted async task model and startup recovery

**Files:**
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/core/schema_migrations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_smoke.py`
- Test: `backend/tests/test_risk_analysis_async.py`

**Step 1: Write the failing test**

Add tests that assert:

- the `risk_analysis_tasks` table exists after app startup
- required columns exist: `requirement_id`, `stage`, `status`, `progress_message`, `progress_percent`, `last_error`, `snapshot_id`, `result_json`, `current_task_started_at`, `current_task_finished_at`
- startup recovery changes `queued` and `running` tasks to `interrupted`

```python
def test_risk_analysis_task_table_exists():
    inspector = inspect(engine)
    assert "risk_analysis_tasks" in inspector.get_table_names()


def test_recover_interrupted_risk_analysis_tasks_marks_in_progress_rows():
    task = RiskAnalysisTask(stage=AnalysisStage.review, status="running", requirement_id=requirement_id)
    db.add(task)
    db.commit()

    changed = recover_interrupted_risk_analysis_tasks()

    db.refresh(task)
    assert changed == 1
    assert task.status == "interrupted"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api_smoke.py tests/test_risk_analysis_async.py -k "risk_analysis_task or interrupted_risk_analysis" -v`

Expected: FAIL because the table, model, and startup recovery do not exist yet.

**Step 3: Write minimal implementation**

Implement:

- a new `RiskAnalysisTask` SQLAlchemy model
- additive schema migration helper for `risk_analysis_tasks`
- app startup recovery function for `queued/running -> interrupted`
- table creation bootstrap through the existing `Base.metadata.create_all(...)`

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_api_smoke.py tests/test_risk_analysis_async.py -k "risk_analysis_task or interrupted_risk_analysis" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/models/entities.py backend/app/core/schema_migrations.py backend/app/main.py backend/tests/test_api_smoke.py backend/tests/test_risk_analysis_async.py
git commit -m "feat: persist async risk analysis tasks"
```

### Task 2: Add backend schemas and task query APIs

**Files:**
- Create: `backend/app/schemas/risk_analysis_task.py`
- Modify: `backend/app/schemas/__init__.py`
- Create: `backend/app/api/risk_analysis_tasks.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_risk_analysis_async.py`

**Step 1: Write the failing test**

Add tests that assert:

- `GET /api/requirements/{id}/analysis-tasks/{stage}` returns `null` when no task exists
- `GET /api/requirements/{id}/analysis-tasks` returns a stage-keyed summary payload

```python
def test_get_single_stage_task_returns_null_when_missing(client, requirement_id):
    resp = client.get(f"/api/requirements/{requirement_id}/analysis-tasks/review")
    assert resp.status_code == 200
    assert resp.json() is None


def test_get_task_summary_returns_stage_mapping(client, requirement_id):
    resp = client.get(f"/api/requirements/{requirement_id}/analysis-tasks")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"review", "pre_dev", "pre_release"}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_risk_analysis_async.py -k "single_stage_task or task_summary" -v`

Expected: FAIL because the schemas and APIs do not exist.

**Step 3: Write minimal implementation**

Implement:

- Pydantic read models for task records and accepted-start responses
- `GET` single-stage latest task endpoint
- `GET` per-requirement stage summary endpoint
- router registration in `backend/app/main.py`

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_risk_analysis_async.py -k "single_stage_task or task_summary" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/schemas/risk_analysis_task.py backend/app/schemas/__init__.py backend/app/api/risk_analysis_tasks.py backend/app/main.py backend/tests/test_risk_analysis_async.py
git commit -m "feat: expose async risk analysis task status APIs"
```

### Task 3: Start review, pre-dev, and pre-release as async background tasks

**Files:**
- Create: `backend/app/services/risk_analysis_task_service.py`
- Modify: `backend/app/api/risk_analysis_tasks.py`
- Test: `backend/tests/test_risk_analysis_async.py`

**Step 1: Write the failing test**

Add tests that assert:

- `POST /api/requirements/{id}/analysis-tasks/review` returns immediately with `{ accepted: true, task }`
- same-stage duplicate start while `queued/running` returns `409`
- `POST` on `pre_dev` and `pre_release` accepts valid stages

```python
def test_start_review_task_returns_accepted(client, requirement_id):
    resp = client.post(f"/api/requirements/{requirement_id}/analysis-tasks/review")
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True
    assert resp.json()["task"]["stage"] == "review"


def test_duplicate_stage_start_returns_conflict(client, seeded_running_review_task):
    resp = client.post(f"/api/requirements/{seeded_running_review_task.requirement_id}/analysis-tasks/review")
    assert resp.status_code == 409
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_risk_analysis_async.py -k "start_review_task or duplicate_stage_start" -v`

Expected: FAIL because the task starter service does not exist.

**Step 3: Write minimal implementation**

Implement:

- service helpers to create-or-reuse one task row per requirement/stage
- conflict protection for `queued/running`
- background worker launcher
- API endpoints in `backend/app/api/risk_analysis_tasks.py` that expose accepted async starts
- explicit stage routing in `backend/app/services/risk_analysis_task_service.py` to:
  - `backend/app/services/effective_requirement_service.py` -> `generate_review_snapshot`
  - `backend/app/services/predev_analyzer.py` -> `analyze_for_predev`
  - `backend/app/services/prerelease_auditor.py` -> `audit_for_prerelease`

Keep the existing synchronous endpoints in `backend/app/api/effective_requirements.py` unchanged for now. The safer transition is to switch the frontend in Task 6 first, then remove deprecated synchronous callers in Task 7.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_risk_analysis_async.py -k "start_review_task or duplicate_stage_start" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/risk_analysis_task_service.py backend/app/api/risk_analysis_tasks.py backend/tests/test_risk_analysis_async.py
git commit -m "feat: launch risk analysis stages asynchronously"
```

### Task 4: Persist worker results, optional snapshot references, and failure states

**Files:**
- Modify: `backend/app/services/risk_analysis_task_service.py`
- Modify: `backend/app/schemas/risk_analysis_task.py`
- Test: `backend/tests/test_risk_analysis_async.py`

**Step 1: Write the failing test**

Add tests that invoke the worker function directly with fake analyzer implementations and assert:

- `review` writes `snapshot_id`, `result_json`, and `completed`
- `pre_dev` writes `conflicts` and `matched_evidence`
- `pre_release` writes audit result without requiring `snapshot_id`
- analyzer exception writes `failed` plus `last_error`

```python
def test_review_worker_persists_snapshot_and_result_json(db_session, review_task, monkeypatch):
    monkeypatch.setattr(service, "generate_review_snapshot", lambda **_: fake_review_result)
    run_risk_analysis_task(task_id=review_task.id)
    db_session.refresh(review_task)
    assert review_task.status == "completed"
    assert review_task.snapshot_id is not None


def test_worker_failure_sets_failed_state(db_session, review_task, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "generate_review_snapshot", _boom)
    run_risk_analysis_task(task_id=review_task.id)
    db_session.refresh(review_task)
    assert review_task.status == "failed"
    assert "boom" in review_task.last_error
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_risk_analysis_async.py -k "worker_persists or worker_failure" -v`

Expected: FAIL because result persistence and terminal state handling are incomplete.

**Step 3: Write minimal implementation**

Implement:

- stage routing to:
  - `backend/app/services/effective_requirement_service.py` -> `generate_review_snapshot`
  - `backend/app/services/predev_analyzer.py` -> `analyze_for_predev`
  - `backend/app/services/prerelease_auditor.py` -> `audit_for_prerelease`
- per-stage `result_json` serializers with stable schemas
- optional `snapshot_id` persistence
- `completed`, `failed`, and timing updates
- user-readable progress messages and percentages

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_risk_analysis_async.py -k "worker_persists or worker_failure" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/risk_analysis_task_service.py backend/app/schemas/risk_analysis_task.py backend/tests/test_risk_analysis_async.py
git commit -m "feat: persist async risk analysis results and failures"
```

### Task 5: Add frontend task types and APIs for start, summary fetch, and polling

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/effectiveRequirements.ts`
- Create: `frontend/src/api/riskAnalysisTasks.ts`
- Test: `N/A — build check only`

**Step 1: Write the failing test**

There is no frontend automated test harness in `frontend/package.json`. Document the manual acceptance checks for this task before coding:

- page can load per-stage task summaries
- stage start API returns accepted task payloads
- in-progress task shape can be parsed from API types without TypeScript errors

**Step 2: Run verification to confirm the current gap**

Run: `cd frontend && npm run build`

Expected: PASS now; this command becomes the regression check after type/API changes because no UI test runner exists yet.

**Step 3: Write minimal implementation**

Implement:

- shared task types, stage status unions, and accepted-start response types
- API helpers for:
  - `startRiskAnalysisTask(requirementId, stage)`
  - `fetchRiskAnalysisTask(requirementId, stage)`
  - `fetchRiskAnalysisTaskSummary(requirementId)`
- preserve existing snapshot/result response types for hydration of last-success results

**Step 4: Run verification after the change**

Run: `cd frontend && npm run build`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/effectiveRequirements.ts frontend/src/api/riskAnalysisTasks.ts
git commit -m "feat: add async risk analysis client types"
```

### Task 6: Refactor `RiskPanel` to use persisted tasks, retained results, and stage polling

**Files:**
- Modify: `frontend/src/pages/RuleTree/RiskPanel.tsx`
- Test: `frontend/src/pages/RuleTree/RiskPanel.tsx`

**Step 1: Write the failing test**

Document the manual UI acceptance steps before coding:

1. Click each of the three stage buttons and confirm the UI returns immediately.
2. Confirm the clicked stage button becomes disabled optimistically.
3. Confirm the panel still shows the previous successful result while a new task is running.
4. Refresh the page mid-task and confirm the running state recovers.
5. Restart the backend mid-task and confirm the panel shows `interrupted`.

**Step 2: Run verification against the current UI**

Run: `cd frontend && npm run build`

Expected: PASS before refactor; current UI still uses synchronous requests and lacks task state recovery.

**Step 3: Write minimal implementation**

Implement in `RiskPanel`:

- separate state for `taskStatus` and `lastSuccessResult`
- summary fetch on initial load and requirement change
- single-stage polling with immediate refresh when the user focuses a stage
- optimistic disable for the clicked stage button
- per-stage status bars under the buttons or at the top of each stage result area
- terminal-state handling:
  - keep previous success result on `failed/interrupted`
  - replace previous result only on `completed`
- refresh risk list and requirement input list after successful completion

**Step 4: Run verification after the change**

Run: `cd frontend && npm run build`

Expected: PASS

Then manually verify:

- start `review`, `pre_dev`, and `pre_release`
- refresh while running
- rerun a completed stage and confirm old result remains visible until replacement

**Step 5: Commit**

```bash
git add frontend/src/pages/RuleTree/RiskPanel.tsx
git commit -m "feat: make risk convergence stages async and recoverable"
```

### Task 7: Update smoke coverage and local runbook

**Files:**
- Modify: `backend/tests/test_api_smoke.py`
- Modify: `frontend/src/api/effectiveRequirements.ts`
- Modify: `docs/联调启动说明.md`
- Modify: `docs/plans/2026-03-18-test-risk-convergence-design.md`
- Test: `backend/tests/test_risk_analysis_async.py`

**Step 1: Write the failing test**

Add a smoke test that asserts the old synchronous `review` path is no longer the frontend integration path, and the async task endpoints behave as expected for a basic requirement.

```python
def test_review_task_flow_smoke(client, requirement_id):
    start = client.post(f"/api/requirements/{requirement_id}/analysis-tasks/review")
    assert start.status_code == 200
    detail = client.get(f"/api/requirements/{requirement_id}/analysis-tasks/review")
    assert detail.status_code == 200
    assert detail.json()["status"] in {"queued", "running", "completed"}
```

This smoke test intentionally does not require immediate `completed`. It only verifies that the async start path is alive and the follow-up read returns a non-error task state.

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api_smoke.py tests/test_risk_analysis_async.py -k "review_task_flow_smoke" -v`

Expected: FAIL because the smoke path is not wired yet.

**Step 3: Write minimal implementation**

Update:

- smoke tests to reflect the new integration path
- remove deprecated synchronous frontend callers from `frontend/src/api/effectiveRequirements.ts` once `RiskPanel` has fully switched to `frontend/src/api/riskAnalysisTasks.ts`
- `docs/联调启动说明.md` with async stage-task flow, status recovery, and interruption semantics
- the design doc if any implementation-specific clarifications emerged

**Step 4: Run full verification**

Run: `cd backend && pytest tests/test_risk_analysis_async.py tests/test_api_smoke.py -v`

Expected: PASS

Run: `cd frontend && npm run build`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_api_smoke.py backend/tests/test_risk_analysis_async.py frontend/src/api/effectiveRequirements.ts docs/联调启动说明.md docs/plans/2026-03-18-test-risk-convergence-design.md
git commit -m "docs: describe async risk convergence task workflow"
```
