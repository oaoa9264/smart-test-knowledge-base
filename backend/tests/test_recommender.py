import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services.cover_set import compute_cover_sets
from app.services.recommender import recommend_regression_set
from app.services.risk_scorer import compute_risk_scores, compute_tree_stats

client = TestClient(app)


def test_recommend_regression_set_selects_highest_weighted_gain():
    result = recommend_regression_set(
        universe={"n1", "n2", "n3"},
        risk_weights={"n1": 5.0, "n2": 3.0, "n3": 1.0},
        cover_sets={
            1: {"n1"},
            2: {"n2", "n3"},
            3: {"n1", "n2"},
        },
        k=2,
    )

    assert [item["case_id"] for item in result["cases"]] == [3, 2]
    assert result["summary"]["covered_risk"] == 9.0
    assert result["summary"]["coverage_ratio"] == 1.0


def test_compute_risk_scores_applies_uncovered_bonus_and_normalization():
    nodes = [
        {"id": "n1", "parent_id": None, "risk_level": "high", "version": 2},
        {"id": "n2", "parent_id": "n1", "risk_level": "critical", "version": 1},
    ]
    stats = compute_tree_stats(nodes)
    scores = compute_risk_scores(nodes=nodes, tree_stats=stats, uncovered_node_ids={"n2"})

    assert round(scores["n1"], 2) == 11.50
    assert round(scores["n2"], 2) == 14.75


def test_compute_cover_sets_expands_nodes_from_bound_paths():
    cases = [
        {"id": 101, "bound_rule_nodes": ["n1"], "bound_paths": ["p1"]},
        {"id": 102, "bound_rule_nodes": [], "bound_paths": []},
    ]
    path_map = {"p1": ["n2", "n3"]}

    cover_sets = compute_cover_sets(cases=cases, path_map=path_map)

    assert cover_sets[101] == {"n1", "n2", "n3"}
    assert cover_sets[102] == set()


def test_recommendation_api_flow_smoke():
    project_resp = client.post(
        "/api/projects",
        json={"name": f"reco-project-{uuid.uuid4().hex[:8]}", "description": "reco"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={"title": "回归推荐", "raw_text": "推荐用例", "source_type": "prd"},
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    root_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": None,
            "node_type": "root",
            "content": "根节点",
            "risk_level": "critical",
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
            "content": "子节点",
            "risk_level": "high",
        },
    )
    assert child_resp.status_code == 201

    case_resp = client.post(
        "/api/testcases",
        json={
            "project_id": project_id,
            "title": "覆盖根节点用例",
            "steps": "执行",
            "expected_result": "通过",
            "risk_level": "high",
            "bound_rule_node_ids": [root_id],
            "bound_path_ids": [],
        },
    )
    assert case_resp.status_code == 201

    reco_resp = client.post(
        "/api/reco/regression",
        json={"requirement_id": requirement_id, "mode": "FULL", "k": 2},
    )
    assert reco_resp.status_code == 200
    reco_body = reco_resp.json()
    assert reco_body["run_id"] > 0
    assert reco_body["summary"]["picked"] >= 1
    assert len(reco_body["cases"]) >= 1
    assert reco_body["cases"][0]["why_selected"]

    list_runs_resp = client.get(f"/api/reco/runs?requirement_id={requirement_id}")
    assert list_runs_resp.status_code == 200
    runs = list_runs_resp.json()
    assert len(runs) >= 1

    run_detail_resp = client.get(f"/api/reco/runs/{reco_body['run_id']}")
    assert run_detail_resp.status_code == 200
    detail = run_detail_resp.json()
    assert detail["run"]["id"] == reco_body["run_id"]
    assert len(detail["results"]) >= 1
