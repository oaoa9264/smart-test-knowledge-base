from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.rule_tree_session import (
    RuleTreeConfirmPayload,
    RuleTreeConfirmResponse,
    RuleTreeGeneratePayload,
    RuleTreeGenerateResponse,
    RuleTreeSessionCreate,
    RuleTreeSessionDetailRead,
    RuleTreeSessionRead,
    RuleTreeUpdatePayload,
    RuleTreeUpdateResponse,
)
from app.services.rule_tree_session import (
    confirm_tree,
    create_session,
    generate_with_review,
    get_session_detail,
    incremental_update,
    list_sessions,
)

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
def generate_rule_tree(session_id: int, payload: RuleTreeGeneratePayload, db: Session = Depends(get_db)):
    try:
        return generate_with_review(
            db=db,
            session_id=session_id,
            requirement_text=payload.requirement_text,
            title=payload.title,
        )
    except ValueError as exc:
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
