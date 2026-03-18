from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import Requirement
from app.schemas.risk_convergence import (
    BlockingRisk,
    ConflictItem,
    EffectiveSnapshotRead,
    MatchedEvidence,
    PredevAnalysisRequest,
    PredevAnalysisResponse,
    PrereleaseAuditRequest,
    PrereleaseAuditResponse,
    ReopenedRisk,
    ResolvedRisk,
    ReviewSnapshotResponse,
    RiskItemCompact,
)
from app.services.effective_requirement_service import (
    generate_review_snapshot,
    get_latest_snapshot,
    list_snapshots,
)
from app.services.predev_analyzer import analyze_for_predev
from app.services.prerelease_auditor import audit_for_prerelease

router = APIRouter(tags=["effective-requirements"])

_VALID_SNAPSHOT_STAGES = {"review", "pre_dev", "pre_release"}


@router.post(
    "/api/requirements/{requirement_id}/snapshots/review",
    response_model=ReviewSnapshotResponse,
)
def create_review_snapshot(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    try:
        result = generate_review_snapshot(db=db, requirement_id=requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    snapshot = result["snapshot"]
    risks = result["risks"]
    hints = result["clarification_hints"]

    snapshot_read = EffectiveSnapshotRead.from_orm(snapshot)
    risk_compacts = [RiskItemCompact.from_orm(r) for r in risks]

    return ReviewSnapshotResponse(
        snapshot=snapshot_read,
        risks=risk_compacts,
        clarification_hints=hints,
    )


@router.get(
    "/api/requirements/{requirement_id}/snapshots",
    response_model=List[EffectiveSnapshotRead],
)
def list_requirement_snapshots(
    requirement_id: int,
    db: Session = Depends(get_db),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    snapshots = list_snapshots(db=db, requirement_id=requirement_id)
    return [EffectiveSnapshotRead.from_orm(s) for s in snapshots]


@router.get(
    "/api/requirements/{requirement_id}/snapshots/latest",
    response_model=Optional[EffectiveSnapshotRead],
)
def get_latest_requirement_snapshot(
    requirement_id: int,
    stage: Optional[str] = None,
    db: Session = Depends(get_db),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    if stage and stage not in _VALID_SNAPSHOT_STAGES:
        raise HTTPException(
            status_code=400,
            detail="invalid stage, must be one of: {0}".format(", ".join(sorted(_VALID_SNAPSHOT_STAGES))),
        )

    snapshot = get_latest_snapshot(db=db, requirement_id=requirement_id, stage=stage)
    if not snapshot:
        return None

    return EffectiveSnapshotRead.from_orm(snapshot)


@router.post(
    "/api/ai/risks/predev-analyze",
    response_model=PredevAnalysisResponse,
)
def run_predev_analysis(
    payload: PredevAnalysisRequest,
    db: Session = Depends(get_db),
):
    requirement = (
        db.query(Requirement)
        .filter(Requirement.id == payload.requirement_id)
        .first()
    )
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    try:
        result = analyze_for_predev(
            db=db, requirement_id=payload.requirement_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    snapshot = result["snapshot"]
    risks = result["risks"]
    conflicts_raw = result.get("conflicts", [])
    evidence_raw = result.get("matched_evidence", [])

    snapshot_read = EffectiveSnapshotRead.from_orm(snapshot)
    risk_compacts = [RiskItemCompact.from_orm(r) for r in risks]
    conflict_items = [ConflictItem(**c) for c in conflicts_raw]
    evidence_items = [MatchedEvidence(**e) for e in evidence_raw]

    return PredevAnalysisResponse(
        snapshot=snapshot_read,
        risks=risk_compacts,
        conflicts=conflict_items,
        matched_evidence=evidence_items,
    )


@router.post(
    "/api/ai/risks/prerelease-audit",
    response_model=PrereleaseAuditResponse,
)
def run_prerelease_audit(
    payload: PrereleaseAuditRequest,
    db: Session = Depends(get_db),
):
    requirement = (
        db.query(Requirement)
        .filter(Requirement.id == payload.requirement_id)
        .first()
    )
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    try:
        result = audit_for_prerelease(
            db=db, requirement_id=payload.requirement_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return PrereleaseAuditResponse(
        closure_summary=result.get("closure_summary", ""),
        blocking_risks=[BlockingRisk(**b) for b in result.get("blocking_risks", [])],
        reopened_risks=[ReopenedRisk(**r) for r in result.get("reopened_risks", [])],
        resolved_risks=[ResolvedRisk(**r) for r in result.get("resolved_risks", [])],
        audit_notes=result.get("audit_notes", []),
    )
