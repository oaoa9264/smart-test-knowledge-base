from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NormalizedRequirementDocTaskRead(BaseModel):
    id: int
    requirement_id: int
    status: str
    progress_message: Optional[str] = None
    progress_percent: Optional[int] = None
    last_error: Optional[str] = None
    basis_hash: Optional[str] = None
    uses_fresh_snapshot: bool
    snapshot_stale: bool
    source_payload_json: Optional[str] = None
    snapshot_payload_json: Optional[str] = None
    result_markdown: Optional[str] = None
    llm_provider: Optional[str] = None
    current_task_started_at: Optional[datetime] = None
    current_task_finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class NormalizedRequirementDocTaskStartResponse(BaseModel):
    accepted: bool
    task: NormalizedRequirementDocTaskRead
