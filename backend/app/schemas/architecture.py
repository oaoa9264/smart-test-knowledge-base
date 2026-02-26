from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class DecisionTreeNode(BaseModel):
    id: str
    type: str
    content: str
    parent_id: Optional[str] = None
    risk_level: str = "medium"


class DecisionTreeResult(BaseModel):
    nodes: List[DecisionTreeNode]


class TestPlanResult(BaseModel):
    markdown: str
    sections: List[str]


class RiskPoint(BaseModel):
    id: str
    description: str
    severity: str
    mitigation: str
    related_node_ids: List[str]


class GeneratedTestCase(BaseModel):
    title: str
    steps: str
    expected_result: str
    risk_level: str
    related_node_ids: List[str]


class ArchitectureAnalysisResult(BaseModel):
    decision_tree: DecisionTreeResult
    test_plan: TestPlanResult
    risk_points: List[RiskPoint]
    test_cases: List[GeneratedTestCase]


class ArchitectureAnalysisRead(BaseModel):
    id: int
    project_id: int
    requirement_id: Optional[int] = None
    title: str
    image_path: Optional[str] = None
    description_text: Optional[str] = None
    status: str
    created_at: datetime
    result: Optional[ArchitectureAnalysisResult] = None


class ArchitectureAnalyzeResponse(ArchitectureAnalysisResult):
    id: int


class ArchitectureImportOptions(BaseModel):
    import_decision_tree: bool = True
    import_test_cases: bool = True
    import_risk_points: bool = True


class ArchitectureImportResult(BaseModel):
    analysis_id: int
    requirement_id: Optional[int] = None
    imported_rule_nodes: int
    imported_test_cases: int
    updated_risk_nodes: int

