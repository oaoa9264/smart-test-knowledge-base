from typing import Dict, List


def build_coverage_matrix(nodes: List[Dict], testcases: List[Dict], paths: List[List[str]]) -> Dict:
    node_coverage = {}
    for node in nodes:
        node_coverage[node["id"]] = {
            "node_id": node["id"],
            "content": node.get("content", ""),
            "risk_level": node.get("risk_level", "medium"),
            "covered_cases": 0,
            "uncovered_paths": 0,
        }

    node_to_cases = {}
    for case in testcases:
        case_id = case["id"]
        for node_id in case.get("bound_rule_nodes", []):
            node_to_cases.setdefault(node_id, set()).add(case_id)

    uncovered_paths = []
    for path in paths:
        covered = False
        for node_id in path:
            if node_to_cases.get(node_id):
                covered = True
                break
        if not covered:
            uncovered_paths.append(path)
            for node_id in path:
                if node_id in node_coverage:
                    node_coverage[node_id]["uncovered_paths"] += 1

    for node_id, case_ids in node_to_cases.items():
        if node_id in node_coverage:
            node_coverage[node_id]["covered_cases"] = len(case_ids)

    total_nodes = len(nodes)
    covered_nodes = len([v for v in node_coverage.values() if v["covered_cases"] > 0])
    uncovered_critical = [
        n["node_id"]
        for n in node_coverage.values()
        if n["risk_level"] == "critical" and n["covered_cases"] == 0
    ]

    return {
        "rows": list(node_coverage.values()),
        "summary": {
            "total_nodes": total_nodes,
            "covered_nodes": covered_nodes,
            "coverage_rate": (covered_nodes / total_nodes) if total_nodes else 0,
            "uncovered_critical": uncovered_critical,
            "uncovered_paths": uncovered_paths,
        },
    }
