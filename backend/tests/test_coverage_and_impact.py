from app.services.coverage import build_coverage_matrix
from app.services.impact import analyze_impact


def test_build_coverage_matrix_flags_uncovered_critical_nodes():
    nodes = [
        {"id": "n1", "content": "A", "risk_level": "critical"},
        {"id": "n2", "content": "B", "risk_level": "high"},
    ]
    testcases = [
        {"id": "tc1", "bound_rule_nodes": ["n2"], "bound_paths": []},
    ]
    paths = [["n1", "n2"]]

    result = build_coverage_matrix(nodes=nodes, testcases=testcases, paths=paths)

    assert result["summary"]["total_nodes"] == 2
    assert result["summary"]["covered_nodes"] == 1
    assert result["summary"]["uncovered_critical"] == ["n1"]


def test_analyze_impact_marks_directly_bound_cases_for_review():
    changed_node_ids = ["n2"]
    testcases = [
        {"id": "tc1", "bound_rule_nodes": ["n1"], "bound_paths": []},
        {"id": "tc2", "bound_rule_nodes": ["n2"], "bound_paths": []},
    ]
    paths = [["n1", "n2"]]

    result = analyze_impact(changed_node_ids=changed_node_ids, testcases=testcases, paths=paths)

    assert result["affected_case_ids"] == ["tc2"]
    assert result["needs_review_case_ids"] == ["tc2"]
