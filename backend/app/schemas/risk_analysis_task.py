from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RiskAnalysisTaskRead(BaseModel):
    id: int
    requirement_id: int
    stage: str
    status: str
    progress_message: Optional[str] = None
    progress_percent: Optional[int] = None
    last_error: Optional[str] = None
    snapshot_id: Optional[int] = None
    result_json: Optional[str] = None
    current_task_started_at: Optional[datetime] = None
    current_task_finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class RiskAnalysisTaskSummaryRead(BaseModel):
    review: Optional[RiskAnalysisTaskRead] = None
    pre_dev: Optional[RiskAnalysisTaskRead] = None
    pre_release: Optional[RiskAnalysisTaskRead] = None


class RiskAnalysisTaskStartResponse(BaseModel):
    accepted: bool
    task: RiskAnalysisTaskRead
