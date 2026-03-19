from typing import List, Optional, Union

from pydantic import BaseModel, validator


class TestPlanRequest(BaseModel):
    requirement_id: int
    session_id: Optional[int] = None


class TestPoint(BaseModel):
    id: str
    name: str
    description: str
    type: str
    related_node_ids: List[str] = []
    priority: str = "medium"


class TestPlanResponse(BaseModel):
    markdown: str
    test_points: List[TestPoint]
    llm_status: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_message: Optional[str] = None
    session_id: Optional[int] = None


class TestCaseGenRequest(BaseModel):
    requirement_id: int
    test_plan_markdown: str
    test_points: List[TestPoint]
    session_id: Optional[int] = None


class GeneratedTestCase(BaseModel):
    title: str
    preconditions: Union[List[str], str] = []
    steps: Union[List[str], str] = []
    expected_result: Union[List[str], str] = []
    risk_level: str = "medium"
    related_node_ids: List[str] = []

    @validator("preconditions", "steps", "expected_result", pre=True)
    def _normalize_to_list(cls, v):
        if isinstance(v, str):
            return [v] if v else []
        return v or []

    def steps_as_text(self) -> str:
        """Serialize steps list to readable text for DB storage."""
        items = self.steps if isinstance(self.steps, list) else [self.steps]
        return "\n".join(
            "{0}. {1}".format(i, s) for i, s in enumerate(items, 1)
        )

    def expected_result_as_text(self) -> str:
        """Serialize expected_result list to readable text for DB storage."""
        items = (
            self.expected_result
            if isinstance(self.expected_result, list)
            else [self.expected_result]
        )
        return "\n".join("- {0}".format(r) for r in items)

    def preconditions_as_text(self) -> str:
        """Serialize preconditions list to readable text for DB storage."""
        items = (
            self.preconditions
            if isinstance(self.preconditions, list)
            else [self.preconditions]
        )
        return "\n".join("- {0}".format(p) for p in items)


class TestCaseGenResponse(BaseModel):
    test_cases: List[GeneratedTestCase]
    llm_status: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_message: Optional[str] = None
    session_id: Optional[int] = None


class TestCaseConfirmRequest(BaseModel):
    requirement_id: int
    test_cases: List[GeneratedTestCase]
    session_id: Optional[int] = None


class TestCaseConfirmResponse(BaseModel):
    created_count: int
    created_case_ids: List[int] = []


# ---------- Plan update ----------


class TestPlanUpdateRequest(BaseModel):
    plan_markdown: str
    test_points: List[TestPoint]


# ---------- Session schemas ----------


class TestPlanSessionCreate(BaseModel):
    requirement_id: int


class TestPlanSessionResponse(BaseModel):
    id: int
    requirement_id: int
    status: str
    plan_markdown: Optional[str] = None
    test_points: Optional[List[TestPoint]] = None
    generated_cases: Optional[List[GeneratedTestCase]] = None
    confirmed_case_ids: Optional[List[int]] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TestPlanSessionListResponse(BaseModel):
    sessions: List[TestPlanSessionResponse]
