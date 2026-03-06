from app.services.coverage import build_coverage_matrix
from app.services.impact import analyze_impact


def test_build_coverage_matrix_flags_uncovered_critical_nodes():
    nodes = [
        {"id": "n1", "content": "A", "node_type": "action", "risk_level": "critical"},
        {"id": "n2", "content": "B", "node_type": "branch", "risk_level": "high"},
    ]
    testcases = [
        {"id": "tc1", "bound_rule_nodes": ["n2"], "bound_paths": []},
    ]
    paths = [["n1", "n2"]]

    result = build_coverage_matrix(nodes=nodes, testcases=testcases, paths=paths)

    assert result["summary"]["total_nodes"] == 2
    assert result["summary"]["covered_nodes"] == 1
    assert result["summary"]["structural_nodes"] == 0
    assert result["summary"]["uncovered_critical"] == ["n1"]


def test_build_coverage_matrix_excludes_structural_nodes_from_rate():
    nodes = [
        {"id": "r1", "content": "Root", "node_type": "root", "risk_level": "low"},
        {"id": "c1", "content": "Condition", "node_type": "condition", "risk_level": "medium"},
        {"id": "a1", "content": "Action", "node_type": "action", "risk_level": "high"},
        {"id": "e1", "content": "Exception", "node_type": "exception", "risk_level": "critical"},
    ]
    testcases = [
        {"id": "tc1", "bound_rule_nodes": ["a1"], "bound_paths": []},
    ]
    paths = [["r1", "c1", "a1"], ["r1", "c1", "e1"]]

    result = build_coverage_matrix(nodes=nodes, testcases=testcases, paths=paths)

    assert result["summary"]["total_nodes"] == 2
    assert result["summary"]["structural_nodes"] == 2
    assert result["summary"]["covered_nodes"] == 1
    assert result["summary"]["coverage_rate"] == 0.5
    assert result["summary"]["uncovered_critical"] == ["e1"]

    rows_by_id = {r["node_id"]: r for r in result["rows"]}
    assert rows_by_id["r1"]["coverable"] is False
    assert rows_by_id["c1"]["coverable"] is False
    assert rows_by_id["a1"]["coverable"] is True
    assert rows_by_id["e1"]["coverable"] is True


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
