# Requirement Freshness And Normalized PRD Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add stale-snapshot detection plus frontend warnings for changed requirements, and add a normalized requirement document preview/export flow that can generate Markdown from the current requirement inputs.

**Architecture:** Extend `EffectiveRequirementSnapshot` with a deterministic `basis_hash` while keeping `based_on_input_ids` for traceability. Reuse one shared hash function in backend services, expose stale status through snapshot APIs, block `pre_dev` and `pre_release` when the selected snapshot is stale, and add a separate normalized document service/API/UI path that can optionally reuse a fresh snapshot but still works from live requirement inputs when no fresh snapshot exists.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Pydantic, React, TypeScript, Axios, Ant Design, pytest, Vite, react-markdown

---

### Task 1: Add snapshot basis hashing and lock down freshness behavior with backend tests

**Files:**
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/core/schema_migrations.py`
- Modify: `backend/app/services/effective_requirement_service.py`
- Modify: `backend/app/schemas/risk_convergence.py`
- Create: `backend/tests/test_effective_requirement_service.py`

**Step 1: Write the failing tests**

Add tests that lock down the new freshness model:

- `EffectiveRequirementSnapshot` has a persisted `basis_hash`
- `compute_basis_hash()` is deterministic for the same requirement/input set
- changing `Requirement.raw_text` changes the computed hash
- changing existing `RequirementInput.content` changes the computed hash even when input IDs stay the same
- new review snapshots persist both `based_on_input_ids` and `basis_hash`

Example test shape:

```python
def test_compute_basis_hash_changes_when_raw_requirement_changes(db_session):
    requirement = _seed_requirement(raw_text="old")
    inputs = _seed_inputs(requirement.id, ["A"])
    first = compute_basis_hash(requirement, inputs)

    requirement.raw_text = "new"
    db_session.flush()

    second = compute_basis_hash(requirement, inputs)
    assert first != second


def test_generate_review_snapshot_persists_basis_hash(db_session):
    result = generate_review_snapshot(db=db_session, requirement_id=requirement_id)
    snapshot = result["snapshot"]
    assert snapshot.basis_hash
    assert snapshot.based_on_input_ids is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/pytest tests/test_effective_requirement_service.py -k "basis_hash or freshness" -v`

Expected: FAIL because the model, schema migration, and hash helper do not exist yet.

**Step 3: Write minimal implementation**

Implement:

- `basis_hash` column on `effective_requirement_snapshots`
- additive schema migration helper for the new column
- `compute_basis_hash(requirement, inputs)` in `backend/app/services/effective_requirement_service.py`
- a small helper such as `is_snapshot_stale(...)`
- schema exposure through `EffectiveSnapshotRead`
- `generate_review_snapshot()` persistence of both `based_on_input_ids` and `basis_hash`

Keep the hash contract centralized in one place; do not duplicate serialization logic across APIs.

**Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/pytest tests/test_effective_requirement_service.py -k "basis_hash or freshness" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/models/entities.py backend/app/core/schema_migrations.py backend/app/services/effective_requirement_service.py backend/app/schemas/risk_convergence.py backend/tests/test_effective_requirement_service.py
git commit -m "feat: add effective snapshot basis hash"
```

### Task 2: Enforce stale-snapshot rules in pre-dev and pre-release APIs

**Files:**
- Modify: `backend/app/services/predev_analyzer.py`
- Modify: `backend/app/services/prerelease_auditor.py`
- Modify: `backend/app/api/effective_requirements.py`
- Modify: `backend/app/services/effective_requirement_service.py`
- Test: `backend/tests/test_risk_service.py`
- Modify: `backend/tests/test_effective_requirement_service.py`

**Step 1: Write the failing tests**

Add tests that assert:

- `pre_dev` rejects when the selected base snapshot is stale
- `pre_release` rejects when the audit-selected snapshot is stale
- response payloads distinguish `NO_SNAPSHOT` from `STALE_SNAPSHOT`

Example:

```python
def test_predev_rejects_stale_snapshot(client, requirement_id, stale_review_snapshot):
    resp = client.post("/api/ai/risks/predev-analyze", json={"requirement_id": requirement_id})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "STALE_SNAPSHOT"


def test_prerelease_requires_snapshot_when_missing(client, requirement_id):
    resp = client.post("/api/ai/risks/prerelease-audit", json={"requirement_id": requirement_id})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "NO_SNAPSHOT"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/pytest tests/test_risk_service.py tests/test_effective_requirement_service.py -k "stale_snapshot or no_snapshot" -v`

Expected: FAIL because stale detection is not enforced yet.

**Step 3: Write minimal implementation**

Implement:

