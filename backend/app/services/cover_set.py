from typing import Any, Dict, Iterable, Set


def _get_field(item: Any, field: str, default=None):
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def _extract_ids(case: Any, field: str):
    values = _get_field(case, field, []) or []
    extracted = []
    for value in values:
        if hasattr(value, "id"):
            extracted.append(str(value.id))
        else:
            extracted.append(str(value))
    return extracted


def compute_cover_sets(cases: Iterable[Any], path_map: Dict[str, Iterable[str]]) -> Dict[int, Set[str]]:
    cover_sets = {}

    for case in cases:
        case_id = _get_field(case, "id")
        if case_id is None:
            continue

        covered = set()
        for node_id in _extract_ids(case, "bound_rule_nodes"):
            covered.add(node_id)

        for path_id in _extract_ids(case, "bound_paths"):
            for node_id in path_map.get(str(path_id), []) or []:
                covered.add(str(node_id))

        cover_sets[int(case_id)] = covered

    return cover_sets
