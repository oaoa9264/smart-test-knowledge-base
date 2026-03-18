import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _create_project_and_requirement(title_suffix: str):
    project_resp = client.post(
        "/api/projects",
        json={"name": f"tc-project-{title_suffix}-{uuid.uuid4().hex[:8]}", "description": "test"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": f"req-{title_suffix}", "raw_text": "demo", "source_type": "prd"},
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    node_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": None,
            "node_type": "root",
            "content": f"node-{title_suffix}",
            "risk_level": "high",
        },
    )
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]

    return project_id, requirement_id, node_id


def test_list_testcases_can_filter_by_requirement():
    project_resp = client.post(
        "/api/projects",
        json={"name": f"tc-filter-{uuid.uuid4().hex[:8]}", "description": "test"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    req_a = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "A", "raw_text": "A", "source_type": "prd"},
    )
    req_b = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "B", "raw_text": "B", "source_type": "prd"},
    )
    assert req_a.status_code == 201
    assert req_b.status_code == 201
    req_a_id = req_a.json()["id"]
    req_b_id = req_b.json()["id"]

    node_a = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": req_a_id,
            "parent_id": None,
            "node_type": "root",
            "content": "node-a",
            "risk_level": "high",
        },
    )
    node_b = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": req_b_id,
            "parent_id": None,
            "node_type": "root",
            "content": "node-b",
            "risk_level": "medium",
        },
    )
    assert node_a.status_code == 201
    assert node_b.status_code == 201

    created_case = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "only-a",
            "steps": "step",
            "expected_result": "ok",
            "risk_level": "high",
            "bound_rule_node_ids": [node_a.json()["id"]],
            "bound_path_ids": [],
        },
    )
    assert created_case.status_code == 201

    list_a = client.get(f"/api/testcases/projects/{project_id}?requirement_id={req_a_id}")
    list_b = client.get(f"/api/testcases/projects/{project_id}?requirement_id={req_b_id}")

    assert list_a.status_code == 200
    assert list_b.status_code == 200
    assert len(list_a.json()) == 1
    assert len(list_b.json()) == 0


def test_path_bound_testcase_survives_rule_path_regeneration():
    project_id, requirement_id, root_node_id = _create_project_and_requirement("path-sync")

    child_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": root_node_id,
            "node_type": "condition",
            "content": "node-path-child",
            "risk_level": "medium",
        },
    )
    assert child_resp.status_code == 201
    child_node_id = child_resp.json()["id"]

    tree_resp = client.get(f"/api/rules/requirements/{requirement_id}/tree")
    assert tree_resp.status_code == 200
    path_id = tree_resp.json()["paths"][0]["id"]

    create_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "path-only-case",
            "steps": "step 1",
            "expected_result": "result 1",
            "risk_level": "medium",
            "bound_rule_node_ids": [],
            "bound_path_ids": [path_id],
        },
    )
    assert create_resp.status_code == 201
    case_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/rules/nodes/{child_node_id}",
        json={"content": "node-path-child-updated"},
    )
    assert update_resp.status_code == 200

    list_resp = client.get(f"/api/testcases/projects/{project_id}?requirement_id={requirement_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["id"] == case_id
    assert list_resp.json()[0]["bound_path_ids"] == [path_id]


def test_get_and_delete_testcase():
    project_id, _, node_id = _create_project_and_requirement("get-delete")

    create_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "case-detail",
            "steps": "step 1",
            "expected_result": "result 1",
            "risk_level": "medium",
            "bound_rule_node_ids": [node_id],
            "bound_path_ids": [],
        },
    )
    assert create_resp.status_code == 201
    case_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/testcases/{case_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == case_id

    delete_resp = client.delete(f"/api/testcases/{case_id}")
    assert delete_resp.status_code == 204

    list_resp = client.get(f"/api/testcases/projects/{project_id}")
    assert list_resp.status_code == 200
    assert all(item["id"] != case_id for item in list_resp.json())


def test_delete_testcase_cascades_reco_results():
    project_id, requirement_id, node_id = _create_project_and_requirement("delete-with-reco")

    create_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "case-with-reco",
            "steps": "step 1",
            "expected_result": "result 1",
            "risk_level": "high",
            "bound_rule_node_ids": [node_id],
            "bound_path_ids": [],
        },
    )
    assert create_resp.status_code == 201
    case_id = create_resp.json()["id"]

    reco_resp = client.post(
        "/api/reco/regression",
        json={
            "requirement_id": requirement_id,
            "mode": "FULL",
            "k": 1,
            "case_filter": {"case_ids": [case_id]},
        },
    )
    assert reco_resp.status_code == 200
    run_id = reco_resp.json()["run_id"]
    assert any(item["case_id"] == case_id for item in reco_resp.json()["cases"])

    delete_resp = client.delete(f"/api/testcases/{case_id}")
    assert delete_resp.status_code == 204

    get_resp = client.get(f"/api/testcases/{case_id}")
    assert get_resp.status_code == 404

    run_detail_resp = client.get(f"/api/reco/runs/{run_id}")
    assert run_detail_resp.status_code == 200
    assert run_detail_resp.json()["results"] == []


