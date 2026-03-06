from typing import List

from pydantic import BaseModel


class TestCaseCreate(BaseModel):
    project_id: int
    title: str
    precondition: str = ""
    steps: str
    expected_result: str
    risk_level: str = "medium"
    status: str = "active"
    bound_rule_node_ids: List[str] = []
    bound_path_ids: List[str] = []


class TestCaseRead(BaseModel):
    id: int
    project_id: int
    title: str
    precondition: str = ""
    steps: str
    expected_result: str
    risk_level: str
    status: str
    bound_rule_node_ids: List[str]
    bound_path_ids: List[str]


class TestCaseUpdate(BaseModel):
    title: str
    precondition: str = ""
    steps: str
    expected_result: str
    risk_level: str = "medium"
    status: str = "active"
    bound_rule_node_ids: List[str] = []
    bound_path_ids: List[str] = []


class TestCaseUpdateStatus(BaseModel):
    status: str