- explicit exceptions such as `NoSnapshotError` and `StaleSnapshotError`
- stale checks in `analyze_for_predev()`
- stale checks in `audit_for_prerelease()`
- structured error details in `backend/app/api/effective_requirements.py`
- `pre_dev` validation against the actual base snapshot it uses
- `pre_release` validation against the actual snapshot selected by `_get_best_snapshot()`

API handling rule:

- catch `NoSnapshotError` and return `detail={"code": "NO_SNAPSHOT", "message": ...}`
- catch `StaleSnapshotError` and return `detail={"code": "STALE_SNAPSHOT", "message": ...}`
- keep the existing generic `ValueError -> detail=str(exc)` path as the compatibility fallback for unrelated service errors

Do not special-case only review snapshots; the selected `pre_dev` snapshot must also be validated.

**Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/pytest tests/test_risk_service.py tests/test_effective_requirement_service.py -k "stale_snapshot or no_snapshot" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/predev_analyzer.py backend/app/services/prerelease_auditor.py backend/app/api/effective_requirements.py backend/app/services/effective_requirement_service.py backend/tests/test_risk_service.py backend/tests/test_effective_requirement_service.py
git commit -m "feat: block stale effective snapshots in analysis stages"
```

### Task 3: Surface snapshot staleness in RiskPanel

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/effectiveRequirements.ts`
- Modify: `frontend/src/pages/RuleTree/RiskPanel.tsx`
- Test: `frontend/package.json`

**Step 1: Add the UI-facing expectations**

Document the exact UI behaviors before editing:

- the latest snapshot section shows a warning when `latestSnapshot.is_stale` is `true`
- failed `pre_dev`/`pre_release` requests show different messages for `NO_SNAPSHOT` and `STALE_SNAPSHOT`
- the existing latest snapshot card still renders even when stale

**Step 2: Run the baseline build**

Run: `cd frontend && npm run build`

Expected: PASS before UI changes.

**Step 3: Write minimal implementation**

Implement:

- new snapshot freshness fields in `frontend/src/types/index.ts`
- API typing updates if needed
- warning alert in `frontend/src/pages/RuleTree/RiskPanel.tsx`
- request error mapping so stale and missing snapshot messages are distinct

Do not redesign the panel; add only the freshness indicators and targeted error messaging.

**Step 4: Run the build to verify it passes**

Run: `cd frontend && npm run build`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/effectiveRequirements.ts frontend/src/pages/RuleTree/RiskPanel.tsx
git commit -m "feat: warn when effective requirement snapshot is stale"
```

### Task 4: Add normalized requirement document backend service and preview/export APIs

**Files:**
- Create: `backend/app/services/normalized_requirement_doc_service.py`
- Create: `backend/app/api/normalized_requirement_docs.py`
- Create: `backend/app/schemas/normalized_requirement_doc.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/effective_requirement_service.py`
- Test: `backend/tests/test_normalized_requirement_doc.py`
- Test: `backend/tests/test_api_smoke.py`

**Step 1: Write the failing tests**

Add coverage for:

- preview works without any snapshot
- preview reuses a fresh snapshot when available
- stale snapshot does not block preview, but marks `uses_fresh_snapshot=False` and `snapshot_stale=True`
- no snapshot path still returns preview content without derivation filtering
- no snapshot path writes the canned pending note about missing snapshot reference
- generated markdown only contains the approved sections
- inferred / missing / contradicted content is pushed into `## 5. 待确认事项`
- export endpoint returns markdown download content

Example:

```python
def test_preview_moves_inferred_content_to_pending_items(db_session):
    result = build_normalized_requirement_doc(db=db_session, requirement_id=requirement_id)
    assert "## 5. 待确认事项" in result.markdown
    assert "推断" not in result.markdown.split("## 5. 待确认事项")[0]


def test_export_markdown_endpoint_returns_markdown(client, requirement_id):
    resp = client.get(f"/api/requirements/{requirement_id}/normalized-doc/export.md")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/pytest tests/test_normalized_requirement_doc.py tests/test_api_smoke.py -k "normalized_requirement_doc or export_markdown" -v`

Expected: FAIL because the service, schema, and APIs do not exist.

**Step 3: Write minimal implementation**

Implement:

- a dedicated normalized-doc service that reads the current requirement plus all inputs
- reuse of `compute_basis_hash()` and latest-snapshot freshness checks
- no-snapshot fallback that builds the first four sections directly from current input text without trying to infer `derivation`
- a canned pending note such as `暂无快照参考，当前文档基于实时输入整理；如需更严格区分已明确与待确认内容，建议先执行评审分析后重新导出。`
- markdown builder with exactly these sections:
  - `# 需求标题`
  - `## 1. 需求背景与目标`
  - `## 2. 主流程`
  - `## 3. 异常与边界场景`
  - `## 4. 约束与兼容性`
  - `## 5. 待确认事项`
