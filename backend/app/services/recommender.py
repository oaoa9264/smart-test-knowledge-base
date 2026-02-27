from typing import Dict, Optional, Set


def recommend_regression_set(
    universe: Set[str],
    risk_weights: Dict[str, float],
    cover_sets: Dict[int, Set[str]],
    k: int,
    cost_mode: str = "UNIT",
    case_costs: Optional[Dict[int, float]] = None,
):
    case_costs = case_costs or {}
    target_nodes = set(universe or set())
    covered = set()
    results = []

    total_target_risk = sum(float(risk_weights.get(node_id, 0.0)) for node_id in target_nodes)
    candidate_case_ids = set(cover_sets.keys())

    while len(results) < max(int(k), 0) and candidate_case_ids:
        best = None

        for case_id in sorted(candidate_case_ids):
            new_cover = (cover_sets.get(case_id, set()) & target_nodes) - covered
            gain = sum(float(risk_weights.get(node_id, 0.0)) for node_id in new_cover)
            if gain <= 0:
                continue

            cost = 1.0
            if str(cost_mode).upper() == "TIME":
                cost = float(case_costs.get(case_id, 1.0) or 1.0)
                if cost <= 0:
                    cost = 1.0

            score = gain / cost
            if best is None:
                best = (case_id, score, gain, new_cover)
                continue

            _, best_score, best_gain, _ = best
            if score > best_score or (score == best_score and gain > best_gain):
                best = (case_id, score, gain, new_cover)

        if best is None:
            break

        picked_case_id, _, gain_risk, gain_nodes = best
        ordered_gain_nodes = sorted(gain_nodes)
        contributors = sorted(
            [{"node_id": node_id, "risk": float(risk_weights.get(node_id, 0.0))} for node_id in gain_nodes],
            key=lambda item: item["risk"],
            reverse=True,
        )

        results.append(
            {
                "rank": len(results) + 1,
                "case_id": int(picked_case_id),
                "gain_risk": float(gain_risk),
                "gain_node_ids": ordered_gain_nodes,
                "top_contributors": contributors[:3],
                "why_selected": "新增覆盖{0}个节点，风险收益{1:.2f}".format(
                    len(ordered_gain_nodes),
                    float(gain_risk),
                ),
            }
        )

        covered.update(gain_nodes)
        candidate_case_ids.remove(picked_case_id)

    covered_risk = sum(float(risk_weights.get(node_id, 0.0)) for node_id in covered)
    coverage_ratio = (covered_risk / total_target_risk) if total_target_risk else 0.0

    remaining_nodes = sorted(
        list(target_nodes - covered),
        key=lambda node_id: float(risk_weights.get(node_id, 0.0)),
        reverse=True,
    )

    remaining_gaps = [
        {"node_id": node_id, "risk": float(risk_weights.get(node_id, 0.0))}
        for node_id in remaining_nodes
        if float(risk_weights.get(node_id, 0.0)) > 0
    ]

    return {
        "summary": {
            "k": int(k),
            "picked": len(results),
            "covered_risk": float(covered_risk),
            "total_target_risk": float(total_target_risk),
            "coverage_ratio": float(coverage_ratio),
        },
        "cases": results,
        "remaining_gaps": remaining_gaps,
    }
