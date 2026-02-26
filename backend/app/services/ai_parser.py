from typing import Dict, List


def parse_requirement_text(raw_text: str) -> Dict[str, List[Dict]]:
    text = (raw_text or "").strip()
    if not text:
        return {"nodes": []}

    clauses = [c.strip() for c in text.replace("。", "，").split("，") if c.strip()]

    nodes = []
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

    return {"nodes": nodes}