- preview API
- use `GET /api/requirements/{id}/normalized-doc/preview` because preview is read-only and has no request body in this design
- markdown download API
- router registration in `backend/app/main.py`

Snapshot-aware rule:

- when a fresh snapshot exists, the first four sections may use only `derivation=explicit` content
- `inferred / missing / contradicted` content goes only into `## 5. 待确认事项`

No-snapshot rule:

- preview/export must still work
- the first four sections are built from clearly stated live input text only
- no derivation filtering is attempted
- `## 5. 待确认事项` must include the canned “no snapshot reference” note

**Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/pytest tests/test_normalized_requirement_doc.py tests/test_api_smoke.py -k "normalized_requirement_doc or export_markdown" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/normalized_requirement_doc_service.py backend/app/api/normalized_requirement_docs.py backend/app/schemas/normalized_requirement_doc.py backend/app/main.py backend/app/services/effective_requirement_service.py backend/tests/test_normalized_requirement_doc.py backend/tests/test_api_smoke.py
git commit -m "feat: add normalized requirement doc preview and export"
```

### Task 5: Add frontend preview and Markdown download for normalized requirement documents

**Files:**
- Create: `frontend/src/api/normalizedRequirementDoc.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/ProjectList/index.tsx`
- Modify: `frontend/src/pages/RuleTree/RiskPanel.tsx`
- Verify: `frontend/package.json`

**Step 1: Define the UX details before implementation**

Lock down the interaction:

- add a `导出规范化需求` entry point near requirement detail / risk analysis context
- clicking it opens a `Modal` or `Drawer`
- the preview uses backend markdown directly
- header shows whether a fresh snapshot was reused
- user can download Markdown from the preview surface

**Step 2: Run the baseline build**

Run: `cd frontend && npm run build`

Expected: PASS before adding the new UI.

**Step 3: Write minimal implementation**

Implement:

- new frontend API module for preview and export
- TypeScript types for preview response
- preview `Modal` or `Drawer` using `react-markdown`
- download action using `Blob` and a generated filename
- small explanatory text:
  - `已复用最新快照`
  - or `当前快照已过期，本次文档基于实时输入整理`

Dependency note:

- `react-markdown` is already present in `frontend/package.json`
- this task should reuse the existing dependency and does not require a new `npm install`

Prefer adding the launch entry to the requirement detail path so users can export without opening multiple pages.

**Step 4: Run the build to verify it passes**

Run: `cd frontend && npm run build`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/api/normalizedRequirementDoc.ts frontend/src/types/index.ts frontend/src/pages/ProjectList/index.tsx frontend/src/pages/RuleTree/RiskPanel.tsx
git commit -m "feat: preview and export normalized requirement markdown"
```

### Task 6: Run end-to-end verification and update docs if implementation details changed

**Files:**
- Modify: `docs/plans/2026-03-19-requirement-freshness-and-normalized-prd-design.md`
- Modify: `docs/plans/2026-03-19-requirement-freshness-and-normalized-prd.md`
- Test: `backend/tests/test_risk_service.py`
- Test: `backend/tests/test_normalized_requirement_doc.py`
- Test: `backend/tests/test_api_smoke.py`
- Test: `frontend/package.json`

**Step 1: Run backend verification**

Run: `cd backend && ./.venv/bin/pytest tests/test_risk_service.py tests/test_normalized_requirement_doc.py tests/test_api_smoke.py -v`

Expected: PASS

**Step 2: Run frontend verification**

Run: `cd frontend && npm run build`

Expected: PASS

**Step 3: Manual verification**

Verify locally:

- update `raw_text`, open risk panel, confirm stale warning appears
- add `pm_addendum` or `test_clarification`, confirm stale warning appears without changing input IDs
- try `pre_dev` with stale snapshot, confirm API and UI show stale-specific error
- open normalized requirement preview with no snapshot, confirm preview still works
- open preview with stale snapshot, confirm it says it used live input
- download Markdown and confirm only the approved 5 sections exist

**Step 4: Sync docs if implementation diverged**

Update the design doc and plan doc if file names, API paths, or error payload shapes changed during implementation.

**Step 5: Commit**

```bash
git add docs/plans/2026-03-19-requirement-freshness-and-normalized-prd-design.md docs/plans/2026-03-19-requirement-freshness-and-normalized-prd.md
git commit -m "docs: finalize requirement freshness and normalized prd docs"
```
