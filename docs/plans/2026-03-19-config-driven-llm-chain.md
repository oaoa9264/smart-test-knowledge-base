# Config-Driven LLM Chain Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the hard-coded `OpenAI -> Zhipu` fallback with a configuration-driven provider chain that can support frequent model/provider changes, and standardize all LLM-backed features to return empty results plus unified failure metadata instead of falling back to local/mock logic during normal `llm` mode.

**Architecture:** Keep the existing layered design (`BaseLLMClient` -> provider clients -> `FallbackLLMClient` -> `LLMClient` facade), but move provider assembly from hard-coded env keys to a provider registry plus `LLM_PROVIDER_CHAIN`. Standardize all LLM-consuming services on a shared failure contract: provider chain success returns normal data, provider chain exhaustion returns service-specific empty results plus `llm_status=failed`, and explicit mock mode remains available only when the environment is intentionally set to `mock`.

**Tech Stack:** Python, FastAPI, Pydantic, httpx SSE, React, TypeScript, pytest

---

### Task 1: Lock Down Existing LLM Chain Behavior With Tests

**Files:**
- Modify: `backend/tests/test_llm_client.py`
- Modify: `backend/tests/test_fallback_llm.py`
- Test: `backend/tests/test_llm_client.py`
- Test: `backend/tests/test_fallback_llm.py`

**Step 1: Write the regression tests**

Add tests that lock down the current behavior so the refactor does not accidentally break it before the config-driven chain lands:

```python
def test_llm_client_builds_chain_openai_first_then_zhipu(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-key")
    providers = [item.provider_name for item in _FakeFallback.last_instance.clients]
    assert providers == ["openai", "zhipu"]


def test_fallback_raises_last_error_when_all_providers_fail():
    main = _FakeProvider("main", json_error=RuntimeError("main failed"))
    backup = _FakeProvider("backup", json_error=RuntimeError("backup failed"))
    client = FallbackLLMClient([main, backup])

    with pytest.raises(RuntimeError, match="backup failed"):
        client.chat_with_json(system_prompt="system", user_prompt="user")
```

**Step 2: Run tests to verify the baseline passes**

Run: `cd backend && ./.venv/bin/pytest tests/test_llm_client.py tests/test_fallback_llm.py -v`
Expected: PASS against the current implementation.

**Step 3: Write minimal implementation**

Only adjust tests or test helpers needed to describe the current baseline precisely. Do not start the config-driven refactor in this task.

**Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/pytest tests/test_llm_client.py tests/test_fallback_llm.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_llm_client.py backend/tests/test_fallback_llm.py
git commit -m "test: lock down current llm chain baseline"
```

### Task 2: Refactor Provider Clients To Accept Config Objects

**Files:**
- Modify: `backend/app/services/openai_client.py`
- Modify: `backend/app/services/zhipu_client.py`
- Modify: `backend/app/services/base_llm_client.py`
- Test: `backend/tests/test_openai_client.py`
- Create: `backend/tests/test_zhipu_client.py`
- Test: `backend/tests/test_base_llm_client.py`

**Step 1: Write the failing tests**

Add tests that instantiate provider clients with explicit constructor arguments instead of relying on global env:

```python
def test_openai_client_uses_explicit_constructor_config(monkeypatch):
    client = OpenAIClient(
        provider_name="main",
        api_key="key",
        base_url="https://example.com/v1",
        text_model="gpt-5.4",
        vision_model="gpt-5.4",
        timeout=60,
        connect_timeout=10,
        max_retries=2,
        max_tokens=6000,
        temperature=0.3,
        seed=42,
    )
    assert client.provider_name == "main"


def test_zhipu_client_uses_explicit_constructor_config():
    client = ZhipuClient(
        provider_name="zhipu",
        api_key="key",
        api_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        text_model="glm-4.7",
        vision_model="glm-4.7",
        timeout=60,
        connect_timeout=10,
        max_retries=2,
        max_tokens=6000,
        temperature=0.3,
        seed=42,
        thinking_type="disabled",
    )
    assert client.provider_name == "zhipu"
    assert client.thinking_type == "disabled"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/pytest tests/test_openai_client.py tests/test_zhipu_client.py tests/test_base_llm_client.py -v`
Expected: FAIL because provider constructors currently read directly from env.

**Step 3: Write minimal implementation**

Implement constructor-based configuration:

- `BaseLLMClient` keeps shared runtime fields only.
- `OpenAIClient` accepts explicit config args and continues to use the existing OpenAI SDK streaming path.
- `ZhipuClient` accepts explicit config args and optional provider-specific extras such as `thinking_type`.
- Remove duplicated `_read_seed_from_env()` helpers from provider clients; env parsing belongs in the factory/facade layer.
- Provider-specific extras are read by the factory using explicit env keys. For Zhipu, use `LLM_PROVIDER_<ALIAS>_THINKING_TYPE` and pass it through as a constructor argument.

**Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/pytest tests/test_openai_client.py tests/test_zhipu_client.py tests/test_base_llm_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/base_llm_client.py backend/app/services/openai_client.py backend/app/services/zhipu_client.py backend/tests/test_openai_client.py backend/tests/test_zhipu_client.py backend/tests/test_base_llm_client.py
git commit -m "refactor: parameterize llm provider clients"
```

