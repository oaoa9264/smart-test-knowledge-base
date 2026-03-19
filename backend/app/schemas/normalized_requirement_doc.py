from pydantic import BaseModel
from typing import Optional


class NormalizedRequirementDocPreview(BaseModel):
    title: str
    markdown: str
    basis_hash: str
    uses_fresh_snapshot: bool
    snapshot_stale: bool
    llm_status: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_message: Optional[str] = None
