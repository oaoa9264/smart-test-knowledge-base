from typing import Dict, List


def analyze_impact(changed_node_ids: List[str], testcases: List[Dict], paths: List[List[str]]) -> Dict:
    changed_node_ids = set(changed_node_ids)

    affected_cases = set()
    for case in testcases:
        if changed_node_ids.intersection(set(case.get("bound_rule_nodes", []))):
            affected_cases.add(case["id"])

    needs_review_case_ids = sorted(list(affected_cases))

    return {
        "affected_case_ids": needs_review_case_ids,
        "needs_review_case_ids": needs_review_case_ids,
        "affected_count": len(needs_review_case_ids),
    }
