import os
import re
from typing import Dict, List, Optional

from app.services.rule_engine import derive_rule_paths


class ArchitectureAnalyzerProvider:
    """Abstract provider for architecture analysis engines."""

    def analyze(self, image_path: Optional[str], description: str, title: Optional[str] = None) -> Dict:
        raise NotImplementedError


class MockAnalyzerProvider(ArchitectureAnalyzerProvider):
    """Rule/template based analyzer used before integrating real LLM providers."""

    def analyze(self, image_path: Optional[str], description: str, title: Optional[str] = None) -> Dict:
        cleaned_description = (description or "").strip()
        cleaned_title = (title or "").strip()
        sentences = _split_sentences(cleaned_description)

        decision_tree = _build_decision_tree(sentences)
        test_plan = _build_test_plan(cleaned_description, decision_tree["nodes"])
        risk_points = _build_risk_points(decision_tree["nodes"])
        test_cases = _build_generated_cases(decision_tree["nodes"], analysis_title=cleaned_title)

        return {
            "decision_tree": decision_tree,
            "test_plan": test_plan,
            "risk_points": risk_points,
            "test_cases": test_cases,
        }


class LLMAnalyzerProvider(ArchitectureAnalyzerProvider):
    """Placeholder for future LLM analyzer integration."""

    def analyze(self, image_path: Optional[str], description: str, title: Optional[str] = None) -> Dict:
        return MockAnalyzerProvider().analyze(image_path=image_path, description=description, title=title)


def get_analyzer_provider() -> ArchitectureAnalyzerProvider:
    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider == "llm":
        return LLMAnalyzerProvider()
    return MockAnalyzerProvider()


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"[。！？!?;；\n]+", text)
    return [part.strip(" ，,\t") for part in parts if part and part.strip(" ，,\t")]


def _build_decision_tree(sentences: List[str]) -> Dict:
    if not sentences:
        return {
            "nodes": [
                {
                    "id": "dt_1",
                    "type": "root",
                    "content": "待补充系统流程描述",
                    "parent_id": None,
                    "risk_level": "medium",
                }
            ]
        }

    nodes = []
    node_index = 1
    root_id = "dt_{0}".format(node_index)
    root_content = sentences[0]
    nodes.append(
        {
            "id": root_id,
            "type": "root",
            "content": root_content,
            "parent_id": None,
            "risk_level": _content_to_risk(root_content),
        }
    )

    for sentence in sentences[1:]:
        sentence = sentence.strip()
        if not sentence:
            continue

        condition_text, action_text = _split_condition_action(sentence)

        node_index += 1
        cond_id = "dt_{0}".format(node_index)
        cond_type = "condition" if _looks_like_condition(condition_text) else "branch"
        nodes.append(
            {
                "id": cond_id,
                "type": cond_type,
                "content": condition_text,
                "parent_id": root_id,
                "risk_level": _content_to_risk(condition_text),
            }
        )

        if action_text:
            node_index += 1
            action_id = "dt_{0}".format(node_index)
            action_type = "exception" if _is_exception_text(action_text) else "action"
            nodes.append(
                {
                    "id": action_id,
                    "type": action_type,
                    "content": action_text,
                    "parent_id": cond_id,
                    "risk_level": _content_to_risk(action_text),
                }
            )

    return {"nodes": nodes}


def _build_test_plan(description: str, nodes: List[Dict]) -> Dict:
    scope = description[:120] if description else "基于上传流程图与描述的系统流程"
    markdown = "\n".join(
        [
            "# AI 生成测试方案",
            "## 1. 测试范围",
            "- {0}".format(scope),
            "- 规则节点总数: {0}".format(len(nodes)),
            "## 2. 测试策略",
            "- 覆盖主流程、分支流程、异常路径",
            "- 重点关注高风险节点与未覆盖路径",
            "## 3. 环境要求",
            "- 具备可模拟外部依赖异常（超时/失败）能力",
            "- 提供基础测试数据与权限账号",
            "## 4. 进度安排",
            "- D1-D2: 规则确认与用例补齐",
            "- D3: 冒烟 + 主链路回归",
            "## 5. 退出标准",
            "- critical/high 风险节点全部有用例覆盖",
            "- 主流程与核心异常流程执行通过",
        ]
    )

    return {
        "markdown": markdown,
        "sections": ["scope", "strategy", "environment", "schedule", "exit_criteria"],
    }


