from typing import Dict, List, Set

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import NodeStatus, Project, Requirement, RiskLevel, RuleNode, RulePath, TestCase
from app.schemas.testcase_import import (
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportParseResponse,
    ParsedCasePreview,
)
from app.services.testcase_importer import parse_testcases_from_upload
from app.services.testcase_matcher import MatchResult, TestCaseMatcher

router = APIRouter(prefix="/api/testcases/import", tags=["testcase-import"])


@router.post("/parse", response_model=ImportParseResponse)
async def parse_import_file(
    requirement_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        parsed_cases = parse_testcases_from_upload(file.filename or "", file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    rule_nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id == requirement_id, RuleNode.status != NodeStatus.deleted)
        .all()
    )
    matcher = TestCaseMatcher()
    matches, analysis_mode = matcher.match_cases(parsed_cases=parsed_cases, rule_nodes=rule_nodes)
    llm_provider = getattr(matcher, "get_llm_provider", lambda: None)()
    llm_status = getattr(matcher, "get_llm_status", lambda: None)()
    llm_message = getattr(matcher, "get_llm_message", lambda: None)()

    node_map = {node.id: node for node in rule_nodes}
    preview_rows = _build_preview_rows(parsed_cases=parsed_cases, matches=matches, node_map=node_map)

    total_cases = len(preview_rows)
    auto_matched = len([item for item in preview_rows if item.matched_node_ids and item.confidence != "none"])
    need_review = total_cases - auto_matched

    return ImportParseResponse(
        parsed_cases=preview_rows,
        total_cases=total_cases,
        auto_matched=auto_matched,
        need_review=need_review,
        analysis_mode=analysis_mode,
        llm_status=llm_status,
        llm_provider=llm_provider,
        llm_message=llm_message,
    )


@router.post("/confirm", response_model=ImportConfirmResponse)
def confirm_import(payload: ImportConfirmRequest, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    requirement = db.query(Requirement).filter(Requirement.id == payload.requirement_id).first()
    if not project or not requirement or requirement.project_id != project.id:
        raise HTTPException(status_code=400, detail="invalid_project_requirement_relation")

    importable_cases = [case for case in payload.cases if not case.skip_import]
    skipped_count = len(payload.cases) - len(importable_cases)

    for case in importable_cases:
        if not case.bound_rule_node_ids:
            raise HTTPException(status_code=400, detail="unbound_case_not_allowed")

    all_rule_node_ids: Set[str] = set()
    all_path_ids: Set[str] = set()
    for case in importable_cases:
        all_rule_node_ids.update(case.bound_rule_node_ids)
        all_path_ids.update(case.bound_path_ids)

    valid_nodes = _validate_nodes(db=db, requirement_id=payload.requirement_id, node_ids=all_rule_node_ids)
    valid_paths = _validate_paths(db=db, requirement_id=payload.requirement_id, path_ids=all_path_ids)

    imported_count = 0
    bound_count = 0

    try:
        for case in importable_cases:
            bound_nodes = [valid_nodes[node_id] for node_id in set(case.bound_rule_node_ids)]
            bound_paths = [valid_paths[path_id] for path_id in set(case.bound_path_ids)]
            case_row = TestCase(
                project_id=payload.project_id,
                title=case.title,
                steps=case.steps,
                expected_result=case.expected_result,
                risk_level=_derive_case_risk_level(bound_nodes),
            )

            _validate_path_contains_nodes(
                node_ids={node.id for node in bound_nodes},
                bound_paths=bound_paths,
            )

            case_row.bound_rule_nodes = bound_nodes
            case_row.bound_paths = bound_paths
            db.add(case_row)

            imported_count += 1
            if bound_nodes:
                bound_count += 1

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return ImportConfirmResponse(
        imported_count=imported_count,
        bound_count=bound_count,
        skipped_count=skipped_count,
    )


def _build_preview_rows(
    parsed_cases,
    matches: List[MatchResult],
    node_map: Dict[str, RuleNode],
) -> List[ParsedCasePreview]:
    rows: List[ParsedCasePreview] = []
    for index, case in enumerate(parsed_cases):
        match = matches[index] if index < len(matches) else MatchResult(
            case_index=index,
            matched_node_ids=[],
                confidence="none",
                reason="未命中规则节点",
        )
        matched_node_ids = [node_id for node_id in match.matched_node_ids if node_id in node_map]
        matched_nodes = [node_map[node_id] for node_id in matched_node_ids]
        suggested_risk_level = (
            _derive_case_risk_level(matched_nodes).value
            if matched_nodes
            else RiskLevel.medium.value
        )
        rows.append(
            ParsedCasePreview(
                index=index,
                title=case.title,
                steps=case.steps,
                expected_result=case.expected_result,
                matched_node_ids=matched_node_ids,
                matched_node_contents=[node_map[node_id].content for node_id in matched_node_ids],
                suggested_risk_level=suggested_risk_level,
                confidence=match.confidence,
                match_reason=match.reason,
            )
        )
    return rows


def _derive_case_risk_level(bound_nodes: List[RuleNode]) -> RiskLevel:
    if not bound_nodes:
        return RiskLevel.medium

    weights = {
        RiskLevel.critical: 4,
        RiskLevel.high: 3,
        RiskLevel.medium: 2,
        RiskLevel.low: 1,
    }
    return max(
        [node.risk_level for node in bound_nodes],
        key=lambda level: weights.get(level, 0),
    )


def _validate_nodes(db: Session, requirement_id: int, node_ids: Set[str]) -> Dict[str, RuleNode]:
    if not node_ids:
        return {}
    rows = db.query(RuleNode).filter(RuleNode.id.in_(node_ids), RuleNode.status != NodeStatus.deleted).all()
    if len(rows) != len(node_ids):
        raise HTTPException(status_code=400, detail="invalid_bound_rule_node_ids")
    if any(row.requirement_id != requirement_id for row in rows):
        raise HTTPException(status_code=400, detail="invalid_bound_rule_node_ids")
    return {row.id: row for row in rows}


def _validate_paths(db: Session, requirement_id: int, path_ids: Set[str]) -> Dict[str, RulePath]:
    if not path_ids:
        return {}
    rows = db.query(RulePath).filter(RulePath.id.in_(path_ids)).all()
    if len(rows) != len(path_ids):
        raise HTTPException(status_code=400, detail="invalid_bound_path_ids")
    if any(row.requirement_id != requirement_id for row in rows):
        raise HTTPException(status_code=400, detail="invalid_bound_path_ids")
    return {row.id: row for row in rows}


def _validate_path_contains_nodes(node_ids: Set[str], bound_paths: List[RulePath]) -> None:
    if not node_ids or not bound_paths:
        return

    for path in bound_paths:
        sequence = set(path.node_sequence.split(",")) if path.node_sequence else set()
        if not node_ids.issubset(sequence):
            raise HTTPException(status_code=400, detail="path_node_mismatch")
