import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import RiskDecision, RiskItem
from app.schemas.risk import (
    RiskAnalyzeRequest,
    RiskAnalyzeResponse,
    RiskDecisionRequest,
    RiskItemRead,
    RiskListResponse,
)
from app.services.risk_service import (
    analyze_risks,
    decide_risk,
    get_risks_for_requirement,
    risk_to_node,
)
from app.schemas.rule import RuleNodeRead

logger = logging.getLogger(__name__)

router = APIRouter(tags=["risks"])


@router.post("/api/ai/risks/analyze", response_model=RiskAnalyzeResponse, status_code=status.HTTP_201_CREATED)
def analyze_requirement_risks(payload: RiskAnalyzeRequest, db: Session = Depends(get_db)):
    try:
        risks = analyze_risks(db=db, requirement_id=payload.requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RiskAnalyzeResponse(
        risks=[RiskItemRead.from_orm(r) for r in risks],
        total=len(risks),
    )


@router.get("/api/rules/requirements/{requirement_id}/risks", response_model=RiskListResponse)
def list_requirement_risks(requirement_id: int, db: Session = Depends(get_db)):
    risks = get_risks_for_requirement(db=db, requirement_id=requirement_id)
    risk_reads = [RiskItemRead.from_orm(r) for r in risks]
    pending = sum(1 for r in risks if r.decision == RiskDecision.pending)
    accepted = sum(1 for r in risks if r.decision == RiskDecision.accepted)
    ignored = sum(1 for r in risks if r.decision == RiskDecision.ignored)
    return RiskListResponse(
        risks=risk_reads,
        total=len(risks),
        pending=pending,
        accepted=accepted,
        ignored=ignored,
    )


@router.put("/api/rules/risks/{risk_id}/decision", response_model=RiskItemRead)
def make_risk_decision(risk_id: str, payload: RiskDecisionRequest, db: Session = Depends(get_db)):
    try:
        risk = decide_risk(
            db=db,
            risk_id=risk_id,
            decision=payload.decision,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if payload.decision == "accepted" and payload.auto_create_node:
        try:
            risk_to_node(db=db, risk_id=risk_id)
        except ValueError:
            pass

    return RiskItemRead.from_orm(risk)


@router.post("/api/rules/risks/{risk_id}/to-node", response_model=RuleNodeRead, status_code=status.HTTP_201_CREATED)
def convert_risk_to_node(risk_id: str, db: Session = Depends(get_db)):
    try:
        node = risk_to_node(db=db, risk_id=risk_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RuleNodeRead.from_orm(node)
