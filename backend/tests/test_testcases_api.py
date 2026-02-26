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
