from typing import Dict, List, Set

COVERABLE_TYPES: Set[str] = {"action", "branch", "exception"}


def build_coverage_matrix(nodes: List[Dict], testcases: List[Dict], paths: List[List[str]]) -> Dict:
    node_coverage = {}
    coverable_ids: Set[str] = set()

    for node in nodes:
        node_type = node.get("node_type", "branch")
        coverable = node_type in COVERABLE_TYPES
        if coverable:
            coverable_ids.add(node["id"])
        node_coverage[node["id"]] = {
            "node_id": node["id"],
            "content": node.get("content", ""),
            "node_type": node_type,
            "coverable": coverable,
            "risk_level": node.get("risk_level", "medium"),
            "covered_cases": 0,
            "uncovered_paths": 0,
        }

    node_to_cases: Dict[str, set] = {}
    for case in testcases:
        case_id = case["id"]
        for node_id in case.get("bound_rule_nodes", []):
            node_to_cases.setdefault(node_id, set()).add(case_id)

    uncovered_paths = []
    for path in paths:
        covered = False
        for node_id in path:
            if node_id in coverable_ids and node_to_cases.get(node_id):
                covered = True
                break
        if not covered:
            uncovered_paths.append(path)
            for node_id in path:
                if node_id in node_coverage and node_id in coverable_ids:
                    node_coverage[node_id]["uncovered_paths"] += 1

    for node_id, case_ids in node_to_cases.items():
        if node_id in node_coverage:
            node_coverage[node_id]["covered_cases"] = len(case_ids)

    coverable_rows = [v for v in node_coverage.values() if v["coverable"]]
    total_nodes = len(coverable_rows)
    covered_nodes = len([v for v in coverable_rows if v["covered_cases"] > 0])
    structural_nodes = len(nodes) - total_nodes
    uncovered_critical = [
        n["node_id"]
        for n in coverable_rows
        if n["risk_level"] == "critical" and n["covered_cases"] == 0
    ]

    return {
        "rows": list(node_coverage.values()),
        "summary": {
            "total_nodes": total_nodes,
            "covered_nodes": covered_nodes,
            "structural_nodes": structural_nodes,
            "coverage_rate": (covered_nodes / total_nodes) if total_nodes else 0,
            "uncovered_critical": uncovered_critical,
            "uncovered_paths": uncovered_paths,
        },
    }