def test_update_testcase():
    project_id, requirement_id, node_id = _create_project_and_requirement("update")

    create_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "case-before",
            "steps": "step before",
            "expected_result": "result before",
            "risk_level": "medium",
            "bound_rule_node_ids": [node_id],
            "bound_path_ids": [],
        },
    )
    assert create_resp.status_code == 201
    case_id = create_resp.json()["id"]

    node_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": node_id,
            "node_type": "condition",
            "content": "node-update-new",
            "risk_level": "high",
        },
    )
    assert node_resp.status_code == 201
    new_node_id = node_resp.json()["id"]

    update_resp = client.put(
        f"/api/testcases/{case_id}",
        json={
            "title": "case-after",
            "steps": "step after",
            "expected_result": "result after",
            "risk_level": "high",
            "bound_rule_node_ids": [new_node_id],
            "bound_path_ids": [],
        },
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["id"] == case_id
    assert body["title"] == "case-after"
    assert body["steps"] == "step after"
    assert body["expected_result"] == "result after"
    assert body["risk_level"] == "high"
    assert body["bound_rule_node_ids"] == [new_node_id]


def test_create_testcase_rejects_invalid_bound_ids():
    project_id, _, _ = _create_project_and_requirement("create-invalid-bind")

    create_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "case-invalid-bind",
            "steps": "step",
            "expected_result": "result",
            "risk_level": "medium",
            "bound_rule_node_ids": ["missing-node"],
            "bound_path_ids": ["missing-path"],
        },
    )
    assert create_resp.status_code == 400
    assert "bound_" in create_resp.json()["detail"]


def test_create_testcase_rejects_cross_project_bindings():
    project_id_a, requirement_id_a, node_id_a = _create_project_and_requirement("create-owner-a")
    project_id_b, _, _ = _create_project_and_requirement("create-owner-b")

    tree_resp = client.get(f"/api/rules/requirements/{requirement_id_a}/tree")
    assert tree_resp.status_code == 200
    path_id_a = tree_resp.json()["paths"][0]["id"]

    create_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id_b,
            "title": "case-cross-project",
            "steps": "step",
            "expected_result": "result",
            "risk_level": "medium",
            "bound_rule_node_ids": [node_id_a],
            "bound_path_ids": [path_id_a],
        },
    )
    assert create_resp.status_code == 400
    assert "bound_" in create_resp.json()["detail"]

    list_resp = client.get(f"/api/testcases/projects/{project_id_b}")
    assert list_resp.status_code == 200
    assert list_resp.json() == []


