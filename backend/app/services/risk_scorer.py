from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Optional, Set

DEFAULT_SCORE_CONFIG = {"a": 3.0, "b": 1.0, "c": 1.5, "d": 2.0}
RISK_LEVEL_WEIGHT = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}


def _get_field(item: Any, field: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def _normalize_enum_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def compute_tree_stats(nodes: Iterable[Any]) -> Dict[str, Any]:
    node_list = list(nodes)
    node_ids = [_get_field(node, "id") for node in node_list if _get_field(node, "id")]
    id_set = set(node_ids)

    children_by_parent = defaultdict(list)
    parent_by_id = {}
    versions = {}

    for node in node_list:
        node_id = _get_field(node, "id")
        if not node_id:
            continue
        parent_id = _get_field(node, "parent_id")
        if parent_id in id_set:
            children_by_parent[parent_id].append(node_id)
            parent_by_id[node_id] = parent_id
        else:
            parent_by_id[node_id] = None
        versions[node_id] = float(_get_field(node, "version", 1) or 1)

    children_count = {node_id: len(children_by_parent.get(node_id, [])) for node_id in id_set}
    max_children = max(children_count.values()) if children_count else 1
    max_version = max(versions.values()) if versions else 1.0

    roots = [node_id for node_id in id_set if parent_by_id.get(node_id) is None]
    if not roots:
        roots = list(id_set)

    depth_map = {node_id: 0 for node_id in id_set}
    visited_depth = set()
    queue = deque([(root, 0) for root in roots])
    while queue:
        node_id, depth = queue.popleft()
        if (node_id, depth) in visited_depth:
            continue
        visited_depth.add((node_id, depth))
        if depth_map.get(node_id, 0) < depth:
            depth_map[node_id] = depth
        for child_id in children_by_parent.get(node_id, []):
            queue.append((child_id, depth + 1))

    memo = {}

    def _subtree_size(node_id: str, stack: Set[str]) -> int:
        if node_id in memo:
            return memo[node_id]
        if node_id in stack:
            return 0

        stack.add(node_id)
        size = 1
        for child_id in children_by_parent.get(node_id, []):
            size += _subtree_size(child_id, stack)
        stack.remove(node_id)

        memo[node_id] = size
        return size

    node_stats = {}
    for node_id in id_set:
        node_stats[node_id] = {
            "children_count": children_count.get(node_id, 0),
            "depth": depth_map.get(node_id, 0),
            "subtree_size": _subtree_size(node_id, set()),
            "version": versions.get(node_id, 1.0),
        }

    return {
        "max_children": float(max_children or 1),
        "max_version": float(max_version or 1),
        "node_stats": node_stats,
    }


def compute_risk_scores(
    nodes: Iterable[Any],
    tree_stats: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, float]] = None,
    uncovered_node_ids: Optional[Set[str]] = None,
) -> Dict[str, float]:
    node_list = list(nodes)
    stats = tree_stats or compute_tree_stats(node_list)
    merged_config = dict(DEFAULT_SCORE_CONFIG)
    if config:
        merged_config.update(config)

    uncovered_ids = set(uncovered_node_ids or set())
    node_stats = stats.get("node_stats", {})
    max_children = float(stats.get("max_children", 1.0) or 1.0)
    max_version = float(stats.get("max_version", 1.0) or 1.0)

    risk_scores = {}
    for node in node_list:
        node_id = _get_field(node, "id")
        if not node_id:
            continue

        risk_level = _normalize_enum_value(_get_field(node, "risk_level", "medium")).lower()
        type_weight = RISK_LEVEL_WEIGHT.get(risk_level, RISK_LEVEL_WEIGHT["medium"])

        node_metric = node_stats.get(node_id, {})
        children_count = float(node_metric.get("children_count", 0.0))
        complexity = children_count / max_children if max_children else 0.0

        version = float(_get_field(node, "version", node_metric.get("version", 1.0)) or 1.0)
        change_freq = version / max_version if max_version else 0.0

        uncovered_bonus = 1.0 if node_id in uncovered_ids else 0.0

        risk_scores[node_id] = (
            merged_config["a"] * type_weight
            + merged_config["b"] * complexity
            + merged_config["c"] * change_freq
            + merged_config["d"] * uncovered_bonus
        )

    return risk_scores
