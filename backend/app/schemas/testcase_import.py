from typing import List, Optional

from pydantic import BaseModel, validator


_CONFIDENCE_VALUES = {"high", "medium", "low", "none"}
_ANALYSIS_MODE_VALUES = {"llm", "mock_fallback"}
_RISK_LEVEL_VALUES = {"critical", "high", "medium", "low"}


class ParsedCasePreview(BaseModel):
    index: int
    title: str
    steps: str
    expected_result: str
    matched_node_ids: List[str] = []
    matched_node_contents: List[str] = []
    suggested_risk_level: str = "medium"
    confidence: str = "none"
    match_reason: str = ""

    @validator("suggested_risk_level")
    def _validate_suggested_risk_level(cls, value):
        if value not in _RISK_LEVEL_VALUES:
            raise ValueError("invalid suggested_risk_level")
        return value

    @validator("confidence")
    def _validate_confidence(cls, value):
        if value not in _CONFIDENCE_VALUES:
            raise ValueError("invalid confidence")
        return value


class ImportParseResponse(BaseModel):
    parsed_cases: List[ParsedCasePreview]
    total_cases: int
    auto_matched: int
    need_review: int
    analysis_mode: str
    llm_provider: Optional[str] = None

    @validator("analysis_mode")
    def _validate_analysis_mode(cls, value):
        if value not in _ANALYSIS_MODE_VALUES:
            raise ValueError("invalid analysis_mode")
        return value


class ImportConfirmCase(BaseModel):
    title: str
    steps: str
    expected_result: str
    risk_level: str = "medium"
    bound_rule_node_ids: List[str] = []
    bound_path_ids: List[str] = []
    skip_import: bool = False

    @validator("risk_level")
    def _validate_risk_level(cls, value):
        if value not in _RISK_LEVEL_VALUES:
            raise ValueError("invalid risk_level")
        return value


class ImportConfirmRequest(BaseModel):
    requirement_id: int
    project_id: int
    cases: List[ImportConfirmCase]


class ImportConfirmResponse(BaseModel):
    imported_count: int
    bound_count: int
    skipped_count: int
