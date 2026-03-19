from typing import List
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.testcase_importer import ParsedTestCase
from app.services.testcase_matcher import MatchResult


client = TestClient(app)


def _create_project_and_requirement(name_prefix: str):
    project_resp = client.post(
        "/api/projects",
        json={"name": "{0}-{1}".format(name_prefix, uuid4().hex[:8]), "description": "import test"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        "/api/projects/{0}/requirements".format(project_id),
        json={"title": "导入需求", "raw_text": "导入校验", "source_type": "prd"},
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]
    return project_id, requirement_id


def _create_rule_nodes(requirement_id: int):
    root_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": None,
            "node_type": "root",
            "content": "登录流程",
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
            "content": "账号密码正确",
            "risk_level": "medium",
        },
    )
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    tree_resp = client.get("/api/rules/requirements/{0}/tree".format(requirement_id))
    assert tree_resp.status_code == 200
    paths = tree_resp.json()["paths"]
    assert len(paths) >= 1
    return root_id, child_id, paths


def test_parse_import_returns_preview(monkeypatch):
    import app.api.testcase_import as testcase_import_api

    project_id, requirement_id = _create_project_and_requirement("import-parse")
    root_id, _, _ = _create_rule_nodes(requirement_id)

    def fake_parse(_filename: str, _bytes: bytes) -> List[ParsedTestCase]:
        return [
            ParsedTestCase(
                title="登录成功",
                steps="输入正确账号密码",
                expected_result="进入首页",
                raw_text="登录成功 输入正确账号密码",
            )
        ]

    class _FakeMatcher:
        def match_cases(self, parsed_cases, rule_nodes):
            assert len(parsed_cases) == 1
            assert len(rule_nodes) >= 1
            return [
                MatchResult(case_index=0, matched_node_ids=[root_id], confidence="high", reason="命中登录主流程")
            ], "llm_failed"

        def get_llm_status(self):
            return "failed"

        def get_llm_message(self):
            return "所有模型调用失败，未生成结果。请稍后重试或检查模型配置。"

    monkeypatch.setattr(testcase_import_api, "parse_testcases_from_upload", fake_parse)
    monkeypatch.setattr(testcase_import_api, "TestCaseMatcher", lambda: _FakeMatcher())

    resp = client.post(
        "/api/testcases/import/parse",
        data={"requirement_id": str(requirement_id)},
        files={"file": ("cases.xlsx", b"fake-content", "application/vnd.ms-excel")},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["analysis_mode"] == "llm_failed"
    assert payload["llm_status"] == "failed"
    assert "所有模型调用失败" in payload["llm_message"]
    assert payload["llm_provider"] is None
    assert payload["total_cases"] == 1
    assert payload["auto_matched"] == 1
    assert payload["parsed_cases"][0]["matched_node_ids"] == [root_id]
    assert payload["parsed_cases"][0]["matched_node_contents"][0] == "登录流程"
    assert payload["parsed_cases"][0]["suggested_risk_level"] == "high"
    assert project_id > 0


def test_parse_import_returns_llm_provider(monkeypatch):
    import app.api.testcase_import as testcase_import_api

    _, requirement_id = _create_project_and_requirement("import-parse-provider")
    root_id, _, _ = _create_rule_nodes(requirement_id)

    def fake_parse(_filename: str, _bytes: bytes) -> List[ParsedTestCase]:
        return [
            ParsedTestCase(
                title="登录成功",
                steps="输入正确账号密码",
                expected_result="进入首页",
                raw_text="登录成功 输入正确账号密码",
            )
        ]

    class _FakeMatcher:
        def match_cases(self, parsed_cases, rule_nodes):
            assert len(parsed_cases) == 1
            assert len(rule_nodes) >= 1
            return [
                MatchResult(case_index=0, matched_node_ids=[root_id], confidence="high", reason="命中登录主流程")
            ], "llm"

        def get_llm_provider(self):
            return "openai"

        def get_llm_status(self):
            return "success"

        def get_llm_message(self):
            return None

    monkeypatch.setattr(testcase_import_api, "parse_testcases_from_upload", fake_parse)
    monkeypatch.setattr(testcase_import_api, "TestCaseMatcher", lambda: _FakeMatcher())

    resp = client.post(
        "/api/testcases/import/parse",
        data={"requirement_id": str(requirement_id)},
        files={"file": ("cases.xlsx", b"fake-content", "application/vnd.ms-excel")},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["analysis_mode"] == "llm"
    assert payload["llm_provider"] == "openai"
    assert payload["llm_status"] == "success"


def test_confirm_import_success_and_skip():
    project_id, requirement_id = _create_project_and_requirement("import-confirm")
    root_id, child_id, paths = _create_rule_nodes(requirement_id)
    path_id = next(path["id"] for path in paths if root_id in path["node_sequence"] and child_id in path["node_sequence"])

    resp = client.post(
        "/api/testcases/import/confirm",
        json={
            "project_id": project_id,
            "requirement_id": requirement_id,
            "cases": [
                {
                    "title": "登录成功",
                    "steps": "输入账号密码",
                    "expected_result": "登录成功",
                    "risk_level": "medium",
                    "bound_rule_node_ids": [root_id, child_id],
                    "bound_path_ids": [path_id],
                },
                {
                    "title": "未处理用例",
                    "steps": "待补充",
                    "expected_result": "待补充",
                    "risk_level": "low",
                    "bound_rule_node_ids": [],
                    "bound_path_ids": [],
                    "skip_import": True,
                },
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported_count"] == 1
    assert body["bound_count"] == 1
    assert body["skipped_count"] == 1

    list_resp = client.get("/api/testcases/projects/{0}?requirement_id={1}".format(project_id, requirement_id))
    assert list_resp.status_code == 200
    imported_case = next(case for case in list_resp.json() if case["title"] == "登录成功")
    assert imported_case["risk_level"] == "high"


def test_confirm_import_rejects_invalid_project_requirement_relation():
    project_a, requirement_a = _create_project_and_requirement("import-rel-a")
    project_b, _ = _create_project_and_requirement("import-rel-b")
    root_id, _, _ = _create_rule_nodes(requirement_a)

    resp = client.post(
        "/api/testcases/import/confirm",
        json={
            "project_id": project_b,
            "requirement_id": requirement_a,
            "cases": [
                {
                    "title": "跨项目绑定",
                    "steps": "step",
                    "expected_result": "result",
                    "risk_level": "low",
                    "bound_rule_node_ids": [root_id],
                    "bound_path_ids": [],
                }
            ],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_project_requirement_relation"
    assert project_a > 0


def test_confirm_import_rejects_unbound_case():
    project_id, requirement_id = _create_project_and_requirement("import-unbound")

    resp = client.post(
        "/api/testcases/import/confirm",
        json={
            "project_id": project_id,
            "requirement_id": requirement_id,
            "cases": [
                {
                    "title": "未绑定",
                    "steps": "step",
                    "expected_result": "result",
                    "risk_level": "medium",
                    "bound_rule_node_ids": [],
                    "bound_path_ids": [],
                }
            ],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unbound_case_not_allowed"


def test_confirm_import_rejects_invalid_node_or_path_and_rolls_back():
    project_id, requirement_id = _create_project_and_requirement("import-invalid")
    root_id, child_id, paths = _create_rule_nodes(requirement_id)

    extra_node_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": root_id,
            "node_type": "action",
            "content": "发送短信通知",
            "risk_level": "low",
        },
    )
    assert extra_node_resp.status_code == 201
    extra_node_id = extra_node_resp.json()["id"]

    tree_resp = client.get("/api/rules/requirements/{0}/tree".format(requirement_id))
    assert tree_resp.status_code == 200
    paths = tree_resp.json()["paths"]
    valid_path_id = next(path["id"] for path in paths if root_id in path["node_sequence"] and child_id in path["node_sequence"])

    # 先试非法节点
    invalid_node_resp = client.post(
        "/api/testcases/import/confirm",
        json={
            "project_id": project_id,
            "requirement_id": requirement_id,
            "cases": [
                {
                    "title": "有效行",
                    "steps": "step",
                    "expected_result": "ok",
                    "risk_level": "high",
                    "bound_rule_node_ids": [root_id],
                    "bound_path_ids": [],
                },
                {
                    "title": "非法节点行",
                    "steps": "step",
                    "expected_result": "ok",
                    "risk_level": "high",
                    "bound_rule_node_ids": ["bad-node-id"],
                    "bound_path_ids": [],
                },
            ],
        },
    )
    assert invalid_node_resp.status_code == 400
    assert invalid_node_resp.json()["detail"] == "invalid_bound_rule_node_ids"

    # 再试路径不包含节点
    mismatch_resp = client.post(
        "/api/testcases/import/confirm",
        json={
            "project_id": project_id,
            "requirement_id": requirement_id,
            "cases": [
                {
                    "title": "路径不匹配",
                    "steps": "step",
                    "expected_result": "ok",
                    "risk_level": "high",
                    "bound_rule_node_ids": [extra_node_id],
                    "bound_path_ids": [valid_path_id],
                }
            ],
        },
    )
    assert mismatch_resp.status_code == 400
    assert mismatch_resp.json()["detail"] == "path_node_mismatch"

    invalid_path_resp = client.post(
        "/api/testcases/import/confirm",
        json={
            "project_id": project_id,
            "requirement_id": requirement_id,
            "cases": [
                {
                    "title": "非法路径",
                    "steps": "step",
                    "expected_result": "ok",
                    "risk_level": "high",
                    "bound_rule_node_ids": [root_id],
                    "bound_path_ids": ["bad-path-id"],
                }
            ],
        },
    )
    assert invalid_path_resp.status_code == 400
    assert invalid_path_resp.json()["detail"] == "invalid_bound_path_ids"

    list_resp = client.get("/api/testcases/projects/{0}?requirement_id={1}".format(project_id, requirement_id))
    assert list_resp.status_code == 200
    titles = [case["title"] for case in list_resp.json()]
    assert "有效行" not in titles
