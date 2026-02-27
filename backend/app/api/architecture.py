import json
import os
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import (
    AnalysisStatus,
    ArchitectureAnalysis,
    NodeStatus,
    NodeType,
    Project,
    Requirement,
    RiskLevel,
    RuleNode,
    RulePath,
    SourceType,
    TestCase,
)
from app.schemas.architecture import (
    ArchitectureAnalysisRead,
    ArchitectureAnalyzeResponse,
    ArchitectureImportOptions,
    ArchitectureImportResult,
)
from app.services.architecture_analyzer import get_analyzer_provider
from app.services.rule_engine import derive_rule_paths

router = APIRouter(prefix="/api/ai/architecture", tags=["architecture"])

CURRENT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads", "architecture")


def _ensure_upload_dir() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _save_upload_file(upload_file) -> Optional[str]:
    if not upload_file or not getattr(upload_file, "filename", None):
        return None

    _ensure_upload_dir()
    ext = os.path.splitext(upload_file.filename)[1] or ".bin"
    filename = "{0}{1}".format(uuid.uuid4().hex, ext)
    abs_path = os.path.join(UPLOAD_DIR, filename)

    with open(abs_path, "wb") as fp:
        fp.write(upload_file.file.read())

    return "/uploads/architecture/{0}".format(filename)


def _serialize_analysis(row: ArchitectureAnalysis) -> Dict:
    parsed = None
    if row.analysis_result:
        parsed = json.loads(row.analysis_result)
    return {
        "id": row.id,
        "project_id": row.project_id,
        "requirement_id": row.requirement_id,
        "title": row.title,
        "image_path": row.image_path,
        "description_text": row.description_text,
        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
        "created_at": row.created_at,
        "result": parsed,
    }


def _to_node_type(value: str) -> NodeType:
    try:
        return NodeType(value)
    except Exception:
        return NodeType.branch


def _to_risk_level(value: str) -> RiskLevel:
    try:
        return RiskLevel(value)
    except Exception:
        return RiskLevel.medium


def _regenerate_paths(db: Session, requirement_id: int):
    db.query(RulePath).filter(RulePath.requirement_id == requirement_id).delete()

    nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id == requirement_id, RuleNode.status != NodeStatus.deleted)
        .all()
    )
    node_dicts = [{"id": n.id, "parent_id": n.parent_id} for n in nodes]

    paths = derive_rule_paths(node_dicts)
    for seq in paths:
        db.add(
            RulePath(
                id=str(uuid.uuid4()),
                requirement_id=requirement_id,
                node_sequence=",".join(seq),
            )
        )
    db.commit()


