from fastapi.testclient import TestClient

from app.main import app
from app.services.architecture_analyzer import MockAnalyzerProvider


client = TestClient(app)


def test_mock_analyzer_returns_four_artifacts():
    provider = MockAnalyzerProvider()

    result = provider.analyze(
        image_path=None,
        title="提现架构拆解",
        description=(
            "用户提交提现申请。如果用户未实名认证，则拒绝提现。"
            "如果已实名认证，检查余额是否充足。余额充足则发起转账。"
            "转账过程中如果银行接口超时，则进入重试队列。"
        ),
    )

    assert "decision_tree" in result
    assert "test_plan" in result
    assert "risk_points" in result
    assert "test_cases" in result

    assert len(result["decision_tree"]["nodes"]) >= 3
    assert len(result["test_cases"]) >= 2
    assert result["test_cases"][0]["title"].startswith("提现架构拆解-路径用例")
    assert any(point["severity"] in ["critical", "high"] for point in result["risk_points"])


def test_architecture_api_analyze_get_import_flow():
    project_resp = client.post("/api/projects", json={"name": "arch-p1", "description": "architecture"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    analyze_resp = client.post(
        "/api/ai/architecture/analyze",
        data={
            "project_id": str(project_id),
            "title": "提现架构拆解",
            "description_text": (
                "用户提交提现申请。如果用户未实名认证，则拒绝提现。"
                "如果已实名认证，检查余额是否充足。余额不足则提示余额不足。"
                "转账异常时进入重试队列。"
            ),
        },
    )
    assert analyze_resp.status_code == 201
    analyze_data = analyze_resp.json()
    analysis_id = analyze_data["id"]
    assert analyze_data["test_cases"][0]["title"].startswith("提现架构拆解-路径用例")

    get_resp = client.get(f"/api/ai/architecture/{analysis_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == analysis_id

    import_resp = client.post(
        f"/api/ai/architecture/{analysis_id}/import",
        json={
            "import_decision_tree": True,
            "import_test_cases": True,
            "import_risk_points": True,
        },
    )
    assert import_resp.status_code == 200
    import_data = import_resp.json()
    assert import_data["imported_rule_nodes"] > 0
    assert import_data["imported_test_cases"] > 0
    assert import_data["requirement_id"] is not None

    tree_resp = client.get(f"/api/rules/requirements/{import_data['requirement_id']}/tree")
    assert tree_resp.status_code == 200
    assert len(tree_resp.json()["nodes"]) > 0

    case_resp = client.get(f"/api/testcases/projects/{project_id}")
    assert case_resp.status_code == 200
    assert len(case_resp.json()) > 0
    assert case_resp.json()[0]["title"].startswith("提现架构拆解-路径用例")
