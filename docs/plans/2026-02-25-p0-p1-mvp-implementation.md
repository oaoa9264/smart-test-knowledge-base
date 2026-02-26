# P0 + P1 MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a runnable MVP for the test knowledge base covering P0 and P1: rule tree CRUD, test case binding, coverage matrix, AI draft parse, and impact analysis.

**Architecture:** Use a mono-repo with `frontend` (React + TS + Vite + AntD + ReactFlow) and `backend` (FastAPI + SQLAlchemy + PostgreSQL-ready schema). Backend exposes REST APIs for projects, rules, test cases, coverage, AI parse, and impact analysis. Frontend consumes APIs via Axios with Zustand store slices.

**Tech Stack:** React 18, TypeScript, Vite, Ant Design 5, ReactFlow, Zustand, Axios, FastAPI, SQLAlchemy 2.x, Pydantic v2, Uvicorn, Pytest, Docker Compose.

### Task 1: Repository scaffolding

**Files:**
- Create: `frontend/`
- Create: `backend/`
- Create: `docker-compose.yml`
- Create: `README.md`

**Step 1: Create backend and frontend base directories**
Run: `mkdir -p frontend/src backend/app`
Expected: Directories created

**Step 2: Add project manifests**
Create `frontend/package.json` and `backend/requirements.txt`.

**Step 3: Add environment examples**
Create `.env.example` files for backend and frontend API base URL.

### Task 2: Backend domain model + schemas

**Files:**
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/entities.py`
- Create: `backend/app/schemas/*.py`

**Step 1: Write failing tests for model-level behavior helpers**
Test: `backend/tests/test_rule_engine.py`

**Step 2: Implement SQLAlchemy entities**
Add `Project`, `Requirement`, `RuleNode`, `RulePath`, `TestCase`, association tables.

**Step 3: Implement Pydantic schemas**
Add create/update/response DTOs for all P0/P1 APIs.

### Task 3: Backend services (rule engine, coverage, impact, ai parser)

**Files:**
- Create: `backend/app/services/rule_engine.py`
- Create: `backend/app/services/coverage.py`
- Create: `backend/app/services/impact.py`
- Create: `backend/app/services/ai_parser.py`
- Test: `backend/tests/test_coverage_and_impact.py`

**Step 1: Write failing tests for path derivation, coverage summary, impact update marking**
Run: `pytest backend/tests -q`
Expected: FAIL for missing services.

**Step 2: Implement minimal logic to satisfy tests**
Implement DFS path generation, coverage aggregation, and impact marking.

**Step 3: Re-run tests**
Run: `pytest backend/tests -q`
Expected: PASS.

### Task 4: Backend API layer

**Files:**
- Create: `backend/app/api/projects.py`
- Create: `backend/app/api/rules.py`
- Create: `backend/app/api/testcases.py`
- Create: `backend/app/api/coverage.py`
- Create: `backend/app/api/ai_parse.py`
- Create: `backend/app/main.py`

**Step 1: Write API tests for key endpoints**
Test: `backend/tests/test_api_smoke.py`

**Step 2: Implement endpoints with DB session wiring**
Expose CRUD + bind + coverage + ai draft + impact report.

**Step 3: Run tests**
Run: `pytest backend/tests -q`
Expected: PASS.

### Task 5: Frontend app shell and P0 pages

**Files:**
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/pages/ProjectList/index.tsx`
- Create: `frontend/src/pages/RuleTree/index.tsx`
- Create: `frontend/src/pages/TestCases/index.tsx`
- Create: `frontend/src/pages/Coverage/index.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/stores/*.ts`

**Step 1: Build global layout and routes**
Add sidebar + top bar + route pages.

**Step 2: Implement RuleTree editor page**
ReactFlow graph, node edit drawer, save/load from API.

**Step 3: Implement TestCases binding page**
Case CRUD + node/path binding + risk level fields.

**Step 4: Implement Coverage matrix page**
Color-coded coverage table with risk sorting.

### Task 6: P1 features and integration

**Files:**
- Modify: `frontend/src/pages/RuleTree/index.tsx`
- Modify: `backend/app/api/ai_parse.py`
- Modify: `backend/app/api/rules.py`
- Modify: `backend/app/services/impact.py`

**Step 1: AI parse draft workflow**
Paste requirement text -> call parse endpoint -> preview generated nodes -> confirm import.

**Step 2: Impact analysis workflow**
After node update/delete, call impact endpoint and display affected cases.

**Step 3: Validate behavior manually**
Run backend and frontend locally and verify page flows.

### Task 7: Containerization and documentation

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Modify: `README.md`

**Step 1: Add compose services**
Define `frontend`, `backend`, `postgres` with env configuration.

**Step 2: Document startup and API overview**
Add quickstart, scripts, and P0/P1 feature map.

**Step 3: Final verification**
Run: `pytest backend/tests -q`
Expected: PASS.
