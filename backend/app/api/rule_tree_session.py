import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.rule_tree_session import (
    RuleTreeConfirmPayload,
    RuleTreeConfirmResponse,
    RuleTreeGenerateResponse,
    RuleTreeSessionCreate,
    RuleTreeSessionDetailRead,
    RuleTreeSessionRead,
    RuleTreeUpdatePayload,
    RuleTreeUpdateResponse,
)
from app.services.rule_tree_session import (
    RuleTreeSessionConflictError,
    confirm_tree,
    create_session,
    get_session_detail,
    incremental_update,
    list_sessions,
    start_generation,
)

CURRENT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads", "session_images")


def _save_session_image(upload_file: Optional[UploadFile]) -> Optional[str]:
    if not upload_file or not upload_file.filename:
        return None
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(upload_file.filename)[1] or ".bin"
    filename = "{0}{1}".format(uuid.uuid4().hex, ext)
    abs_path = os.path.join(UPLOAD_DIR, filename)
    with open(abs_path, "wb") as fp:
        fp.write(upload_file.file.read())
    return abs_path


def _cleanup_session_image(image_path: Optional[str]) -> None:
    if not image_path:
        return
    try:
        if os.path.exists(image_path):
            os.remove(image_path)
    except OSError:
        pass

router = APIRouter(prefix="/api/rules/sessions", tags=["rule-tree-sessions"])


@router.post("", response_model=RuleTreeSessionRead, status_code=status.HTTP_201_CREATED)
def create_rule_tree_session(payload: RuleTreeSessionCreate, db: Session = Depends(get_db)):
    try:
        return create_session(db=db, requirement_id=payload.requirement_id, title=payload.title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("", response_model=List[RuleTreeSessionRead])
def list_rule_tree_sessions(requirement_id: int = Query(...), db: Session = Depends(get_db)):
    return list_sessions(db=db, requirement_id=requirement_id)


@router.get("/{session_id}", response_model=RuleTreeSessionDetailRead)
def get_rule_tree_session(session_id: int, db: Session = Depends(get_db)):
    try:
        session, messages = get_session_detail(db=db, session_id=session_id)
        return {"session": session, "messages": messages}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{session_id}/generate", response_model=RuleTreeGenerateResponse)
async def generate_rule_tree(
    session_id: int,
    requirement_text: str = Form(...),
    title: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    image_path: Optional[str] = None
    try:
        image_path = _save_session_image(image)
        return start_generation(
            db=db,
            session_id=session_id,
            requirement_text=requirement_text,
            title=title,
            image_path=image_path,
        )
    except RuleTreeSessionConflictError as exc:
        _cleanup_session_image(image_path)
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        _cleanup_session_image(image_path)
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/update", response_model=RuleTreeUpdateResponse)
def update_rule_tree(session_id: int, payload: RuleTreeUpdatePayload, db: Session = Depends(get_db)):
    try:
        return incremental_update(
            db=db,
            session_id=session_id,
            new_requirement_text=payload.new_requirement_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/confirm", response_model=RuleTreeConfirmResponse)
def confirm_rule_tree(session_id: int, payload: RuleTreeConfirmPayload, db: Session = Depends(get_db)):
    try:
        return confirm_tree(
            db=db,
            session_id=session_id,
            tree_json=payload.tree_json,
            requirement_text=payload.requirement_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
