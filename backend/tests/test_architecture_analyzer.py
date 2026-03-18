import io
import os

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.entities import InputType, RequirementInput
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
    }


class _FakeLLMClient:
    def __init__(self, *, vision_text="阶段1架构理解", json_result=None, raise_in_json=False, provider_name="openai"):
        self.vision_text = vision_text
        self.json_result = json_result if json_result is not None else _build_llm_result()
        self.raise_in_json = raise_in_json
        self.provider_name = provider_name
        self.vision_calls = []
        self.json_calls = []
        self._last_provider = None
        self._last_provider_by_method = {}

    def chat_with_vision(self, system_prompt, user_content):
        self.vision_calls.append((system_prompt, user_content))
        self._last_provider = self.provider_name
        self._last_provider_by_method["chat_with_vision"] = self.provider_name
        return self.vision_text

    def chat_with_json(self, system_prompt, user_prompt):
        self.json_calls.append((system_prompt, user_prompt))
        self._last_provider = self.provider_name
        self._last_provider_by_method["chat_with_json"] = self.provider_name
        if self.raise_in_json:
            raise RuntimeError("llm unavailable")
        return self.json_result

    def get_last_provider(self, method_name=None):
        if method_name:
            return self._last_provider_by_method.get(method_name)
        return self._last_provider

    @staticmethod
    def image_to_base64_url(file_path):
        return "data:image/png;base64,fake"


def test_mock_analyzer_returns_decision_tree_only():
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
    assert len(result["decision_tree"]["nodes"]) >= 3
    assert result["test_plan"] is None
    assert result["risk_points"] == []
    assert result["test_cases"] == []
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
    assert result["test_plan"] is None
    assert result["risk_points"] == []
    assert result["test_cases"] == []
    assert provider.get_analysis_mode() == "llm"
    assert provider.get_llm_provider() == "openai"


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


def test_llm_analyzer_vision_output_truncates_to_4000_chars():
    long_text = "A" * 5000
    fake_llm = _FakeLLMClient(vision_text=long_text)
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    provider.analyze(
        image_path="/tmp/withdraw_flow.png",
        title="提现需求拆解",
        description="用户提交提现申请。",
    )

    _, user_prompt = fake_llm.json_calls[0]
    assert ("A" * 4000) in user_prompt
    assert ("A" * 4001) not in user_prompt


def test_llm_analyzer_fallbacks_to_mock_on_llm_error():
    fake_llm = _FakeLLMClient(raise_in_json=True)
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    result = provider.analyze(
        image_path=None,
        title="提现需求拆解",
        description="用户提交提现申请。如果余额不足，则拒绝提现。",
    )

    assert "decision_tree" in result
    assert len(result["decision_tree"]["nodes"]) >= 1
    assert result["test_cases"] == []
    assert provider.get_analysis_mode() == "mock_fallback"
    assert provider.get_llm_provider() == "openai"


def test_llm_analyzer_fallbacks_to_mock_on_invalid_llm_payload():
    fake_llm = _FakeLLMClient(json_result={"invalid": True})
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    result = provider.analyze(
        image_path=None,
        title="退款流程拆解",
        description="用户提交退款申请。如果订单已发货，则人工审核。",
    )

    assert "decision_tree" in result
    assert len(result["decision_tree"]["nodes"]) >= 1
    assert result["test_cases"] == []
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
    assert result["test_plan"] is None
    assert result["risk_points"] == []
    assert result["test_cases"] == []


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
    assert result["test_plan"] is None
    assert result["risk_points"] == []
    assert result["test_cases"] == []


