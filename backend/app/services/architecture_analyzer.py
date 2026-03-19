import os
import re
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.architecture import ArchitectureAnalysisResult
from app.services.llm_client import LLMClient
from app.services.llm_result_helpers import build_llm_failure_meta, build_llm_success_meta
from app.services.prompts.architecture import (
    GENERATE_SYSTEM_PROMPT,
    GENERATE_USER_TEMPLATE,
    VISION_SYSTEM_PROMPT,
    VISION_USER_TEMPLATE,
)
from app.services.rule_engine import derive_rule_paths

logger = logging.getLogger(__name__)


class ArchitectureAnalyzerProvider:
    """Abstract provider for architecture analysis engines."""

    def __init__(self):
        self._analysis_mode = "mock"
        self._llm_provider: Optional[str] = None

    def analyze(self, image_path: Optional[str], description: str, title: Optional[str] = None) -> Dict:
        raise NotImplementedError

    def get_analysis_mode(self) -> str:
        return self._analysis_mode

    def get_llm_provider(self) -> Optional[str]:
        return self._llm_provider


class MockAnalyzerProvider(ArchitectureAnalyzerProvider):
    """Rule/template based analyzer used before integrating real LLM providers."""

    def analyze(self, image_path: Optional[str], description: str, title: Optional[str] = None) -> Dict:
        self._analysis_mode = "mock"
        self._llm_provider = None
        cleaned_description = _compose_analysis_description(description=description, image_path=image_path)
        sentences = _split_sentences(cleaned_description)

        decision_tree = _build_decision_tree(sentences)
        return _decision_tree_only_result({"decision_tree": decision_tree})


class LLMAnalyzerProvider(ArchitectureAnalyzerProvider):
    """LLM-based analyzer with a two-stage multimodal strategy."""

    def __init__(self, llm_client=None):
        super().__init__()
        self.llm = llm_client

    def analyze(self, image_path: Optional[str], description: str, title: Optional[str] = None) -> Dict:
        normalized_desc = (description or "").strip()
        normalized_title = (title or "").strip()
        stage = "init"
        self._llm_provider = None

        try:
            architecture_understanding = normalized_desc
            if image_path:
                stage = "vision"
                architecture_understanding = self._vision_analyze(image_path=image_path, description=normalized_desc)

            stage = "generate"
            generated = self._generate_artifacts(
                architecture_understanding=architecture_understanding,
                description=normalized_desc,
                title=normalized_title,
            )
            stage = "validate"
            validated = self._validate_payload(
                generated,
                title=normalized_title,
            )
            self._analysis_mode = "llm"
            return {
                **_decision_tree_only_result(validated),
                **build_llm_success_meta(self._llm_provider),
            }
        except Exception:
            logger.exception(
                "LLM analyze failed at stage=%s, returning empty result (title=%s, has_image=%s, desc_len=%d)",
                stage,
                normalized_title or "<empty>",
                bool(image_path),
                len(normalized_desc),
            )
            self._analysis_mode = "llm_failed"
            self._llm_provider = None
            return _empty_architecture_result()

    def _get_llm(self):
        if self.llm is None:
            self.llm = LLMClient()
        return self.llm

    def _vision_analyze(self, image_path: str, description: str) -> str:
        llm = self._get_llm()
        image_url = llm.image_to_base64_url(image_path)
        user_prompt = VISION_USER_TEMPLATE.format(description=description or "无")
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        understanding = llm.chat_with_vision(system_prompt=VISION_SYSTEM_PROMPT, user_content=user_content)
        self._llm_provider = self._resolve_provider_from_llm(llm, "chat_with_vision") or self._llm_provider
        return (understanding or description or "")[:4000]

    def _generate_artifacts(self, architecture_understanding: str, description: str, title: str) -> Dict:
        llm = self._get_llm()
        user_prompt = GENERATE_USER_TEMPLATE.format(
            title=title or "未命名架构分析",
            description=description or "无补充文字描述",
            architecture_understanding=architecture_understanding or "无架构理解",
        )
        try:
            return llm.chat_with_json(system_prompt=GENERATE_SYSTEM_PROMPT, user_prompt=user_prompt)
        finally:
            self._llm_provider = self._resolve_provider_from_llm(llm, "chat_with_json") or self._llm_provider

    @staticmethod
    def _resolve_provider_from_llm(llm: Any, method_name: str) -> Optional[str]:
        getter = getattr(llm, "get_last_provider", None)
        if not callable(getter):
            return None
        provider = getter(method_name=method_name)
        if provider:
            return str(provider).strip().lower()
        return None

    def _validate_payload(
        self,
        payload: Dict,
        title: str,
    ) -> Dict:
        payload_summary = _summarize_payload_structure(payload)
        try:
            validated = ArchitectureAnalysisResult.parse_obj(payload).dict()
            _validate_related_node_ids(validated)
            return _post_process_decision_tree(validated, title=title)
        except Exception as exc:
            try:
                normalized_payload = _normalize_llm_payload(payload)
                normalized = ArchitectureAnalysisResult.parse_obj(normalized_payload).dict()
                _validate_related_node_ids(normalized)
                logger.info(
                    "LLM payload normalized and accepted (title=%s, payload_summary=%s)",
                    (title or "").strip() or "<empty>",
                    payload_summary,
                )
                return _post_process_decision_tree(normalized, title=title)
            except Exception as normalize_exc:
                raise ValueError(
                    "LLM payload invalid ({0}, raw_error={1}, normalize_error={2})".format(
                        payload_summary,
                        exc,
                        normalize_exc,
                    )
                )


