from app.services.rule_engine import derive_rule_paths


def test_derive_rule_paths_returns_all_root_to_leaf_paths():
    nodes = [
        {"id": "root", "parent_id": None},
        {"id": "a", "parent_id": "root"},
        {"id": "b", "parent_id": "root"},
        {"id": "a1", "parent_id": "a"},
        {"id": "a2", "parent_id": "a"},
    ]

    paths = derive_rule_paths(nodes)

    assert sorted(paths) == sorted([
        ["root", "a", "a1"],
        ["root", "a", "a2"],
        ["root", "b"],
    ])


def test_derive_rule_paths_empty_when_no_roots():
    nodes = [{"id": "n1", "parent_id": "missing"}]

    assert derive_rule_paths(nodes) == []


def test_derive_rule_paths_handles_cycle_without_recursion_error():
    nodes = [
        {"id": "root", "parent_id": None},
        {"id": "a", "parent_id": "root"},
        {"id": "b", "parent_id": "a"},
        {"id": "a", "parent_id": "b"},
    ]

    assert derive_rule_paths(nodes) == [["root", "a", "b"]]
