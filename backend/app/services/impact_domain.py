from collections import defaultdict
from typing import Any, Iterable, Set


def _get_field(item: Any, field: str, default=None):
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def compute_impact_domain(changed_node_ids: Iterable[str], nodes: Iterable[Any]) -> Set[str]:
    node_list = list(nodes)
    node_ids = set()
    parent_by_id = {}
    children_by_parent = defaultdict(list)

    for node in node_list:
        node_id = _get_field(node, "id")
        if not node_id:
            continue
        node_ids.add(node_id)
        parent_id = _get_field(node, "parent_id")
        parent_by_id[node_id] = parent_id
        if parent_id:
            children_by_parent[parent_id].append(node_id)

    impacted = set()

    for changed_id in changed_node_ids or []:
        if changed_id not in node_ids:
            continue

        impacted.add(changed_id)

        current = parent_by_id.get(changed_id)
        seen_up = set()
        while current and current not in seen_up:
            seen_up.add(current)
            if current in node_ids:
                impacted.add(current)
            current = parent_by_id.get(current)

        stack = [changed_id]
        seen_down = set()
        while stack:
            node_id = stack.pop()
            if node_id in seen_down:
                continue
            seen_down.add(node_id)
            impacted.add(node_id)
            for child_id in children_by_parent.get(node_id, []):
                stack.append(child_id)

    return impacted