def get_analyzer_provider() -> ArchitectureAnalyzerProvider:
    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider == "llm":
        return LLMAnalyzerProvider()
    return MockAnalyzerProvider()


def _compose_analysis_description(description: str, image_path: Optional[str]) -> str:
    text = (description or "").strip()
    image_hint = _extract_image_hint(image_path)
    if text and image_hint:
        return "{0}。流程图参考信息：{1}".format(text, image_hint)
    if text:
        return text
    if image_hint:
        return "流程图参考信息：{0}".format(image_hint)
    return ""


def _extract_image_hint(image_path: Optional[str]) -> str:
    if not image_path:
        return ""

    filename = os.path.basename(image_path).strip()
    if not filename:
        return "已上传流程图"

    stem = os.path.splitext(filename)[0]
    normalized = re.sub(r"[_\-]+", " ", stem).strip()
    return normalized or filename


def _empty_architecture_result() -> Dict:
    return {
        "decision_tree": {"nodes": []},
        "test_plan": None,
        "risk_points": [],
        "test_cases": [],
        **build_llm_failure_meta(),
    }


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


def _normalize_llm_payload(payload: Any) -> Dict:
    if not isinstance(payload, dict):
        raise ValueError("LLM payload must be object to normalize")

    normalized_payload = _unwrap_payload_envelope(payload)
    if not _has_artifact_signal(normalized_payload):
        raise ValueError("LLM payload missing recognizable artifact fields")

    decision_tree = _pick_payload_value(normalized_payload, ["decision_tree", "decisionTree", "tree", "rule_tree"])
    nodes = _normalize_decision_tree_nodes(_extract_items(decision_tree, ["nodes", "items", "list", "children"]))
    return _decision_tree_only_result({
        "decision_tree": {"nodes": nodes},
    })


def _unwrap_payload_envelope(payload: Dict[str, Any]) -> Dict[str, Any]:
    current: Any = payload
    for _ in range(3):
        if not isinstance(current, dict):
            break
        if _has_artifact_signal(current):
            return current

        wrapped = _pick_payload_value(current, ["data", "result", "output", "analysis", "payload", "response"])
        if isinstance(wrapped, dict):
            current = wrapped
            continue
        break
    return payload


