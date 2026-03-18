import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import (
    NodeStatus,
    RecoMode,
    RecoResult,
    RecoRun,
    Requirement,
    RuleNode,
    RulePath,
    TestCase,
)
from app.schemas.recommendation import (
    RecoRequest,
    RecoResponse,
    RecoResultRead,
    RecoRunDetailRead,
    RecoRunRead,
)
from app.services.cover_set import compute_cover_sets
from app.services.impact_domain import compute_impact_domain
from app.services.recommender import recommend_regression_set
from app.services.risk_scorer import compute_risk_scores, compute_tree_stats

router = APIRouter(prefix="/api/reco", tags=["recommendation"])


def _json_loads(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _parse_node_sequence(value):
    if not value:
        return []
    return [node_id.strip() for node_id in value.split(",") if node_id.strip()]


def _to_run_read(run):
    return RecoRunRead(
        id=run.id,
        requirement_id=run.requirement_id,
        mode=run.mode.value if hasattr(run.mode, "value") else str(run.mode),
        k=run.k,
        input_changed_node_ids=_json_loads(run.input_changed_node_ids, []),
        total_target_risk=float(run.total_target_risk),
        covered_risk=float(run.covered_risk),
        coverage_ratio=float(run.coverage_ratio),
        created_at=run.created_at,
    )


def _to_result_read(result):
    return RecoResultRead(
        id=result.id,
        run_id=result.run_id,
        rank=result.rank,
        case_id=result.case_id,
        gain_risk=float(result.gain_risk),
        gain_node_ids=_json_loads(result.gain_node_ids, []),
        top_contributors=_json_loads(result.top_contributors, []),
        why_selected=result.why_selected,
    )


@router.post("/regression", response_model=RecoResponse)
def recommend_regression(payload: RecoRequest, db: Session = Depends(get_db)):
    if payload.k <= 0:
        raise HTTPException(status_code=400, detail="k must be positive")

    requirement = db.query(Requirement).filter(Requirement.id == payload.requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    mode_value = str(payload.mode or "FULL").upper()
    if mode_value not in {RecoMode.full.value, RecoMode.change.value}:
        raise HTTPException(status_code=400, detail="mode must be FULL or CHANGE")
    if mode_value == RecoMode.change.value and not payload.changed_node_ids:
        raise HTTPException(status_code=400, detail="changed_node_ids is required in CHANGE mode")

    nodes = (
        db.query(RuleNode)
        .filter(
            RuleNode.requirement_id == payload.requirement_id,
            RuleNode.status != NodeStatus.deleted,
        )
        .all()
    )
    if not nodes:
        raise HTTPException(status_code=400, detail="rule tree is empty")
    paths = db.query(RulePath).filter(RulePath.requirement_id == payload.requirement_id).all()

    case_query = (
        db.query(TestCase)
        .filter(TestCase.project_id == requirement.project_id)
        .outerjoin(TestCase.bound_rule_nodes)
        .outerjoin(TestCase.bound_paths)
        .filter(
            or_(
                RuleNode.requirement_id == payload.requirement_id,
                RulePath.requirement_id == payload.requirement_id,
            )
        )
        .distinct()
    )

    if payload.case_filter:
        if payload.case_filter.status_in:
            case_query = case_query.filter(TestCase.status.in_(payload.case_filter.status_in))
        if payload.case_filter.case_ids:
            case_query = case_query.filter(TestCase.id.in_(payload.case_filter.case_ids))

    cases = case_query.order_by(TestCase.id.asc()).all()

    path_map = {path.id: _parse_node_sequence(path.node_sequence) for path in paths}
    cover_sets = compute_cover_sets(cases=cases, path_map=path_map)

    covered_node_ids = set()
    for node_ids in cover_sets.values():
        covered_node_ids.update(node_ids)

    tree_stats = compute_tree_stats(nodes)
    uncovered_node_ids = {node.id for node in nodes if node.id not in covered_node_ids}
    risk_weights = compute_risk_scores(
        nodes=nodes,
        tree_stats=tree_stats,
        uncovered_node_ids=uncovered_node_ids,
    )

    universe = {node.id for node in nodes}
    if mode_value == RecoMode.change.value:
        valid_node_ids = {node.id for node in nodes}
        if not any(node_id in valid_node_ids for node_id in (payload.changed_node_ids or [])):
            raise HTTPException(status_code=400, detail="invalid changed_node_ids")
        impacted = compute_impact_domain(payload.changed_node_ids or [], nodes)
        if not impacted:
            raise HTTPException(status_code=400, detail="invalid changed_node_ids")
        universe = impacted
        for node_id in impacted:
            risk_weights[node_id] = float(risk_weights.get(node_id, 0.0)) * 1.5

    recommend_result = recommend_regression_set(
        universe=universe,
        risk_weights=risk_weights,
        cover_sets=cover_sets,
        k=payload.k,
        cost_mode=payload.cost_mode,
    )

    run = RecoRun(
        requirement_id=payload.requirement_id,
        mode=RecoMode.change if mode_value == RecoMode.change.value else RecoMode.full,
        k=payload.k,
        input_changed_node_ids=json.dumps(payload.changed_node_ids or []),
        total_target_risk=float(recommend_result["summary"]["total_target_risk"]),
        covered_risk=float(recommend_result["summary"]["covered_risk"]),
        coverage_ratio=float(recommend_result["summary"]["coverage_ratio"]),
    )
    db.add(run)
    db.flush()

    for item in recommend_result["cases"]:
        db.add(
            RecoResult(
                run_id=run.id,
                rank=item["rank"],
                case_id=item["case_id"],
                gain_risk=float(item["gain_risk"]),
                gain_node_ids=json.dumps(item.get("gain_node_ids", [])),
                top_contributors=json.dumps(item.get("top_contributors", [])),
                why_selected=item["why_selected"],
            )
        )

    db.commit()

    return RecoResponse(
        run_id=run.id,
        summary=recommend_result["summary"],
        cases=[
            {
                "rank": item["rank"],
                "case_id": item["case_id"],
                "gain_risk": item["gain_risk"],
                "gain_nodes": item.get("gain_node_ids", []),
                "top_contributors": item.get("top_contributors", []),
                "why_selected": item["why_selected"],
            }
            for item in recommend_result["cases"]
        ],
        remaining_high_risk_gaps=recommend_result["remaining_gaps"],
    )


@router.get("/runs", response_model=List[RecoRunRead])
def list_reco_runs(requirement_id: int, db: Session = Depends(get_db)):
    runs = (
        db.query(RecoRun)
        .filter(RecoRun.requirement_id == requirement_id)
        .order_by(RecoRun.id.desc())
        .all()
    )
    return [_to_run_read(run) for run in runs]


@router.get("/runs/{run_id}", response_model=RecoRunDetailRead)
def get_reco_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(RecoRun).filter(RecoRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="reco run not found")

    results = db.query(RecoResult).filter(RecoResult.run_id == run_id).order_by(RecoResult.rank.asc()).all()
    return RecoRunDetailRead(run=_to_run_read(run), results=[_to_result_read(result) for result in results])
