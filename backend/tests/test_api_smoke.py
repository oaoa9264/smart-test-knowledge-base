from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app


client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_project_rule_case_coverage_flow():
    project_resp = client.post(
        "/api/projects",
        json={"name": "P1-{0}".format(uuid4().hex[:8]), "description": "demo"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "登录需求", "raw_text": "当密码错误3次锁定", "source_type": "prd"},
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    root_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": None,
            "node_type": "root",
            "content": "用户登录",
            "risk_level": "high",
        },
    )
    assert root_resp.status_code == 201
    root_id = root_resp.json()["id"]

    child_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": root_id,
            "node_type": "condition",
            "content": "密码正确",
            "risk_level": "medium",
        },
    )
    assert child_resp.status_code == 201

    case_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "登录成功",
            "steps": "输入正确密码",
            "expected_result": "登录成功",
            "risk_level": "high",
            "bound_rule_node_ids": [root_id],
            "bound_path_ids": [],
        },
    )
    assert case_resp.status_code == 201

    coverage_resp = client.get(f"/api/coverage/projects/{project_id}")
    assert coverage_resp.status_code == 200
    assert coverage_resp.json()["summary"]["total_nodes"] >= 2


def test_coverage_can_be_split_by_requirement():
    project_resp = client.post(
        "/api/projects",
        json={"name": "P2-{0}".format(uuid4().hex[:8]), "description": "coverage split"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    req1_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "需求A", "raw_text": "A", "source_type": "prd"},
    )
    assert req1_resp.status_code == 201
    req1_id = req1_resp.json()["id"]

    req2_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "需求B", "raw_text": "B", "source_type": "prd"},
    )
    assert req2_resp.status_code == 201
    req2_id = req2_resp.json()["id"]

    req1_node_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": req1_id,
            "parent_id": None,
            "node_type": "root",
            "content": "需求A-节点",
            "risk_level": "high",
        },
    )
    assert req1_node_resp.status_code == 201
    req1_node_id = req1_node_resp.json()["id"]

    req2_node_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": req2_id,
            "parent_id": None,
            "node_type": "root",
            "content": "需求B-节点",
            "risk_level": "critical",
        },
    )
    assert req2_node_resp.status_code == 201

    case_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "覆盖需求A",
            "steps": "执行A流程",
            "expected_result": "A通过",
            "risk_level": "high",
            "bound_rule_node_ids": [req1_node_id],
            "bound_path_ids": [],
        },
    )
    assert case_resp.status_code == 201

    req1_coverage = client.get(f"/api/coverage/projects/{project_id}/requirements/{req1_id}")
    assert req1_coverage.status_code == 200
    assert req1_coverage.json()["summary"]["total_nodes"] == 1
    assert req1_coverage.json()["summary"]["covered_nodes"] == 1

    req2_coverage = client.get(f"/api/coverage/projects/{project_id}/requirements/{req2_id}")
    assert req2_coverage.status_code == 200
    assert req2_coverage.json()["summary"]["total_nodes"] == 1
    assert req2_coverage.json()["summary"]["covered_nodes"] == 0

    project_coverage = client.get(f"/api/coverage/projects/{project_id}")
    assert project_coverage.status_code == 200
    assert project_coverage.json()["summary"]["total_nodes"] == 2
    assert project_coverage.json()["summary"]["covered_nodes"] == 1


def test_ai_parse_returns_draft_nodes():
    resp = client.post(
        "/api/ai/parse",
        json={"raw_text": "如果用户未实名则禁止提现"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis_mode"] in ["llm", "mock", "mock_fallback"]
    assert "nodes" in body
    assert len(body["nodes"]) >= 1


def test_deleted_node_is_hidden_from_rule_tree():
    project_resp = client.post(
        "/api/projects",
        json={"name": "P3-{0}".format(uuid4().hex[:8]), "description": "delete node visibility"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "删除节点需求", "raw_text": "删除后树不展示", "source_type": "prd"},
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    node_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": None,
            "node_type": "root",
            "content": "待删除节点",
            "risk_level": "low",
        },
    )
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]

    delete_resp = client.delete(f"/api/rules/nodes/{node_id}")
    assert delete_resp.status_code == 200

    tree_resp = client.get(f"/api/rules/requirements/{requirement_id}/tree")
    assert tree_resp.status_code == 200
    assert tree_resp.json()["nodes"] == []