def _has_artifact_signal(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in payload.keys():
        normalized = _normalize_key_name(key)
        if normalized in {
            "decisiontree",
            "tree",
            "ruletree",
        }:
            return True
    return False


def _decision_tree_only_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    tree = payload.get("decision_tree", {}) if isinstance(payload, dict) else {}
    nodes = tree.get("nodes", []) if isinstance(tree, dict) else []
    return {
        "decision_tree": {"nodes": nodes},
        "test_plan": None,
        "risk_points": [],
        "test_cases": [],
    }


def _post_process_decision_tree(payload: Dict[str, Any], title: str) -> Dict[str, Any]:
    result = _decision_tree_only_result(payload)
    raw_nodes = result.get("decision_tree", {}).get("nodes", [])
    dedup_nodes, removed_count = _deduplicate_sibling_nodes(raw_nodes)
    result["decision_tree"]["nodes"] = dedup_nodes

    if removed_count > 0:
        logger.info(
            "Decision tree deduplicated (%d -> %d, removed=%d, title=%s)",
            len(raw_nodes),
            len(dedup_nodes),
            removed_count,
            (title or "").strip() or "<empty>",
        )
    _log_node_count_warning(len(dedup_nodes), title=title)
    return result


def _deduplicate_sibling_nodes(nodes: Any) -> Tuple[List[Dict], int]:
    if not isinstance(nodes, list):
        return [], 0

    deduped: List[Dict] = []
    replaced_ids: Dict[str, str] = {}
    seen_key_to_id: Dict[Tuple[Optional[str], str, str], str] = {}

    for raw in nodes:
        if not isinstance(raw, dict):
            continue

        node = dict(raw)
        node_id = _coerce_text(node.get("id"))
        if not node_id:
            continue

        parent_id = _coerce_text(node.get("parent_id")) or None
        if parent_id in replaced_ids:
            parent_id = replaced_ids[parent_id]
        node["parent_id"] = parent_id

        dedup_key = (
            parent_id,
            _coerce_text(node.get("type")).lower(),
            _normalize_node_content_for_dedup(node.get("content")),
        )
        kept_id = seen_key_to_id.get(dedup_key)
        if kept_id and kept_id != node_id:
            replaced_ids[node_id] = kept_id
            continue

        seen_key_to_id[dedup_key] = node_id
        deduped.append(node)

    if not deduped:
        return [], 0

    deduped_ids = {node.get("id") for node in deduped}
    root_id = _coerce_text(deduped[0].get("id"))
    for index, node in enumerate(deduped):
        node_id = _coerce_text(node.get("id"))
        parent_id = _coerce_text(node.get("parent_id")) or None
        if parent_id in replaced_ids:
            parent_id = replaced_ids[parent_id]

        if index == 0:
            node["type"] = "root"
            node["parent_id"] = None
            continue

        if not parent_id or parent_id not in deduped_ids or parent_id == node_id:
            node["parent_id"] = root_id
        else:
            node["parent_id"] = parent_id

    return deduped, max(len(nodes) - len(deduped), 0)


def _normalize_node_content_for_dedup(value: Any) -> str:
    text = _coerce_text(value).lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。,.；;:：!?！？]", "", text)
    return text


def _log_node_count_warning(node_count: int, title: str) -> None:
    title_text = (title or "").strip() or "<empty>"
    if node_count < 15:
        logger.warning("节点数过少，可能粒度太粗 (count=%d, title=%s)", node_count, title_text)
        return
    if node_count > 40:
        logger.warning("节点数过多，可能存在冗余 (count=%d, title=%s)", node_count, title_text)


def _pick_payload_value(payload: Any, candidate_keys: List[str]) -> Any:
    if not isinstance(payload, dict):
        return None

    for key in candidate_keys:
        if key in payload:
            return payload.get(key)

    normalized_candidates = {_normalize_key_name(key): key for key in candidate_keys}
    for key, value in payload.items():
        if _normalize_key_name(key) in normalized_candidates:
            return value
    return None


def _normalize_key_name(value: Any) -> str:
    text = _coerce_text(value)
    if not text:
        return ""
    return re.sub(r"[\s_\-]+", "", text).lower()


def _extract_items(raw_value: Any, list_keys: List[str]) -> List[Any]:
    if isinstance(raw_value, list):
        return raw_value
    if isinstance(raw_value, dict):
        nested = _pick_payload_value(raw_value, list_keys)
        if isinstance(nested, list):
            return nested
        if nested is not None:
            return [nested]
    return []


def _normalize_decision_tree_nodes(raw_nodes: Any) -> List[Dict]:
    nodes: List[Dict] = []
    used_ids: Set[str] = set()
    items = raw_nodes if isinstance(raw_nodes, list) else []

    for item in items:
        node = item if isinstance(item, dict) else {"content": _coerce_text(item)}
        node_id = _coerce_text(_pick_payload_value(node, ["id", "node_id", "nodeId", "key"]))
        if not node_id or node_id in used_ids:
            node_id = "dt_{0}".format(len(nodes) + 1)

        node_type = _normalize_node_type(_pick_payload_value(node, ["type", "node_type", "nodeType"]), is_first=len(nodes) == 0)
        content = (
            _coerce_text(_pick_payload_value(node, ["content", "text", "name", "title", "label", "description"]))
            or "节点{0}".format(len(nodes) + 1)
        )
        risk_level = _normalize_risk_level(_pick_payload_value(node, ["risk_level", "risk", "severity", "level"]))
        parent_id = _coerce_text(_pick_payload_value(node, ["parent_id", "parentId", "parent"])) or None

        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "content": content,
                "parent_id": parent_id,
                "risk_level": risk_level,
            }
        )
        used_ids.add(node_id)

    if not nodes:
        return [
            {
                "id": "dt_1",
                "type": "root",
                "content": "待补充系统流程描述",
                "parent_id": None,
                "risk_level": "medium",
            }
        ]

    node_ids = {node["id"] for node in nodes}
    root_id = nodes[0]["id"]
    for index, node in enumerate(nodes):
        if index == 0:
            node["type"] = "root"
            node["parent_id"] = None
            continue

        if node.get("parent_id") not in node_ids or node.get("parent_id") == node["id"]:
            node["parent_id"] = root_id

    return nodes