def test_llm_analyzer_deduplicates_exact_sibling_nodes_and_relinks_children():
    fake_llm = _FakeLLMClient(
        json_result={
            "decision_tree": {
                "nodes": [
                    {"id": "dt_1", "type": "root", "content": "用户提交订单", "parent_id": None, "risk_level": "medium"},
                    {"id": "dt_2", "type": "branch", "content": "进入支付页", "parent_id": "dt_1", "risk_level": "low"},
                    {"id": "dt_3", "type": "branch", "content": "进入支付页", "parent_id": "dt_1", "risk_level": "low"},
                    {"id": "dt_4", "type": "action", "content": "展示支付方式", "parent_id": "dt_3", "risk_level": "low"},
                ]
            }
        }
    )
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    result = provider.analyze(
        image_path=None,
        title="下单流程拆解",
        description="用户提交订单并进入支付页面。",
    )

    nodes = result["decision_tree"]["nodes"]
    node_ids = {node["id"] for node in nodes}
    assert "dt_3" not in node_ids
    child = next(node for node in nodes if node["id"] == "dt_4")
    assert child["parent_id"] == "dt_2"


def test_llm_analyzer_warns_when_node_count_too_high(caplog):
    nodes = [
        {"id": "dt_1", "type": "root", "content": "根节点", "parent_id": None, "risk_level": "medium"},
    ]
    for i in range(2, 43):
        nodes.append(
            {
                "id": f"dt_{i}",
                "type": "branch",
                "content": f"分支{i}",
                "parent_id": "dt_1",
                "risk_level": "low",
            }
        )

    fake_llm = _FakeLLMClient(json_result={"decision_tree": {"nodes": nodes}})
    provider = LLMAnalyzerProvider(llm_client=fake_llm)

    with caplog.at_level("WARNING"):
        provider.analyze(
            image_path=None,
            title="超大流程",
            description="用于触发节点过多日志。",
        )

    assert "节点数过多，可能存在冗余" in caplog.text


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
    assert analyze_data["llm_provider"] is None
    assert "流程图" in analyze_data["decision_tree"]["nodes"][0]["content"]


