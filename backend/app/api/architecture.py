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
    InputType,
    NodeStatus,
    NodeType,
    Project,
    Requirement,
    RequirementInput,
    RiskLevel,
    RuleNode,
    SourceType,
)
from app.schemas.architecture import (
    ArchitectureAnalysisRead,
    ArchitectureAnalyzeResponse,
    ArchitectureImportOptions,
    ArchitectureImportResult,
)
from app.services.architecture_analyzer import get_analyzer_provider
from app.services.rule_path_service import sync_rule_paths

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


def _resolve_local_image_path(image_path: Optional[str]) -> Optional[str]:
    if not image_path:
        return None

    normalized = image_path.strip()
    if not normalized:
        return None

    if os.path.isabs(normalized) and os.path.exists(normalized):
        return normalized

    if normalized.startswith("/uploads/"):
        return os.path.join(BACKEND_DIR, normalized.lstrip("/"))

    return normalized


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
    sync_rule_paths(db, requirement_id)


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
    requirement_id = None
    if requirement_id_raw:
        try:
            requirement_id = int(requirement_id_raw)
        except ValueError:
            raise HTTPException(status_code=400, detail="requirement_id must be integer")
        requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
        if not requirement:
            raise HTTPException(status_code=404, detail="requirement not found")
        if requirement.project_id != project_id:
            raise HTTPException(status_code=400, detail="invalid project_requirement relation")
    title = str(form.get("title") or "需求拆解")
    description_text = str(form.get("description_text") or "").strip()

    uploaded_file = form.get("image")
    has_image = bool(uploaded_file and getattr(uploaded_file, "filename", None))
    if not description_text and not has_image:
        raise HTTPException(status_code=400, detail="description_text or image is required")

    image_path = _save_upload_file(uploaded_file)

    provider = get_analyzer_provider()
    result = provider.analyze(
        image_path=_resolve_local_image_path(image_path),
        description=description_text,
        title=title,
    )
    analysis_mode = provider.get_analysis_mode()
    llm_provider = provider.get_llm_provider()
    persisted_result = {**result, "analysis_mode": analysis_mode, "llm_provider": llm_provider}

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
    if result.get("llm_status") == "failed" or result.get("analysis_mode") == "llm_failed":
        raise HTTPException(status_code=400, detail="cannot import failed architecture analysis")

    requirement = None
    if analysis.requirement_id:
        requirement = db.query(Requirement).filter(Requirement.id == analysis.requirement_id).first()

    if not requirement:
        requirement = Requirement(
            project_id=analysis.project_id,
            title="{0} - 需求拆解".format(analysis.title),
            raw_text=analysis.description_text or "",
            source_type=SourceType.flowchart,
        )
        db.add(requirement)
        db.flush()
        db.add(
            RequirementInput(
                requirement_id=requirement.id,
                input_type=InputType.raw_requirement,
                content=requirement.raw_text,
                source_label="requirement.raw_text",
            )
        )
        db.commit()
        db.refresh(requirement)
        analysis.requirement_id = requirement.id
        db.commit()

    imported_rule_nodes = 0
    generated_nodes = result.get("decision_tree", {}).get("nodes", [])
    id_map = {}

    if payload.import_decision_tree:
        existing_node_count = (
            db.query(RuleNode)
            .filter(
                RuleNode.requirement_id == requirement.id,
                RuleNode.status != NodeStatus.deleted,
            )
            .count()
        )
        if existing_node_count == 0:
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

    analysis.status = AnalysisStatus.imported
    db.commit()

    return {
        "analysis_id": analysis.id,
        "requirement_id": requirement.id if requirement else None,
        "imported_rule_nodes": imported_rule_nodes,
    }