def test_deleted_node_is_hidden_from_coverage_matrix():
    project_resp = client.post(
        "/api/projects",
        json={"name": "P4-{0}".format(uuid4().hex[:8]), "description": "delete node coverage visibility"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "删除后覆盖需求", "raw_text": "删除后覆盖不展示", "source_type": "prd"},
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    node_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": None,
            "node_type": "root",
            "content": "覆盖矩阵待删除节点",
            "risk_level": "low",
        },
    )
    assert node_resp.status_code == 201
    node_id = node_resp.json()["id"]

    delete_resp = client.delete(f"/api/rules/nodes/{node_id}")
    assert delete_resp.status_code == 200

    req_coverage_resp = client.get(f"/api/coverage/projects/{project_id}/requirements/{requirement_id}")
    assert req_coverage_resp.status_code == 200
    assert req_coverage_resp.json()["summary"]["total_nodes"] == 0
    assert req_coverage_resp.json()["rows"] == []

    project_coverage_resp = client.get(f"/api/coverage/projects/{project_id}")
    assert project_coverage_resp.status_code == 200
    assert project_coverage_resp.json()["summary"]["total_nodes"] == 0
    assert project_coverage_resp.json()["rows"] == []


def test_update_node_rejects_cycle_parent_assignment():
    project_resp = client.post(
        "/api/projects",
        json={"name": "P5-{0}".format(uuid4().hex[:8]), "description": "cycle-check"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "环检测需求", "raw_text": "禁止形成环", "source_type": "prd"},
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    root_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": None,
            "node_type": "root",
            "content": "root",
            "risk_level": "high",
        },
    )
    assert root_resp.status_code == 201
    root_id = root_resp.json()["id"]

    child_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": root_id,
            "node_type": "condition",
            "content": "child",
            "risk_level": "medium",
        },
    )
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    cycle_resp = client.put(
        f"/api/rules/nodes/{root_id}",
        json={"parent_id": child_id},
    )
    assert cycle_resp.status_code == 400


def test_update_node_allows_parent_id_to_become_null():
    project_resp = client.post(
        "/api/projects",
        json={"name": "P6-{0}".format(uuid4().hex[:8]), "description": "set parent null"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "提级到根节点", "raw_text": "支持 parent_id 置空", "source_type": "prd"},
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    root_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": None,
            "node_type": "root",
            "content": "root",
            "risk_level": "high",
        },
    )
    assert root_resp.status_code == 201
    root_id = root_resp.json()["id"]

    child_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": root_id,
            "node_type": "condition",
            "content": "child",
            "risk_level": "medium",
        },
    )
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    update_resp = client.put(
        f"/api/rules/nodes/{child_id}",
        json={"parent_id": None},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["node"]["parent_id"] is None

    tree_resp = client.get(f"/api/rules/requirements/{requirement_id}/tree")
    assert tree_resp.status_code == 200
    nodes = {node["id"]: node for node in tree_resp.json()["nodes"]}
    assert nodes[child_id]["parent_id"] is None


def test_suggest_update_without_risk_item_uses_supplement_text():
    import_resp = client.post(
        "/api/product-docs/import",
        json={
            "product_code": "DOC-{0}".format(uuid4().hex[:8]),
            "name": "手工补录文档",
            "description": "doc import",
            "content": "## 登录\n系统支持用户名密码登录。\n\n## 风控\n登录失败达到阈值需要限制。",
        },
    )
    assert import_resp.status_code == 201
    product_doc_id = import_resp.json()["id"]

    suggest_resp = client.post(
        "/api/product-docs/suggest-update",
        json={
            "product_doc_id": product_doc_id,
            "clarification_text": "需要补充验证码触发条件。",
            "supplement_text": "登录失败达到5次后触发验证码校验。",
        },
    )

    assert suggest_resp.status_code == 201
    body = suggest_resp.json()
    assert body["risk_item_id"] is None
    assert body["chunk_id"] is not None


def test_suggest_update_rejects_missing_risk_item_and_supplement_text():
    import_resp = client.post(
        "/api/product-docs/import",
        json={
            "product_code": "DOC-{0}".format(uuid4().hex[:8]),
            "name": "缺少查询条件文档",
            "description": "doc import",
            "content": "## 登录\n系统支持用户名密码登录。",
        },
    )
    assert import_resp.status_code == 201
    product_doc_id = import_resp.json()["id"]

    suggest_resp = client.post(
        "/api/product-docs/suggest-update",
        json={
            "product_doc_id": product_doc_id,
            "clarification_text": "只有澄清，没有检索条件。",
        },
    )

    assert suggest_resp.status_code == 400
