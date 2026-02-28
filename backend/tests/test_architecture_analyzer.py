import io

from fastapi.testclient import TestClient

from app.main import app
from app.services.architecture_analyzer import LLMAnalyzerProvider, MockAnalyzerProvider


client = TestClient(app)


def _build_llm_result():
    return {
        "decision_tree": {
            "nodes": [
                {
                    "id": "dt_1",
                    "type": "root",
                    "content": "用户提交提现申请",
                    "parent_id": None,
                    "risk_level": "medium",
                }
            ]
        },
        "test_plan": {
            "markdown": "# AI 生成测试方案\n- 覆盖主流程与异常流程",
            "sections": ["scope", "strategy"],
        },
        "risk_points": [
            {
                "id": "rp_1",
                "description": "转账链路有超时风险",
                "severity": "high",
                "mitigation": "增加重试与超时兜底",
                "related_node_ids": ["dt_1"],
            }
        ],
        "test_cases": [
            {
                "title": "提现主链路验证",
                "steps": "验证用户申请到转账完成",
                "expected_result": "主链路执行成功",
                "risk_level": "medium",
                "related_node_ids": ["dt_1"],
            }
        ],
    }


class _FakeLLMClient:
    def __init__(self, *, vision_text="阶段1架构理解", json_result=None, raise_in_json=False):
        self.vision_text = vision_text
        self.json_result = json_result if json_result is not None else _build_llm_result()
        self.raise_in_json = raise_in_json
        self.vision_calls = []
        self.json_calls = []

    def chat_with_vision(self, system_prompt, user_content):
        self.vision_calls.append((system_prompt, user_content))
        return self.vision_text

    def chat_with_json(self, system_prompt, user_prompt):
        self.json_calls.append((system_prompt, user_prompt))
        if self.raise_in_json:
            raise RuntimeError("llm unavailable")
        return self.json_result

    @staticmethod
    def image_to_base64_url(file_path):
        return "data:image/png;base64,fake"