### Task 3: Implement Provider Registry, Config-Driven Chain, And Exhaustion Error

**Files:**
- Modify: `backend/app/services/llm_client.py`
- Modify: `backend/app/services/fallback_llm_client.py`
- Create: `backend/app/services/llm_provider_factory.py`
- Test: `backend/tests/test_llm_client.py`
- Test: `backend/tests/test_fallback_llm.py`

**Step 1: Write the failing tests**

Add coverage for:

- `LLM_PROVIDER_CHAIN` order is respected
- legacy env fallback still works when `LLM_PROVIDER_CHAIN` is unset
- unknown provider type fails fast
- providers with missing required config are skipped or rejected according to design
- single-provider chain works
- `get_last_provider()` returns the configured provider alias
- chain exhaustion raises `AllLLMProvidersFailedError`

```python
def test_llm_client_uses_provider_alias_for_last_provider(monkeypatch):
    ...
    assert client.get_last_provider("chat_with_json") == "backup"


def test_llm_client_falls_back_to_legacy_env_when_chain_unset(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_CHAIN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-key")
    ...
    assert providers == ["openai", "zhipu"]
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/pytest tests/test_llm_client.py tests/test_fallback_llm.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Implement:

- `AllLLMProvidersFailedError(Exception)`
- `LLMProviderFactory.build(alias: str) -> BaseLLMClient`
- env contract:

```env
LLM_PROVIDER_CHAIN=main,backup,zhipu
LLM_PROVIDER_MAIN_TYPE=openai_compatible
LLM_PROVIDER_MAIN_API_KEY=...
LLM_PROVIDER_MAIN_BASE_URL=...
LLM_PROVIDER_MAIN_TEXT_MODEL=gpt-5.4
LLM_PROVIDER_MAIN_VISION_MODEL=gpt-5.4
```

- shared optional env keys:
  - `LLM_REQUEST_TIMEOUT`
  - `LLM_CONNECT_TIMEOUT`
  - `LLM_MAX_RETRIES`
  - `LLM_MAX_TOKENS`
  - `LLM_TEMPERATURE`
  - `LLM_SEED`
- optional per-provider overrides such as:
  - `LLM_PROVIDER_MAIN_REQUEST_TIMEOUT`
  - `LLM_PROVIDER_MAIN_CONNECT_TIMEOUT`
  - `LLM_PROVIDER_MAIN_MAX_RETRIES`

Rules:

- In normal `llm` mode, `LLM_PROVIDER_CHAIN` is the source of truth.
- `provider_name` stored on each client is the alias from the chain (`main`, `backup`, `zhipu`), not the generic type name.
- When every provider fails, raise `AllLLMProvidersFailedError(failed_providers, last_error, method_name)`.
- If `LLM_PROVIDER_CHAIN` is unset, fall back to the current legacy env behavior (`OPENAI_API_KEY` / `ZHIPU_API_KEY`) and emit a deprecation warning in logs so existing deployments do not break silently.

**Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/pytest tests/test_llm_client.py tests/test_fallback_llm.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/llm_client.py backend/app/services/fallback_llm_client.py backend/app/services/llm_provider_factory.py backend/tests/test_llm_client.py backend/tests/test_fallback_llm.py
git commit -m "feat: add config-driven llm provider chain"
```

### Task 4: Define Shared Failure Metadata And Empty Result Helpers

**Files:**
- Create: `backend/app/services/llm_result_helpers.py`
- Create: `backend/tests/test_llm_result_helpers.py`

**Step 1: Write the helper-only failing tests**

Add unit tests for helper behavior only:

```python
def test_build_llm_success_meta_sets_success_status():
    result = build_llm_success_meta("main")
    assert result == {
        "llm_status": "success",
        "llm_provider": "main",
        "llm_message": None,
    }


def test_build_llm_failure_meta_uses_default_message():
    result = build_llm_failure_meta()
    assert result["llm_status"] == "failed"
    assert result["llm_provider"] is None
    assert "所有模型调用失败" in result["llm_message"]
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/pytest tests/test_llm_result_helpers.py -v`
Expected: FAIL because the helper module does not exist yet.

**Step 3: Write minimal implementation**

Create shared helpers:

- `build_llm_success_meta(provider: Optional[str])`
- `build_llm_failure_meta(message: str = DEFAULT_MESSAGE)`
- Keep service-specific `empty_result()` helpers in each service module; do not centralize service payload shapes here.

Standard metadata:

```python
{
    "llm_status": "success" | "failed",
    "llm_provider": "main" | "backup" | "zhipu" | None,
    "llm_message": Optional[str],
}
```

Compatibility rule:

- Keep existing `analysis_mode` fields temporarily.
- Add `analysis_mode="llm_failed"` where the endpoint already exposes `analysis_mode`.
- New frontend logic should prefer `llm_status`.

**Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/pytest tests/test_llm_result_helpers.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/llm_result_helpers.py backend/tests/test_llm_result_helpers.py
git commit -m "feat: add shared llm failure metadata"
```

### Task 5: Remove Production Fallbacks From Rule/Plan/Matcher Flows

**Files:**
- Modify: `backend/app/services/ai_parser.py`
- Modify: `backend/app/services/test_plan_generator.py`
- Modify: `backend/app/services/testcase_matcher.py`
- Modify: `backend/app/services/requirement_module_analyzer.py`
- Test: `backend/tests/test_ai_parser.py`
- Test: `backend/tests/test_testcase_import_services.py`

**Step 1: Write the failing tests**

Add tests for:

- LLM exhaustion returns empty results, not clause parsing
- test plan generation returns empty plan/cases, not fallback points/cases
- testcase matcher returns empty matches for LLM exhaustion, but still short-circuits safely on empty inputs
- requirement module analyzer returns empty module result on LLM exhaustion

```python
def test_ai_parser_returns_empty_result_when_all_providers_fail(monkeypatch):
    monkeypatch.setenv("AI_PARSE_PROVIDER", "llm")
    result = parse_requirement_text("foo", llm_client=_FailingLLMClient())
    assert result["nodes"] == []
    assert result["risks"] == []
    assert result["llm_status"] == "failed"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/pytest tests/test_ai_parser.py tests/test_testcase_import_services.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Apply these rules:

- Explicit mock mode still works when the service env says `mock`.
- Normal `llm` mode no longer falls back to local parsing/matching when provider chain exhaustion occurs.
- Empty input is not an LLM failure; keep current short-circuit empty return behavior where that is business-correct.

**Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/pytest tests/test_ai_parser.py tests/test_testcase_import_services.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/ai_parser.py backend/app/services/test_plan_generator.py backend/app/services/testcase_matcher.py backend/app/services/requirement_module_analyzer.py backend/tests/test_ai_parser.py backend/tests/test_testcase_import_services.py
git commit -m "refactor: remove production llm fallbacks from parser flows"
```

### Task 6: Remove Production Fallbacks From Analysis Services

**Files:**
- Modify: `backend/app/services/architecture_analyzer.py`
- Modify: `backend/app/services/risk_service.py`
- Modify: `backend/app/services/effective_requirement_service.py`
- Modify: `backend/app/services/predev_analyzer.py`
- Modify: `backend/app/services/prerelease_auditor.py`
- Modify: `backend/app/services/evidence_service.py`
- Modify: `backend/app/services/product_doc_service.py`
- Test: `backend/tests/test_architecture_analyzer.py`

**Step 1: Write the failing tests**

Add or update tests to assert:

- architecture analysis returns empty analysis payload and `llm_failed` instead of `mock_fallback`
- risk/review/predev/prerelease/evidence/product-doc services return their service-specific empty results plus failure metadata
- explicit mock mode still returns legacy mock/static behavior when configured

```python
def test_llm_analyzer_returns_empty_result_on_exhaustion():
    fake_llm = _FailingLLMClient()
    provider = LLMAnalyzerProvider(llm_client=fake_llm)
    result = provider.analyze(image_path=None, description="desc")
    assert result["decision_tree"]["nodes"] == []
    assert provider.get_analysis_mode() == "llm_failed"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/pytest tests/test_architecture_analyzer.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Implement service-specific empty result helpers and replace production fallback branches with:

- success path
- explicit mock path
- provider chain exhaustion path returning empty result + failure metadata

Do not physically delete `MockAnalyzerProvider` in this task; keep it as an explicit mock-mode implementation and for tests.

**Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/pytest tests/test_architecture_analyzer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/architecture_analyzer.py backend/app/services/risk_service.py backend/app/services/effective_requirement_service.py backend/app/services/predev_analyzer.py backend/app/services/prerelease_auditor.py backend/app/services/evidence_service.py backend/app/services/product_doc_service.py backend/tests/test_architecture_analyzer.py
git commit -m "refactor: standardize llm failure handling across analysis services"
```

### Task 7: Update API Schemas And Routers To Surface Failure Metadata

**Files:**
- Modify: `backend/app/api/ai_parse.py`
- Modify: `backend/app/api/architecture.py`
- Modify: `backend/app/api/testcase_import.py`
- Modify: `backend/app/schemas/test_plan.py`
- Modify: `backend/app/schemas/risk.py`
- Modify: `backend/app/schemas/effective_requirement.py`
- Modify: `backend/app/schemas/product_doc.py`
- Test: `backend/tests/test_testcase_import_api.py`
- Test: `backend/tests/test_api_smoke.py`

**Step 1: Write the failing tests**

Add API-level assertions for:

- empty successful HTTP response payload shape when provider chain is exhausted
- `llm_status=failed`
- `llm_provider=null`
- `llm_message` populated
- legacy `analysis_mode` compatibility where applicable

**Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/pytest tests/test_testcase_import_api.py tests/test_api_smoke.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Make router response models and payload assembly consistent with the new service return contracts. Keep HTTP 200 for “all providers failed but request was handled” unless an endpoint is explicitly better served by non-200 semantics.

**Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/pytest tests/test_testcase_import_api.py tests/test_api_smoke.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/api/ai_parse.py backend/app/api/architecture.py backend/app/api/testcase_import.py backend/app/schemas/test_plan.py backend/app/schemas/risk.py backend/app/schemas/effective_requirement.py backend/app/schemas/product_doc.py backend/tests/test_testcase_import_api.py backend/tests/test_api_smoke.py
git commit -m "feat: expose llm failure metadata in api responses"
```

### Task 8: Migrate Frontend UI To Unified Failure State

**Files:**
- Modify: `frontend/src/pages/TestCases/index.tsx`
- Modify: `frontend/src/pages/ArchitectureAnalysis/index.tsx`
- Modify: `frontend/src/utils/enumLabels.ts`
- Modify: `frontend/src/types/index.ts`
- Test: `frontend/src/utils/enumLabels.check.ts`

**Step 1: Write the failing tests**

Add/update type and label checks:

```ts
getImportAnalysisModeLabel("llm_failed")
```

Add focused UI assertions where this repo already uses them, or at minimum update type checks and enum validation scripts.

**Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- --runInBand`
Expected: FAIL or type-check errors because `llm_failed` and `llm_status` are not wired in.

**Step 3: Write minimal implementation**

Frontend rules:

- Prefer `llm_status === "failed"` for display logic.
- Fall back to `analysis_mode === "llm_failed"` for compatibility.
- Show user-facing message:

```text
所有模型调用失败，未生成结果。请稍后重试或检查模型配置。
```

- Keep successful provider labeling by alias where helpful.

**Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- --runInBand`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/pages/TestCases/index.tsx frontend/src/pages/ArchitectureAnalysis/index.tsx frontend/src/utils/enumLabels.ts frontend/src/types/index.ts frontend/src/utils/enumLabels.check.ts
git commit -m "feat: add unified llm failure ui state"
```

### Task 9: Replace Legacy Env Docs And Add Migration Notes

**Files:**
- Modify: `backend/.env`
- Modify: `backend/.env.example`
- Modify: `docs/联调启动说明.md`
- Modify: `KNOWLEDGE_BASE.md`
- Modify: `docs/plans/2026-03-19-config-driven-llm-chain-design.md`

**Step 1: Write the failing test/check**

Document-only task. Create a checklist of strings that must be updated:

- `OPENAI_API_KEY`
- `OPENAI_TEXT_MODEL`
- `OpenAI -> 智谱`
- `mock_fallback`

**Step 2: Run the verification check**

Run: `rg -n "OPENAI_API_KEY|OPENAI_TEXT_MODEL|OpenAI -> 智谱|mock_fallback" docs KNOWLEDGE_BASE.md backend/.env backend/.env.example`
Expected: old references found before doc updates.

**Step 3: Write minimal implementation**

Update docs to describe:

- new config-driven provider chain
- explicit mock mode vs normal llm mode
- failure metadata contract
- migration examples from old env keys to new env keys
- update both `backend/.env` and `backend/.env.example` to the new format so local development and fresh deployment docs stay aligned

Write the high-level design summary into:

- `docs/plans/2026-03-19-config-driven-llm-chain-design.md`

**Step 4: Run the verification check again**

Run: `rg -n "OPENAI_API_KEY|OPENAI_TEXT_MODEL|OpenAI -> 智谱" docs KNOWLEDGE_BASE.md backend/.env backend/.env.example`
Expected: only intentionally retained migration references remain.

**Step 5: Commit**

```bash
git add backend/.env backend/.env.example docs/联调启动说明.md KNOWLEDGE_BASE.md docs/plans/2026-03-19-config-driven-llm-chain-design.md docs/plans/2026-03-19-config-driven-llm-chain.md
git commit -m "docs: document config-driven llm chain migration"
```

### Task 10: Run Focused Regression Verification

**Files:**
- Test: `backend/tests/test_llm_client.py`
- Test: `backend/tests/test_fallback_llm.py`
- Test: `backend/tests/test_ai_parser.py`
- Test: `backend/tests/test_architecture_analyzer.py`
- Test: `backend/tests/test_testcase_import_services.py`
- Test: `backend/tests/test_testcase_import_api.py`
- Test: `backend/tests/test_api_smoke.py`
- Test: `frontend/src/utils/enumLabels.check.ts`

**Step 1: Run backend focused suite**

Run:

```bash
cd backend && ./.venv/bin/pytest \
  tests/test_llm_client.py \
  tests/test_fallback_llm.py \
  tests/test_ai_parser.py \
  tests/test_architecture_analyzer.py \
  tests/test_testcase_import_services.py \
  tests/test_testcase_import_api.py \
  tests/test_api_smoke.py -v
```

Expected: PASS

**Step 2: Run frontend focused verification**

Run:

```bash
cd frontend && npm test -- --runInBand
```

Expected: PASS

**Step 3: Run targeted grep for stale fallback semantics**

Run:

```bash
rg -n "mock_fallback|using mock|using fallback|fallback to mock|关键词兜底|规则分句兜底" backend/app frontend/src docs
```

Expected: only intentional explicit-mock references or historical docs remain.

**Step 4: Review git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only planned files changed.

**Step 5: Commit**

```bash
git add backend/tests/test_llm_client.py backend/tests/test_fallback_llm.py backend/tests/test_openai_client.py backend/tests/test_zhipu_client.py backend/tests/test_base_llm_client.py backend/tests/test_llm_result_helpers.py backend/tests/test_ai_parser.py backend/tests/test_architecture_analyzer.py backend/tests/test_testcase_import_services.py backend/tests/test_testcase_import_api.py backend/tests/test_api_smoke.py backend/app/services/base_llm_client.py backend/app/services/openai_client.py backend/app/services/zhipu_client.py backend/app/services/llm_client.py backend/app/services/fallback_llm_client.py backend/app/services/llm_provider_factory.py backend/app/services/llm_result_helpers.py backend/app/services/ai_parser.py backend/app/services/test_plan_generator.py backend/app/services/testcase_matcher.py backend/app/services/requirement_module_analyzer.py backend/app/services/architecture_analyzer.py backend/app/services/risk_service.py backend/app/services/effective_requirement_service.py backend/app/services/predev_analyzer.py backend/app/services/prerelease_auditor.py backend/app/services/evidence_service.py backend/app/services/product_doc_service.py backend/app/api/ai_parse.py backend/app/api/architecture.py backend/app/api/testcase_import.py backend/app/schemas/architecture.py backend/app/schemas/testcase_import.py backend/app/schemas/test_plan.py backend/app/schemas/risk.py backend/app/schemas/effective_requirement.py backend/app/schemas/product_doc.py frontend/src/pages/TestCases/index.tsx frontend/src/pages/ArchitectureAnalysis/index.tsx frontend/src/utils/enumLabels.ts frontend/src/types/index.ts frontend/src/utils/enumLabels.check.ts backend/.env backend/.env.example docs/联调启动说明.md KNOWLEDGE_BASE.md docs/plans/2026-03-19-config-driven-llm-chain-design.md docs/plans/2026-03-19-config-driven-llm-chain.md
git commit -m "feat: migrate project to config-driven llm provider chain"
```