def _normalize_sections(raw_sections: Any) -> List[str]:
    if isinstance(raw_sections, str):
        raw_sections = [part for part in re.split(r"[,，\s]+", raw_sections) if part]
    elif not isinstance(raw_sections, list):
        return []

    sections: List[str] = []
    for item in raw_sections:
        if isinstance(item, dict):
            value = (
                item.get("name")
                or item.get("id")
                or item.get("title")
                or item.get("section")
                or item.get("value")
            )
        else:
            value = item

        text = _coerce_text(value)
        if text and text not in sections:
            sections.append(text)
    return sections


def _normalize_risk_points(raw_risks: Any, node_ids: Set[str], default_node_id: Optional[str]) -> List[Dict]:
    raw_risks = _extract_items(raw_risks, ["items", "risk_points", "risks", "list", "data"])
    if not raw_risks:
        return []

    normalized: List[Dict] = []
    for index, item in enumerate(raw_risks, start=1):
        risk = item if isinstance(item, dict) else {"description": _coerce_text(item)}
        risk_id = _coerce_text(_pick_payload_value(risk, ["id", "risk_id", "riskId"])) or "rp_{0}".format(index)
        description = (
            _coerce_text(_pick_payload_value(risk, ["description", "content", "text", "name", "title"]))
            or "风险点{0}".format(index)
        )
        severity = _normalize_risk_level(_pick_payload_value(risk, ["severity", "risk_level", "risk", "level"]))
        mitigation = _coerce_text(_pick_payload_value(risk, ["mitigation", "suggestion", "advice", "action"])) or "补充边界条件用例并加入告警/重试保护。"
        related_node_ids = _normalize_related_node_ids(
            _pick_payload_value(risk, ["related_node_ids", "node_ids", "nodeIds", "relatedNodes"]),
            node_ids=node_ids,
            default_node_id=default_node_id,
        )

        normalized.append(
            {
                "id": risk_id,
                "description": description,
                "severity": severity,
                "mitigation": mitigation,
                "related_node_ids": related_node_ids,
            }
        )
    return normalized


def _normalize_test_cases(raw_cases: Any, node_ids: Set[str], default_node_id: Optional[str], title: str) -> List[Dict]:
    normalized: List[Dict] = []
    raw_cases = _extract_items(raw_cases, ["items", "test_cases", "cases", "list", "data"])
    if raw_cases:
        for index, item in enumerate(raw_cases, start=1):
            case = item if isinstance(item, dict) else {"title": _coerce_text(item)}
            case_title = _coerce_text(_pick_payload_value(case, ["title", "name", "case_name"])) or "{0}-用例{1}".format((title or "架构分析").strip(), index)
            steps = _coerce_multiline_text(_pick_payload_value(case, ["steps", "step", "actions", "procedure"])) or "待补充执行步骤"
            expected_result = (
                _coerce_text(_pick_payload_value(case, ["expected_result", "expected", "result", "assertion"]))
                or "行为符合预期"
            )
            risk_level = _normalize_risk_level(_pick_payload_value(case, ["risk_level", "risk", "severity", "level"]))
            related_node_ids = _normalize_related_node_ids(
                _pick_payload_value(case, ["related_node_ids", "node_ids", "nodeIds", "relatedNodes"]),
                node_ids=node_ids,
                default_node_id=default_node_id,
            )

            normalized.append(
                {
                    "title": case_title,
                    "steps": steps,
                    "expected_result": expected_result,
                    "risk_level": risk_level,
                    "related_node_ids": related_node_ids,
                }
            )

    if not normalized and default_node_id:
        normalized.append(
            {
                "title": "{0}-默认用例".format((title or "架构分析").strip()),
                "steps": "验证关键流程节点",
                "expected_result": "流程行为符合预期",
                "risk_level": "medium",
                "related_node_ids": [default_node_id],
            }
        )
    return normalized


