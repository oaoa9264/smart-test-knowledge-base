import logging
import os
from typing import Any, Dict, List, Optional

from app.services.llm_client import LLMClient
from app.services.llm_result_helpers import build_llm_failure_meta, build_llm_success_meta
from app.services.prompts.risk_analysis import RISK_WRITING_GUIDE


logger = logging.getLogger(__name__)

AI_PARSE_SYSTEM_PROMPT = """
你是测试规则树助手。请把需求文本拆解为规则树草稿节点，并识别潜在风险。

只返回 JSON 对象，不要输出任何解释。格式如下：
{{
  "nodes": [
    {{"id":"temp_1","type":"root","content":"...","parent_id":null}},
    {{"id":"temp_2","type":"condition","content":"...","parent_id":"temp_1"}}
  ],
  "risks": [
    {{"id":"risk_1","related_node_id":"temp_2","category":"flow_gap","risk_level":"high","description":"...","suggestion":"..."}}
  ]
}}

nodes 约束：
1) type 只能是 root/condition/branch/action/exception。
2) 必须有且仅有 1 个 root，root 的 parent_id 为 null。
3) content 要简洁、可执行，避免空内容。
4) 节点总数建议 3-12 个，优先保留关键判断和关键动作。
5) parent_id 必须引用同一结果中的 id。

risks 约束：
1) id 使用 "risk_N" 格式；
2) related_node_id 引用 nodes 中已有 id，全局风险设为 null；
3) category 只能是 input_validation/flow_gap/data_integrity/boundary/security；
4) risk_level 只能是 critical/high/medium/low；
5) 风险项建议 2-6 个；
6) description 和 suggestion 必须严格遵循以下书写规范：

{risk_writing_guide}
""".strip().format(risk_writing_guide=RISK_WRITING_GUIDE)

AI_PARSE_USER_TEMPLATE = """
请拆解以下需求文本为规则树草稿节点：

{raw_text}
""".strip()

_NODE_TYPE_ALIASES = {
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
    "异常": "exception",
}


def parse_requirement_text(raw_text: str, llm_client: Optional[Any] = None) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return {"analysis_mode": "mock", "nodes": [], "risks": []}

    if _should_use_llm():
        try:
            llm = llm_client or LLMClient()
            payload = llm.chat_with_json(
                system_prompt=AI_PARSE_SYSTEM_PROMPT,
                user_prompt=AI_PARSE_USER_TEMPLATE.format(raw_text=text),
            )
            normalized = _normalize_llm_payload(payload)
            if normalized["nodes"]:
                return {
                    **normalized,
                    "analysis_mode": "llm",
                    **build_llm_success_meta(_resolve_provider_from_llm(llm)),
                }
            logger.warning("AI parse LLM returned no usable nodes, returning empty result")
        except Exception as exc:
            logger.warning(
                "AI parse LLM failed, returning empty result (%s: %s)",
                type(exc).__name__,
                exc,
            )
        return {
            "analysis_mode": "llm_failed",
            "nodes": [],
            "risks": [],
            **build_llm_failure_meta(),
        }

    fallback = _parse_by_clause(text)
    fallback["analysis_mode"] = "mock"
    return fallback


def _should_use_llm() -> bool:
    provider = os.getenv("AI_PARSE_PROVIDER", "llm").strip().lower()
    return provider in {"llm", "auto", ""}


def _parse_by_clause(text: str) -> Dict[str, Any]:
    clauses = [c.strip() for c in text.replace("。", "，").split("，") if c.strip()]

    nodes: List[Dict[str, Any]] = []
    parent_id = None
    for index, clause in enumerate(clauses, start=1):
        node_id = "temp_{0}".format(index)
        node_type = "condition" if index == 1 else "branch"
        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "content": clause,
                "parent_id": parent_id,
            }
        )
        parent_id = node_id

    if len(nodes) == 1:
        nodes[0]["type"] = "root"

    return {"nodes": nodes, "risks": []}


