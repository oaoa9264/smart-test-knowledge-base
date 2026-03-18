import json
import logging
from typing import Any, Dict, List, Optional

from app.services.llm_client import LLMClient
from app.services.prompts.test_plan import (
    TEST_CASE_GEN_SYSTEM_PROMPT,
    TEST_CASE_GEN_USER_TEMPLATE,
    TEST_PLAN_SYSTEM_PROMPT,
    TEST_PLAN_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

COVERABLE_TYPES = {"action", "branch", "exception"}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _build_nodes_json(nodes: List[Dict[str, Any]]) -> str:
    compact = [
        {
            "id": n.get("id"),
            "content": n.get("content"),
            "node_type": n.get("node_type"),
            "risk_level": n.get("risk_level", "medium"),
        }
        for n in nodes
    ]
    return _json_dumps(compact)


def _build_paths_json(
    paths: List[List[str]], node_map: Dict[str, Dict[str, Any]]
) -> str:
    result = []
    for idx, path in enumerate(paths, start=1):
        contents = [
            node_map[nid].get("content", nid) for nid in path if nid in node_map
        ]
        result.append(
            {
                "path_index": idx,
                "node_ids": path,
                "description": " -> ".join(contents),
            }
        )
    return _json_dumps(result)


def _validate_node_ids(
    items: List[Dict[str, Any]], valid_ids: set, field: str = "related_node_ids"
) -> List[Dict[str, Any]]:
    """Filter out invalid node IDs from each item."""
    for item in items:
        raw = item.get(field, [])
        if isinstance(raw, list):
            item[field] = [nid for nid in raw if nid in valid_ids]
    return items


def _ensure_coverage(
    test_points: List[Dict[str, Any]],
    coverable_ids: set,
) -> List[Dict[str, Any]]:
    """Ensure every coverable node appears in at least one test point."""
    covered = set()
    for tp in test_points:
        for nid in tp.get("related_node_ids", []):
            covered.add(nid)

    uncovered = coverable_ids - covered
    if uncovered:
        logger.warning("Test plan missed %d coverable nodes, adding fallback points", len(uncovered))
        for nid in sorted(uncovered):
            test_points.append(
                {
                    "id": "tp_auto_{0}".format(nid),
                    "name": "补充测试点-{0}".format(nid),
                    "description": "自动补充：确保节点 {0} 被覆盖".format(nid),
                    "type": "normal",
                    "related_node_ids": [nid],
                    "priority": "medium",
                }
            )
    return test_points


def _fallback_test_plan(nodes: List[Dict[str, Any]], paths: List[List[str]]) -> Dict[str, Any]:
    node_map = {n["id"]: n for n in nodes}
    coverable_ids = [n["id"] for n in nodes if n.get("node_type") in COVERABLE_TYPES]
    fallback_ids = coverable_ids or [n["id"] for n in nodes]
    lines = ["# 测试方案", "", "## 覆盖范围"]
    if paths:
        for idx, path in enumerate(paths, start=1):
            contents = [node_map[nid].get("content", nid) for nid in path if nid in node_map]
            if contents:
                lines.append("{0}. {1}".format(idx, " -> ".join(contents)))
    else:
        for idx, node_id in enumerate(fallback_ids, start=1):
            lines.append("{0}. {1}".format(idx, node_map.get(node_id, {}).get("content", node_id)))
    if len(lines) == 3:
        lines.append("1. 通用规则回归与关键流程检查")

    test_points = []
    for idx, node_id in enumerate(fallback_ids, start=1):
        node = node_map.get(node_id, {})
        test_points.append(
            {
                "id": "tp_fallback_{0}".format(idx),
                "name": "覆盖-{0}".format(node.get("content", node_id)),
                "description": "兜底生成：覆盖节点 {0}".format(node.get("content", node_id)),
                "type": "normal",
                "related_node_ids": [node_id],
                "priority": "medium",
            }
        )
    if not test_points:
        test_points.append(
            {
                "id": "tp_fallback_general",
                "name": "通用回归检查",
                "description": "兜底生成：覆盖需求关键流程与异常处理",
                "type": "normal",
                "related_node_ids": [],
                "priority": "medium",
            }
        )
    return {"markdown": "\n".join(lines), "test_points": test_points}


def _fallback_test_cases(
    test_points: List[Dict[str, Any]],
    nodes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    node_map = {n["id"]: n for n in nodes}
    fallback_cases = []
    for idx, point in enumerate(test_points, start=1):
        related_ids = [nid for nid in point.get("related_node_ids", []) if nid in node_map]
        title_suffix = point.get("name") or "测试点{0}".format(idx)
        fallback_cases.append(
            {
                "title": "兜底用例-{0}".format(title_suffix),
                "preconditions": ["系统已准备好执行该测试点"],
                "steps": ["执行测试点：{0}".format(title_suffix)],
                "expected_result": ["相关规则按预期生效"],
                "risk_level": "medium",
                "related_node_ids": related_ids,
            }
        )
    return fallback_cases


def generate_test_plan(
    nodes: List[Dict[str, Any]],
    paths: List[List[str]],
    llm_client: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    node_map = {n["id"]: n for n in nodes}
    coverable_ids = {
        n["id"] for n in nodes if n.get("node_type") in COVERABLE_TYPES
    }

    nodes_json = _build_nodes_json(nodes)
    paths_json = _build_paths_json(paths, node_map)

    user_prompt = TEST_PLAN_USER_TEMPLATE.format(
        nodes_json=nodes_json,
        paths_json=paths_json,
    )

    try:
        llm = llm_client or LLMClient()
        result = llm.chat_with_json(
            system_prompt=TEST_PLAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        logger.warning(
            "Test plan generation failed (%s: %s), using fallback",
            type(exc).__name__,
            exc,
        )
        result = _fallback_test_plan(nodes=nodes, paths=paths)

    markdown = result.get("markdown", "")
    test_points = result.get("test_points", [])
    if not isinstance(test_points, list):
        test_points = []

    test_points = _validate_node_ids(test_points, set(node_map.keys()))
    test_points = _ensure_coverage(test_points, coverable_ids)

    return {"markdown": markdown, "test_points": test_points}


def generate_test_cases(
    test_plan_markdown: str,
    test_points: List[Dict[str, Any]],
    nodes: List[Dict[str, Any]],
    paths: List[List[str]],
    llm_client: Optional[LLMClient] = None,
) -> List[Dict[str, Any]]:
    node_map = {n["id"]: n for n in nodes}
    coverable_ids = {
        n["id"] for n in nodes if n.get("node_type") in COVERABLE_TYPES
    }

    nodes_json = _build_nodes_json(nodes)
    paths_json = _build_paths_json(paths, node_map)
    test_points_json = _json_dumps(test_points)

    user_prompt = TEST_CASE_GEN_USER_TEMPLATE.format(
        test_plan_markdown=test_plan_markdown,
        test_points_json=test_points_json,
        nodes_json=nodes_json,
        paths_json=paths_json,
    )

    try:
        llm = llm_client or LLMClient()
        result = llm.chat_with_json(
            system_prompt=TEST_CASE_GEN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        logger.warning(
            "Test case generation failed (%s: %s), using fallback",
            type(exc).__name__,
            exc,
        )
        result = {"test_cases": _fallback_test_cases(test_points=test_points, nodes=nodes)}

    test_cases = result.get("test_cases", [])
    if not isinstance(test_cases, list):
        test_cases = []

    test_cases = _validate_node_ids(test_cases, set(node_map.keys()))

    covered = set()
    for tc in test_cases:
        for nid in tc.get("related_node_ids", []):
            covered.add(nid)

    uncovered = coverable_ids - covered
    if uncovered:
        logger.warning("Generated cases missed %d coverable nodes, adding fallback cases", len(uncovered))
        for nid in sorted(uncovered):
            node = node_map.get(nid, {})
            content = node.get("content", nid)
            test_cases.append(
                {
                    "title": "补充用例-{0}".format(content),
                    "preconditions": ["系统中存在触发「{0}」的数据条件".format(content)],
                    "steps": ["构造满足「{0}」的测试数据".format(content), "执行对应操作并观察结果"],
                    "expected_result": ["「{0}」行为符合预期".format(content)],
                    "risk_level": node.get("risk_level", "medium"),
                    "related_node_ids": [nid],
                }
            )

    return test_cases