def _normalize_related_node_ids(raw_related_ids: Any, node_ids: Set[str], default_node_id: Optional[str]) -> List[str]:
    values: List[Any] = []
    if isinstance(raw_related_ids, list):
        values = raw_related_ids
    elif isinstance(raw_related_ids, tuple):
        values = list(raw_related_ids)
    elif isinstance(raw_related_ids, str):
        values = [part for part in re.split(r"[,，\s]+", raw_related_ids) if part]
    elif raw_related_ids is not None:
        values = [raw_related_ids]

    normalized: List[str] = []
    for item in values:
        node_id = _coerce_text(item)
        if node_id and node_id in node_ids and node_id not in normalized:
            normalized.append(node_id)

    if not normalized and default_node_id and default_node_id in node_ids:
        normalized.append(default_node_id)
    return normalized


def _normalize_node_type(value: Any, is_first: bool) -> str:
    if isinstance(value, dict):
        value = _pick_payload_value(value, ["type", "node_type", "nodeType", "value", "name"])
    normalized = _coerce_text(value).lower()
    mapping = {
        "root": "root",
        "condition": "condition",
        "branch": "branch",
        "action": "action",
        "exception": "exception",
        "根节点": "root",
        "根": "root",
        "条件": "condition",
        "分支": "branch",
        "动作": "action",
        "行为": "action",
        "异常": "exception",
    }
    if normalized in mapping:
        return mapping[normalized]
    return "root" if is_first else "branch"


def _normalize_risk_level(value: Any) -> str:
    if isinstance(value, dict):
        value = _pick_payload_value(value, ["risk_level", "risk", "severity", "level", "value"])
    normalized = _coerce_text(value).lower()
    if not normalized:
        return "medium"

    mapping = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "严重": "critical",
        "高": "high",
        "中": "medium",
        "中等": "medium",
        "一般": "medium",
        "低": "low",
        "major": "high",
        "minor": "low",
    }
    if normalized in mapping:
        return mapping[normalized]
    if "critical" in normalized or "严重" in normalized:
        return "critical"
    if "high" in normalized or "高" in normalized:
        return "high"
    if "low" in normalized or "低" in normalized:
        return "low"
    return "medium"


def _coerce_multiline_text(value: Any) -> str:
    if isinstance(value, list):
        lines = [_coerce_text(item) for item in value]
        lines = [line for line in lines if line]
        return "\n".join(lines)
    return _coerce_text(value)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ["text", "content", "value", "name", "title", "label", "description"]:
            text = _coerce_text(value.get(key))
            if text:
                return text
        return str(value).strip()
    if isinstance(value, list):
        parts = [_coerce_text(item) for item in value]
        parts = [part for part in parts if part]
        return " ".join(parts)
    return str(value).strip()


def _summarize_payload_structure(payload: Any) -> str:
    if isinstance(payload, dict):
        items: List[str] = []
        for key, value in list(payload.items())[:8]:
            items.append("{0}:{1}".format(key, _payload_value_shape(value)))
        if len(payload) > 8:
            items.append("...+{0}".format(len(payload) - 8))
        return "dict({0})".format(", ".join(items))
    return "payload_type={0}".format(type(payload).__name__)


def _payload_value_shape(value: Any) -> str:
    if isinstance(value, dict):
        return "dict[{0}]".format(len(value))
    if isinstance(value, list):
        return "list[{0}]".format(len(value))
    if isinstance(value, str):
        return "str[{0}]".format(len(value))
    return type(value).__name__


def _validate_related_node_ids(payload: Dict) -> None:
    node_ids = {node.get("id") for node in payload.get("decision_tree", {}).get("nodes", [])}
    node_ids.discard(None)

    for risk in payload.get("risk_points", []):
        for node_id in risk.get("related_node_ids", []):
            if node_id not in node_ids:
                raise ValueError("risk_points.related_node_ids contains unknown node id")

    for test_case in payload.get("test_cases", []):
        for node_id in test_case.get("related_node_ids", []):
            if node_id not in node_ids:
                raise ValueError("test_cases.related_node_ids contains unknown node id")