def test_update_testcase_rejects_cross_project_bindings():
    project_id_a, requirement_id_a, node_id_a = _create_project_and_requirement("update-owner-a")
    project_id_b, _, node_id_b = _create_project_and_requirement("update-owner-b")

    tree_resp = client.get(f"/api/rules/requirements/{requirement_id_a}/tree")
    assert tree_resp.status_code == 200
    path_id_a = tree_resp.json()["paths"][0]["id"]

    create_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id_b,
            "title": "case-update-owner-before",
            "steps": "step before",
            "expected_result": "result before",
            "risk_level": "medium",
            "bound_rule_node_ids": [node_id_b],
            "bound_path_ids": [],
        },
    )
    assert create_resp.status_code == 201
    case_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/testcases/{case_id}",
        json={
            "title": "case-update-owner-after",
            "steps": "step after",
            "expected_result": "result after",
            "risk_level": "high",
            "status": "active",
            "bound_rule_node_ids": [node_id_a],
            "bound_path_ids": [path_id_a],
        },
    )
    assert update_resp.status_code == 400
    assert "bound_" in update_resp.json()["detail"]

    get_resp = client.get(f"/api/testcases/{case_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["bound_rule_node_ids"] == [node_id_b]
    assert get_resp.json()["bound_path_ids"] == []


def test_create_and_update_testcase_status():
    project_id, _, node_id = _create_project_and_requirement("status")

    create_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "case-status-before",
            "steps": "step before",
            "expected_result": "result before",
            "risk_level": "medium",
            "status": "needs_review",
            "bound_rule_node_ids": [node_id],
            "bound_path_ids": [],
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["status"] == "needs_review"

    case_id = created["id"]
    update_resp = client.put(
        f"/api/testcases/{case_id}",
        json={
            "title": "case-status-after",
            "steps": "step after",
            "expected_result": "result after",
            "risk_level": "high",
            "status": "active",
            "bound_rule_node_ids": [node_id],
            "bound_path_ids": [],
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["status"] == "active"


def test_confirm_cases_rejects_nodes_from_other_requirement():
    project_id, requirement_id, _ = _create_project_and_requirement("confirm-owner-a")
    _, _, other_node_id = _create_project_and_requirement("confirm-owner-b")

    resp = client.post(
        "/api/test-plan/confirm-cases",
        json={
            "requirement_id": requirement_id,
            "test_cases": [
                {
                    "title": "跨需求绑定",
                    "preconditions": ["p"],
                    "steps": ["s"],
                    "expected_result": ["e"],
                    "risk_level": "medium",
                    "related_node_ids": [other_node_id],
                }
            ],
        },
    )
    assert resp.status_code == 400
    assert "related_node_ids" in resp.json()["detail"]

    list_resp = client.get(f"/api/testcases/projects/{project_id}?requirement_id={requirement_id}")
    assert list_resp.status_code == 200
    assert list_resp.json() == []


def test_confirm_cases_is_idempotent_for_confirmed_session():
    project_id, requirement_id, node_id = _create_project_and_requirement("confirm-idempotent")

    session_resp = client.post(
        "/api/test-plan/sessions",
        json={"requirement_id": requirement_id},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    payload = {
        "requirement_id": requirement_id,
        "session_id": session_id,
        "test_cases": [
            {
                "title": "确认用例",
                "preconditions": ["p"],
                "steps": ["s"],
                "expected_result": ["e"],
                "risk_level": "medium",
                "related_node_ids": [node_id],
            }
        ],
    }

    first = client.post("/api/test-plan/confirm-cases", json=payload)
    second = client.post("/api/test-plan/confirm-cases", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()

    list_resp = client.get(f"/api/testcases/projects/{project_id}?requirement_id={requirement_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_generate_test_plan_rejects_session_requirement_mismatch(monkeypatch):
    project_id, requirement_id_a, _ = _create_project_and_requirement("plan-mismatch-a")
    _, requirement_id_b, _ = _create_project_and_requirement("plan-mismatch-b")

    session_resp = client.post(
        "/api/test-plan/sessions",
        json={"requirement_id": requirement_id_a},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    monkeypatch.setattr(
        "app.api.test_plan.generate_test_plan",
        lambda nodes, paths: {
            "markdown": "mock plan",
            "test_points": [
                {
                    "id": "tp1",
                    "name": "测试点",
                    "description": "desc",
                    "type": "normal",
                    "related_node_ids": [],
                    "priority": "medium",
                }
            ],
        },
    )

    resp = client.post(
        "/api/test-plan/generate",
        json={"requirement_id": requirement_id_b, "session_id": session_id},
    )
    assert resp.status_code == 400
    assert "session requirement mismatch" in resp.json()["detail"].lower()

    session_detail = client.get(f"/api/test-plan/sessions/{session_id}")
    assert session_detail.status_code == 200
    assert session_detail.json()["status"] == "plan_generating"
    assert session_detail.json()["plan_markdown"] is None


def test_generate_test_cases_rejects_session_requirement_mismatch(monkeypatch):
    _, requirement_id_a, _ = _create_project_and_requirement("case-mismatch-a")
    _, requirement_id_b, _ = _create_project_and_requirement("case-mismatch-b")

    session_resp = client.post(
        "/api/test-plan/sessions",
        json={"requirement_id": requirement_id_a},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    monkeypatch.setattr(
        "app.api.test_plan.generate_test_cases",
        lambda test_plan_markdown, test_points, nodes, paths: [
            {
                "title": "mock case",
                "preconditions": ["p"],
                "steps": ["s"],
                "expected_result": ["e"],
                "risk_level": "medium",
                "related_node_ids": [],
            }
        ],
    )

    resp = client.post(
        "/api/test-plan/generate-cases",
        json={
            "requirement_id": requirement_id_b,
            "session_id": session_id,
            "test_plan_markdown": "plan",
            "test_points": [],
        },
    )
    assert resp.status_code == 400
    assert "session requirement mismatch" in resp.json()["detail"].lower()

    session_detail = client.get(f"/api/test-plan/sessions/{session_id}")
    assert session_detail.status_code == 200
    assert session_detail.json()["status"] == "plan_generating"
    assert session_detail.json()["generated_cases"] is None


def test_generate_test_plan_falls_back_when_llm_client_unavailable(monkeypatch):
    project_id, requirement_id, _ = _create_project_and_requirement("plan-fallback")

    session_resp = client.post(
        "/api/test-plan/sessions",
        json={"requirement_id": requirement_id},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    class _FailingLLMClient:
        def __init__(self, *args, **kwargs):
            raise ValueError("missing llm credentials")

    monkeypatch.setattr("app.services.test_plan_generator.LLMClient", _FailingLLMClient)

    resp = client.post(
        "/api/test-plan/generate",
        json={"requirement_id": requirement_id, "session_id": session_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["markdown"] != ""
    assert len(body["test_points"]) > 0

    session_detail = client.get(f"/api/test-plan/sessions/{session_id}")
    assert session_detail.status_code == 200
    assert session_detail.json()["status"] == "plan_generated"


def test_generate_test_plan_archives_fresh_session_on_failure(monkeypatch):
    _, requirement_id, _ = _create_project_and_requirement("plan-failure-archive")

    session_resp = client.post(
        "/api/test-plan/sessions",
        json={"requirement_id": requirement_id},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    monkeypatch.setattr(
        "app.api.test_plan.generate_test_plan",
        lambda nodes, paths: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    resp = client.post(
        "/api/test-plan/generate",
        json={"requirement_id": requirement_id, "session_id": session_id},
    )
    assert resp.status_code == 500

    session_detail = client.get(f"/api/test-plan/sessions/{session_id}")
    assert session_detail.status_code == 200
    assert session_detail.json()["status"] == "archived"
    assert session_detail.json()["plan_markdown"] is None


def test_generate_test_cases_falls_back_when_llm_client_unavailable(monkeypatch):
    _, requirement_id, node_id = _create_project_and_requirement("cases-fallback")

    session_resp = client.post(
        "/api/test-plan/sessions",
        json={"requirement_id": requirement_id},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    class _FailingLLMClient:
        def __init__(self, *args, **kwargs):
            raise ValueError("missing llm credentials")

    monkeypatch.setattr("app.services.test_plan_generator.LLMClient", _FailingLLMClient)

    resp = client.post(
        "/api/test-plan/generate-cases",
        json={
            "requirement_id": requirement_id,
            "session_id": session_id,
            "test_plan_markdown": "mock plan",
            "test_points": [
                {
                    "id": "tp1",
                    "name": "测试点",
                    "description": "desc",
                    "type": "normal",
                    "related_node_ids": [node_id],
                    "priority": "medium",
                }
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert len(body["test_cases"]) > 0

    session_detail = client.get(f"/api/test-plan/sessions/{session_id}")
    assert session_detail.status_code == 200
    assert session_detail.json()["status"] == "cases_generated"