def _build_risk_points(nodes: List[Dict]) -> List[Dict]:
    risk_points = []
    risk_idx = 1
    for node in nodes:
        severity = node.get("risk_level", "medium")
        if severity not in ["critical", "high"]:
            continue

        mitigation = "补充边界条件用例并加入告警/重试保护。"
        if severity == "critical":
            mitigation = "增加重试、超时阈值和故障回退策略，并纳入发布前阻断检查。"

        risk_points.append(
            {
                "id": "rp_{0}".format(risk_idx),
                "description": "节点“{0}”存在{1}风险。".format(node.get("content", ""), severity),
                "severity": severity,
                "mitigation": mitigation,
                "related_node_ids": [node["id"]],
            }
        )
        risk_idx += 1

    return risk_points


def _build_generated_cases(nodes: List[Dict], analysis_title: Optional[str] = None) -> List[Dict]:
    node_payload = [{"id": n["id"], "parent_id": n.get("parent_id")} for n in nodes]
    paths = derive_rule_paths(node_payload)
    node_map = {n["id"]: n for n in nodes}
    title_prefix = (analysis_title or "").strip()

    cases = []
    for index, path in enumerate(paths, start=1):
        contents = [node_map[node_id]["content"] for node_id in path if node_id in node_map]
        steps = " -> ".join(contents)
        risk_level = _path_risk_level([node_map[node_id].get("risk_level", "medium") for node_id in path])
        case_title = "架构路径用例 {0}".format(index)
        if title_prefix:
            case_title = "{0}-路径用例{1}".format(title_prefix, index)

        cases.append(
            {
                "title": case_title,
                "steps": "依次验证: {0}".format(steps),
                "expected_result": "路径节点行为符合预期，无阻断性异常",
                "risk_level": risk_level,
                "related_node_ids": path,
            }
        )

    if not cases and nodes:
        root = nodes[0]
        root_title = "架构根节点验证"
        if title_prefix:
            root_title = "{0}-根节点验证".format(title_prefix)
        cases.append(
            {
                "title": root_title,
                "steps": "验证根流程: {0}".format(root.get("content", "")),
                "expected_result": "根流程可执行",
                "risk_level": root.get("risk_level", "medium"),
                "related_node_ids": [root["id"]],
            }
        )

    return cases


def _split_condition_action(sentence: str):
    for token in ["则", "那么", "->", "，"]:
        if token in sentence:
            parts = sentence.split(token, 1)
            condition = parts[0].strip()
            action = parts[1].strip()
            if condition and action:
                return condition, action
    return sentence, ""


def _looks_like_condition(text: str) -> bool:
    keywords = ["如果", "当", "若", "是否", "检查", "校验"]
    return any(word in text for word in keywords)


def _is_exception_text(text: str) -> bool:
    return any(word in text for word in ["异常", "失败", "超时", "错误", "拒绝"])


def _content_to_risk(content: str) -> str:
    critical_keywords = ["资金", "转账", "并发", "安全", "权限", "超时"]
    high_keywords = ["失败", "异常", "错误", "拒绝", "重试"]

    if any(word in content for word in critical_keywords):
        return "critical"
    if any(word in content for word in high_keywords):
        return "high"
    if any(word in content for word in ["检查", "校验", "不足"]):
        return "medium"
    return "low"


def _path_risk_level(risk_levels: List[str]) -> str:
    weight = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    if not risk_levels:
        return "medium"
    return sorted(risk_levels, key=lambda level: weight.get(level, 0), reverse=True)[0]