def _normalize_llm_payload(payload: Any) -> Dict[str, Any]:
    raw_nodes = _extract_nodes(payload)
    if not raw_nodes:
        return {"nodes": [], "risks": []}

    nodes: List[Dict[str, Any]] = []
    used_ids = set()

    for index, raw_node in enumerate(raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue

        node_id = _pick_string(raw_node, ["id", "node_id", "nodeId", "key"]) or "temp_{0}".format(index)
        if node_id in used_ids:
            node_id = "{0}_{1}".format(node_id, index)
        used_ids.add(node_id)

        content = _pick_string(raw_node, ["content", "text", "name", "title"]) or "节点{0}".format(index)
        node_type = _normalize_node_type(
            _pick_string(raw_node, ["type", "node_type", "nodeType", "kind"]),
            is_first=(len(nodes) == 0),
        )
        parent_id = _pick_string(raw_node, ["parent_id", "parentId", "parent", "parent_node_id", "pid"])

        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "content": content.strip(),
                "parent_id": parent_id,
            }
        )

    _repair_tree(nodes)
    risks = _extract_risks(payload)
    return {"nodes": nodes, "risks": risks}


def _extract_nodes(payload: Any) -> List[Any]:
    if not isinstance(payload, dict):
        return []

    nodes = payload.get("nodes")
    if isinstance(nodes, list):
        return nodes

    decision_tree = payload.get("decision_tree")
    if isinstance(decision_tree, dict) and isinstance(decision_tree.get("nodes"), list):
        return decision_tree["nodes"]

    decision_tree_alias = payload.get("decisionTree")
    if isinstance(decision_tree_alias, list):
        return decision_tree_alias

    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_nodes(data)

    return []


def _pick_string(payload: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalize_node_type(value: Optional[str], is_first: bool) -> str:
    if value:
        mapped = _NODE_TYPE_ALIASES.get(value.strip().lower()) or _NODE_TYPE_ALIASES.get(value.strip())
        if mapped:
            return mapped
    return "root" if is_first else "branch"


def _repair_tree(nodes: List[Dict[str, Any]]) -> None:
    if not nodes:
        return

    root_id = nodes[0]["id"]
    nodes[0]["type"] = "root"
    nodes[0]["parent_id"] = None

    seen_ids = {root_id}
    for node in nodes[1:]:
        if node.get("type") == "root":
            node["type"] = "condition"
        parent_id = node.get("parent_id")
        if not parent_id or parent_id not in seen_ids:
            node["parent_id"] = root_id
        seen_ids.add(node["id"])


_VALID_RISK_CATEGORIES = {"input_validation", "flow_gap", "data_integrity", "boundary", "security"}
_VALID_RISK_LEVELS = {"critical", "high", "medium", "low"}


def _extract_risks(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    raw_risks = payload.get("risks")
    if not isinstance(raw_risks, list):
        return []

    risks: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_risks, start=1):
        if not isinstance(item, dict):
            continue

        risk_id = _pick_string(item, ["id"]) or "risk_{0}".format(index)
        related_node_id = _pick_string(item, ["related_node_id", "relatedNodeId"]) or None
        category = _pick_string(item, ["category", "type"]) or "flow_gap"
        if category not in _VALID_RISK_CATEGORIES:
            category = "flow_gap"
        risk_level = _pick_string(item, ["risk_level", "riskLevel", "severity"]) or "medium"
        if risk_level not in _VALID_RISK_LEVELS:
            risk_level = "medium"
        description = _pick_string(item, ["description", "desc", "content"]) or ""
        suggestion = _pick_string(item, ["suggestion", "advice", "mitigation"]) or ""

        if not description:
            continue

        risks.append({
            "id": risk_id,
            "related_node_id": related_node_id,
            "category": category,
            "risk_level": risk_level,
            "description": description,
            "suggestion": suggestion,
        })

    return risks


def _resolve_provider_from_llm(llm: Any) -> Optional[str]:
    getter = getattr(llm, "get_last_provider", None)
    if not callable(getter):
        return None
    provider = getter(method_name="chat_with_json")
    if not provider:
        return None
    return str(provider).strip().lower()
