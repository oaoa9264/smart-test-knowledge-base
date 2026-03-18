from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import AnalysisStage, Requirement, RiskAnalysisTask
from app.schemas.risk_analysis_task import (
    RiskAnalysisTaskRead,
    RiskAnalysisTaskStartResponse,
    RiskAnalysisTaskSummaryRead,
)
from app.services.risk_analysis_task_service import (
    RiskAnalysisTaskConflictError,
    start_risk_analysis_task,
)

router = APIRouter(tags=["risk-analysis-tasks"])

_VALID_ANALYSIS_STAGES = {stage.value for stage in AnalysisStage}


def _get_requirement_or_404(db: Session, requirement_id: int) -> Requirement:
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")
    return requirement


def _get_stage_task(db: Session, requirement_id: int, stage: str) -> Optional[RiskAnalysisTask]:
    return (
        db.query(RiskAnalysisTask)
        .filter(
            RiskAnalysisTask.requirement_id == requirement_id,
            RiskAnalysisTask.stage == AnalysisStage(stage),
        )
        .first()
    )


@router.get(
    "/api/requirements/{requirement_id}/analysis-tasks",
    response_model=RiskAnalysisTaskSummaryRead,
)
def get_risk_analysis_task_summary(requirement_id: int, db: Session = Depends(get_db)):
    _get_requirement_or_404(db, requirement_id)
    review_task = _get_stage_task(db, requirement_id, "review")
    pre_dev_task = _get_stage_task(db, requirement_id, "pre_dev")
    pre_release_task = _get_stage_task(db, requirement_id, "pre_release")
    return RiskAnalysisTaskSummaryRead(
        review=RiskAnalysisTaskRead.from_orm(review_task) if review_task else None,
        pre_dev=RiskAnalysisTaskRead.from_orm(pre_dev_task) if pre_dev_task else None,
        pre_release=RiskAnalysisTaskRead.from_orm(pre_release_task) if pre_release_task else None,
    )


@router.get(
    "/api/requirements/{requirement_id}/analysis-tasks/{stage}",
    response_model=Optional[RiskAnalysisTaskRead],
)
def get_risk_analysis_task(requirement_id: int, stage: str, db: Session = Depends(get_db)):
    _get_requirement_or_404(db, requirement_id)
    if stage not in _VALID_ANALYSIS_STAGES:
        raise HTTPException(
            status_code=400,
            detail="invalid stage, must be one of: {0}".format(", ".join(sorted(_VALID_ANALYSIS_STAGES))),
        )

    task = _get_stage_task(db, requirement_id, stage)
    if not task:
        return None
    return RiskAnalysisTaskRead.from_orm(task)


@router.post(
    "/api/requirements/{requirement_id}/analysis-tasks/{stage}",
    response_model=RiskAnalysisTaskStartResponse,
)
def start_requirement_risk_analysis_task(
    requirement_id: int,
    stage: str,
    db: Session = Depends(get_db),
):
    _get_requirement_or_404(db, requirement_id)
    if stage not in _VALID_ANALYSIS_STAGES:
        raise HTTPException(
            status_code=400,
            detail="invalid stage, must be one of: {0}".format(", ".join(sorted(_VALID_ANALYSIS_STAGES))),
        )

    try:
        task = start_risk_analysis_task(db, requirement_id, AnalysisStage(stage))
    except RiskAnalysisTaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return RiskAnalysisTaskStartResponse(
        accepted=True,
        task=RiskAnalysisTaskRead.from_orm(task),
    )
