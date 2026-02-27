from typing import Dict, List


def derive_rule_paths(nodes: List[Dict[str, str]]) -> List[List[str]]:
    if not nodes:
        return []

    by_parent = {}
    node_ids = set()
    for node in nodes:
        node_ids.add(node["id"])
        parent_id = node.get("parent_id")
        by_parent.setdefault(parent_id, []).append(node["id"])

    roots = [node_id for node_id in by_parent.get(None, []) if node_id in node_ids]
    if not roots:
        return []

    paths = []

    def dfs(node_id: str, path: List[str], visited: set) -> None:
        children = by_parent.get(node_id, [])
        advanced = False
        for child in children:
            if child in visited:
                continue
            advanced = True
            path.append(child)
            visited.add(child)
            dfs(child, path, visited)
            visited.remove(child)
            path.pop()
        if not advanced:
            paths.append(path[:])

    for root_id in roots:
        dfs(root_id, [root_id], {root_id})

    return paths