def test_mock_analyzer_returns_four_artifacts():
    provider = MockAnalyzerProvider()

    result = provider.analyze(
        image_path=None,
        title="提现需求拆解",
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
    assert result["test_cases"][0]["title"].startswith("提现需求拆解-路径用例")
    assert any(point["severity"] in ["critical", "high"] for point in result["risk_points"])
    assert provider.get_analysis_mode() == "mock"


def test_llm_analyzer_text_only_skips_vision_stage():
    fake_llm = _FakeLLMClient()
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    result = provider.analyze(
        image_path=None,
        title="提现需求拆解",
        description="用户提交提现申请并校验余额。",
    )

    assert len(fake_llm.vision_calls) == 0
    assert len(fake_llm.json_calls) == 1
    assert "decision_tree" in result
    assert result["test_cases"][0]["title"] == "提现主链路验证"
    assert provider.get_analysis_mode() == "llm"


def test_llm_analyzer_with_image_runs_two_stages():
    fake_llm = _FakeLLMClient(vision_text="流程图展示了提现主链路和异常链路")
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    provider.analyze(
        image_path="/tmp/withdraw_flow.png",
        title="提现需求拆解",
        description="用户提交提现申请。",
    )

    assert len(fake_llm.vision_calls) == 1
    assert len(fake_llm.json_calls) == 1
    _, user_prompt = fake_llm.json_calls[0]
    assert "流程图展示了提现主链路和异常链路" in user_prompt


def test_llm_analyzer_fallbacks_to_mock_on_llm_error():
    fake_llm = _FakeLLMClient(raise_in_json=True)
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    result = provider.analyze(
        image_path=None,
        title="提现需求拆解",
        description="用户提交提现申请。如果余额不足，则拒绝提现。",
    )

    assert result["test_cases"][0]["title"].startswith("提现需求拆解-路径用例")
    assert provider.get_analysis_mode() == "mock_fallback"


def test_llm_analyzer_fallbacks_to_mock_on_invalid_llm_payload():
    fake_llm = _FakeLLMClient(json_result={"invalid": True})
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    result = provider.analyze(
        image_path=None,
        title="退款流程拆解",
        description="用户提交退款申请。如果订单已发货，则人工审核。",
    )

    assert result["test_cases"][0]["title"].startswith("退款流程拆解-路径用例")
    assert provider.get_analysis_mode() == "mock_fallback"


def test_llm_analyzer_normalizes_common_payload_shape_drifts():
    drift_payload = {
        "decision_tree": {
            "nodes": [
                {
                    "type": "root",
                    "content": "用户提交提现申请",
                    "risk_level": "HIGH",
                }
            ]
        },
        "test_plan": {
            "markdown": "# AI 生成测试方案",
            "sections": [{"name": "scope"}, {"name": "strategy"}],
        },
        "risk_points": [
            {
                "description": "转账链路有超时风险",
                "severity": "高",
                "mitigation": "增加重试与超时兜底",
            }
        ],
        "test_cases": [
            {
                "title": "提现主链路验证",
                "steps": ["验证用户申请", "验证余额扣减", "验证转账结果"],
                "expected_result": "主链路执行成功",
                "risk_level": "中",
                "related_node_ids": "dt_1",
            }
        ],
    }
    fake_llm = _FakeLLMClient(json_result=drift_payload)
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    result = provider.analyze(
        image_path=None,
        title="提现需求拆解",
        description="用户提交提现申请并校验余额。",
    )

    assert provider.get_analysis_mode() == "llm"
    assert result["decision_tree"]["nodes"][0]["id"] == "dt_1"
    assert result["test_plan"]["sections"] == ["scope", "strategy"]
    assert result["risk_points"][0]["id"] == "rp_1"
    assert result["risk_points"][0]["related_node_ids"] == ["dt_1"]
    assert isinstance(result["test_cases"][0]["steps"], str)
    assert result["test_cases"][0]["related_node_ids"] == ["dt_1"]


def test_llm_analyzer_normalizes_enveloped_alias_payload():
    drift_payload = {
        "data": {
            "decisionTree": [
                {
                    "nodeId": "root_1",
                    "nodeType": "根节点",
                    "text": "用户提交提现申请",
                    "risk": "高",
                }
            ],
            "testPlan": {
                "content": "# 方案\n- 覆盖主链路",
                "outline": ["scope", {"title": "strategy"}],
            },
            "riskPoints": {
                "items": [
                    {
                        "content": "转账链路超时风险",
                        "level": "严重",
                        "node_ids": "root_1",
                    }
                ]
            },
            "testCases": {
                "items": [
                    {
                        "name": "提现主链路验证",
                        "actions": ["验证申请", "验证余额扣减", "验证转账结果"],
                        "expected": "主链路执行成功",
                        "risk": "中",
                        "node_ids": ["root_1"],
                    }
                ]
            },
        }
    }
    fake_llm = _FakeLLMClient(json_result=drift_payload)
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    result = provider.analyze(
        image_path=None,
        title="提现需求拆解",
        description="用户提交提现申请并校验余额。",
    )

    assert provider.get_analysis_mode() == "llm"
    assert result["decision_tree"]["nodes"][0]["id"] == "root_1"
    assert result["decision_tree"]["nodes"][0]["type"] == "root"
    assert result["test_plan"]["sections"] == ["scope", "strategy"]
    assert result["risk_points"][0]["severity"] == "critical"
    assert result["risk_points"][0]["related_node_ids"] == ["root_1"]
    assert result["test_cases"][0]["title"] == "提现主链路验证"
    assert isinstance(result["test_cases"][0]["steps"], str)
    assert result["test_cases"][0]["related_node_ids"] == ["root_1"]


def test_mock_analyzer_combines_description_and_flowchart_context():
    provider = MockAnalyzerProvider()

    result = provider.analyze(
        image_path="/uploads/architecture/refund_flow.png",
        title="退款流程拆解",
        description="用户提交退款申请。如果订单已发货，则进入人工审核。",
    )
    node_contents = [node["content"] for node in result["decision_tree"]["nodes"]]

    assert any("用户提交退款申请" in content for content in node_contents)
    assert any("流程图参考信息" in content for content in node_contents)


def test_architecture_api_analyze_supports_image_only(monkeypatch):
    monkeypatch.setenv("ANALYZER_PROVIDER", "mock")
    project_resp = client.post("/api/projects", json={"name": "arch-p1-image", "description": "architecture"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    analyze_resp = client.post(
        "/api/ai/architecture/analyze",
        data={
            "project_id": str(project_id),
            "title": "仅流程图拆解",
            "description_text": "",
        },
        files={"image": ("payment_flow.png", io.BytesIO(b"fake-image-content"), "image/png")},
    )

    assert analyze_resp.status_code == 201
    analyze_data = analyze_resp.json()
    assert analyze_data["analysis_mode"] == "mock"
    assert "流程图" in analyze_data["decision_tree"]["nodes"][0]["content"]


def test_architecture_api_analyze_get_import_flow(monkeypatch):
    monkeypatch.setenv("ANALYZER_PROVIDER", "mock")
    project_resp = client.post("/api/projects", json={"name": "arch-p1", "description": "architecture"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    analyze_resp = client.post(
        "/api/ai/architecture/analyze",
        data={
            "project_id": str(project_id),
            "title": "提现需求拆解",
            "description_text": (
                "用户提交提现申请。如果用户未实名认证，则拒绝提现。"
                "如果已实名认证，检查余额是否充足。余额不足则提示余额不足。"
                "转账异常时进入重试队列。"
            ),
        },
    )
    assert analyze_resp.status_code == 201
    analyze_data = analyze_resp.json()
    assert analyze_data["analysis_mode"] == "mock"
    analysis_id = analyze_data["id"]
    assert analyze_data["test_cases"][0]["title"].startswith("提现需求拆解-路径用例")

    get_resp = client.get(f"/api/ai/architecture/{analysis_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == analysis_id
    assert get_resp.json()["result"]["analysis_mode"] == "mock"

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
    assert case_resp.json()[0]["title"].startswith("提现需求拆解-路径用例")