def test_architecture_api_passes_absolute_image_path_to_provider(monkeypatch):
    class _CapturePathProvider:
        def __init__(self):
            self.received_image_path = None

        def analyze(self, image_path, description, title=None):
            self.received_image_path = image_path
            return {
                "decision_tree": {
                    "nodes": [
                        {
                            "id": "dt_1",
                            "type": "root",
                            "content": "test",
                            "parent_id": None,
                            "risk_level": "medium",
                        }
                    ]
                },
                "test_plan": None,
                "risk_points": [],
                "test_cases": [],
            }

        @staticmethod
        def get_analysis_mode():
            return "llm"

        @staticmethod
        def get_llm_provider():
            return "openai"

    provider = _CapturePathProvider()
    monkeypatch.setattr("app.api.architecture.get_analyzer_provider", lambda: provider)

    project_resp = client.post("/api/projects", json={"name": "arch-p1-abs-path", "description": "architecture"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    analyze_resp = client.post(
        "/api/ai/architecture/analyze",
        data={
            "project_id": str(project_id),
            "title": "图片路径传参",
            "description_text": "文本补充",
        },
        files={"image": ("payment_flow.png", io.BytesIO(b"fake-image-content"), "image/png")},
    )

    assert analyze_resp.status_code == 201
    assert provider.received_image_path is not None
    assert os.path.isabs(provider.received_image_path)
    assert os.path.exists(provider.received_image_path)


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
    assert len(analyze_data["decision_tree"]["nodes"]) > 0
    assert analyze_data["test_cases"] == []

    get_resp = client.get(f"/api/ai/architecture/{analysis_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == analysis_id
    assert get_resp.json()["result"]["analysis_mode"] == "mock"

    import_resp = client.post(
        f"/api/ai/architecture/{analysis_id}/import",
        json={
            "import_decision_tree": True,
        },
    )
    assert import_resp.status_code == 200
    import_data = import_resp.json()
    assert import_data["imported_rule_nodes"] > 0
    assert import_data["requirement_id"] is not None

    tree_resp = client.get(f"/api/rules/requirements/{import_data['requirement_id']}/tree")
    assert tree_resp.status_code == 200
    assert len(tree_resp.json()["nodes"]) > 0


def test_architecture_api_rejects_invalid_requirement_id(monkeypatch):
    monkeypatch.setenv("ANALYZER_PROVIDER", "mock")
    project_resp = client.post("/api/projects", json={"name": "arch-p-invalid-reqid", "description": "architecture"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    analyze_resp = client.post(
        "/api/ai/architecture/analyze",
        data={
            "project_id": str(project_id),
            "requirement_id": "bad",
            "title": "无效需求ID",
            "description_text": "用户提交提现申请。",
        },
    )
    assert analyze_resp.status_code == 400
    assert "requirement_id" in analyze_resp.json()["detail"]


def test_architecture_api_rejects_requirement_from_other_project(monkeypatch):
    monkeypatch.setenv("ANALYZER_PROVIDER", "mock")
    project_a = client.post("/api/projects", json={"name": "arch-p-owner-a", "description": "architecture"})
    project_b = client.post("/api/projects", json={"name": "arch-p-owner-b", "description": "architecture"})
    assert project_a.status_code == 201
    assert project_b.status_code == 201
    project_a_id = project_a.json()["id"]
    project_b_id = project_b.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_b_id}/requirements",
        json={"title": "B需求", "raw_text": "demo", "source_type": "prd"},
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    analyze_resp = client.post(
        "/api/ai/architecture/analyze",
        data={
            "project_id": str(project_a_id),
            "requirement_id": str(requirement_id),
            "title": "跨项目需求引用",
            "description_text": "用户提交提现申请。",
        },
    )
    assert analyze_resp.status_code == 400
    assert "project" in analyze_resp.json()["detail"].lower()


def test_architecture_import_registers_raw_requirement_input(monkeypatch):
    monkeypatch.setenv("ANALYZER_PROVIDER", "mock")
    project_resp = client.post("/api/projects", json={"name": "arch-p2", "description": "architecture"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    description_text = "用户发起退款申请，系统校验订单状态并决定是否进入退款流程。"
    analyze_resp = client.post(
        "/api/ai/architecture/analyze",
        data={
            "project_id": str(project_id),
            "title": "退款需求拆解",
            "description_text": description_text,
        },
    )
    assert analyze_resp.status_code == 201
    analysis_id = analyze_resp.json()["id"]

    import_resp = client.post(
        f"/api/ai/architecture/{analysis_id}/import",
        json={"import_decision_tree": False},
    )
    assert import_resp.status_code == 200
    requirement_id = import_resp.json()["requirement_id"]

    db = SessionLocal()
    try:
        inputs = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == requirement_id)
            .all()
        )
        assert len(inputs) == 1
        assert inputs[0].input_type == InputType.raw_requirement
        assert inputs[0].content == description_text
    finally:
        db.close()


def test_architecture_import_is_idempotent_for_same_analysis(monkeypatch):
    monkeypatch.setenv("ANALYZER_PROVIDER", "mock")
    project_resp = client.post("/api/projects", json={"name": "arch-p3", "description": "architecture"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    analyze_resp = client.post(
        "/api/ai/architecture/analyze",
        data={
            "project_id": str(project_id),
            "title": "重复导入拆解",
            "description_text": "用户提交提现申请。如果未实名认证则拒绝。",
        },
    )
    assert analyze_resp.status_code == 201
    analysis_id = analyze_resp.json()["id"]

    first_import = client.post(
        f"/api/ai/architecture/{analysis_id}/import",
        json={"import_decision_tree": True},
    )
    assert first_import.status_code == 200
    requirement_id = first_import.json()["requirement_id"]

    first_tree = client.get(f"/api/rules/requirements/{requirement_id}/tree")
    assert first_tree.status_code == 200
    first_node_count = len(first_tree.json()["nodes"])
    assert first_node_count > 0

    second_import = client.post(
        f"/api/ai/architecture/{analysis_id}/import",
        json={"import_decision_tree": True},
    )
    assert second_import.status_code == 200
    assert second_import.json()["imported_rule_nodes"] == 0

    second_tree = client.get(f"/api/rules/requirements/{requirement_id}/tree")
    assert second_tree.status_code == 200
    assert len(second_tree.json()["nodes"]) == first_node_count