@router.post("/analyze", response_model=ArchitectureAnalyzeResponse, status_code=status.HTTP_201_CREATED)
async def analyze_architecture(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    project_id_raw = form.get("project_id")
    if not project_id_raw:
        raise HTTPException(status_code=400, detail="project_id is required")

    try:
        project_id = int(project_id_raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="project_id must be integer")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    requirement_id_raw = form.get("requirement_id")
    requirement_id = int(requirement_id_raw) if requirement_id_raw else None
    title = str(form.get("title") or "AI 架构拆解")
    description_text = str(form.get("description_text") or "").strip()

    uploaded_file = form.get("image")
    has_image = bool(uploaded_file and getattr(uploaded_file, "filename", None))
    if not description_text and not has_image:
        raise HTTPException(status_code=400, detail="description_text or image is required")

    image_path = _save_upload_file(uploaded_file)

    provider = get_analyzer_provider()
    result = provider.analyze(image_path=image_path, description=description_text, title=title)
    analysis_mode = provider.get_analysis_mode()
    persisted_result = {**result, "analysis_mode": analysis_mode}

    analysis = ArchitectureAnalysis(
        project_id=project_id,
        requirement_id=requirement_id,
        title=title,
        image_path=image_path,
        description_text=description_text,
        analysis_result=json.dumps(persisted_result, ensure_ascii=False),
        status=AnalysisStatus.completed,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return {"id": analysis.id, **persisted_result}


@router.get("/{analysis_id}", response_model=ArchitectureAnalysisRead)
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.query(ArchitectureAnalysis).filter(ArchitectureAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="analysis not found")
    return _serialize_analysis(analysis)


@router.post("/{analysis_id}/import", response_model=ArchitectureImportResult)
def import_analysis(
    analysis_id: int,
    payload: ArchitectureImportOptions,
    db: Session = Depends(get_db),
):
    analysis = db.query(ArchitectureAnalysis).filter(ArchitectureAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="analysis not found")
    if not analysis.analysis_result:
        raise HTTPException(status_code=400, detail="analysis result is empty")

    result = json.loads(analysis.analysis_result)

    requirement = None
    if analysis.requirement_id:
        requirement = db.query(Requirement).filter(Requirement.id == analysis.requirement_id).first()

    if not requirement:
        requirement = Requirement(
            project_id=analysis.project_id,
            title="{0} - 架构拆解".format(analysis.title),
            raw_text=analysis.description_text or "",
            source_type=SourceType.flowchart,
        )
        db.add(requirement)
        db.commit()
        db.refresh(requirement)
        analysis.requirement_id = requirement.id
        db.commit()

    imported_rule_nodes = 0
    imported_test_cases = 0
    updated_risk_nodes = 0

    generated_nodes = result.get("decision_tree", {}).get("nodes", [])
    id_map = {}

    if payload.import_decision_tree:
        pending_nodes = generated_nodes[:]
        while pending_nodes:
            progress = False
            next_round = []
            for item in pending_nodes:
                source_parent_id = item.get("parent_id")
                if source_parent_id and source_parent_id not in id_map:
                    next_round.append(item)
                    continue

                node = RuleNode(
                    id=str(uuid.uuid4()),
                    requirement_id=requirement.id,
                    parent_id=id_map.get(source_parent_id),
                    node_type=_to_node_type(item.get("type", "branch")),
                    content=item.get("content", ""),
                    risk_level=_to_risk_level(item.get("risk_level", "medium")),
                    status=NodeStatus.active,
                )
                db.add(node)
                db.flush()
                id_map[item["id"]] = node.id
                imported_rule_nodes += 1
                progress = True

            if not progress:
                break
            pending_nodes = next_round

        db.commit()
        _regenerate_paths(db, requirement.id)

    if payload.import_risk_points:
        if not id_map:
            existing_nodes = (
                db.query(RuleNode).filter(RuleNode.requirement_id == requirement.id, RuleNode.status == NodeStatus.active).all()
            )
            by_content = {n.content: n.id for n in existing_nodes}
            for item in generated_nodes:
                if item.get("content") in by_content:
                    id_map[item["id"]] = by_content[item["content"]]

        for risk_point in result.get("risk_points", []):
            severity = risk_point.get("severity", "medium")
            for source_id in risk_point.get("related_node_ids", []):
                real_id = id_map.get(source_id)
                if not real_id:
                    continue
                node = db.query(RuleNode).filter(RuleNode.id == real_id).first()
                if not node:
                    continue
                node.risk_level = _to_risk_level(severity)
                updated_risk_nodes += 1
        db.commit()

    if payload.import_test_cases:
        for case_data in result.get("test_cases", []):
            case = TestCase(
                project_id=analysis.project_id,
                title=case_data.get("title", "架构拆解生成用例"),
                steps=case_data.get("steps", ""),
                expected_result=case_data.get("expected_result", ""),
                risk_level=_to_risk_level(case_data.get("risk_level", "medium")),
            )

            related_ids = [id_map[node_id] for node_id in case_data.get("related_node_ids", []) if node_id in id_map]
            if related_ids:
                case.bound_rule_nodes = db.query(RuleNode).filter(RuleNode.id.in_(related_ids)).all()

            db.add(case)
            imported_test_cases += 1
        db.commit()

    analysis.status = AnalysisStatus.imported
    db.commit()

    return {
        "analysis_id": analysis.id,
        "requirement_id": requirement.id if requirement else None,
        "imported_rule_nodes": imported_rule_nodes,
        "imported_test_cases": imported_test_cases,
        "updated_risk_nodes": updated_risk_nodes,
    }
