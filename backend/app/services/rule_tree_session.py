import difflib
import json
import threading
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import (
    NodeStatus,
    NodeType,
    Requirement,
    RiskItem,
    RiskLevel,
    RuleNode,
    RuleTreeMessage,
    RuleTreeSession,
    RuleTreeSessionStatus,
)
from app.services.llm_client import LLMClient
from app.services.prompts.architecture import (
    VISION_SYSTEM_PROMPT,
    VISION_USER_TEMPLATE,
)
from app.services.prompts.rule_tree_session import (
    GENERATE_SYSTEM_PROMPT,
    GENERATE_USER_TEMPLATE,
    INCREMENTAL_UPDATE_USER_TEMPLATE,
    REVIEW_USER_PROMPT,
)
from app.services.rule_path_service import sync_rule_paths

_NODE_TYPE_ALIASES = {
    "root": "root",
    "condition": "condition",
    "branch": "branch",
    "action": "action",
    "exception": "exception",
    "根节点": "root",
    "根": "root",
    "条件": "condition",
    "分支": "branch",
    "动作": "action",
    "异常": "exception",
}

_RISK_LEVEL_ALIASES = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "严重": "critical",
    "高": "high",
    "中": "medium",
    "低": "low",
}

_IN_PROGRESS_SESSION_STATUSES = {
    RuleTreeSessionStatus.generating,
    RuleTreeSessionStatus.reviewing,
    RuleTreeSessionStatus.saving,
}


class RuleTreeSessionConflictError(ValueError):
    pass


_STAGE_PROGRESS = {
    RuleTreeSessionStatus.generating.value: ("正在生成规则树", 45),
    RuleTreeSessionStatus.reviewing.value: ("正在复核规则树", 80),
    RuleTreeSessionStatus.saving.value: ("正在保存规则树", 95),
    RuleTreeSessionStatus.completed.value: ("规则树生成完成", 100),
    RuleTreeSessionStatus.failed.value: ("规则树生成失败", 100),
}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _to_node_type(value: str) -> NodeType:
    normalized = _NODE_TYPE_ALIASES.get((value or "").strip().lower()) or _NODE_TYPE_ALIASES.get((value or "").strip())
    if not normalized:
        normalized = "branch"
    try:
        return NodeType(normalized)
    except Exception:
        return NodeType.branch


def _to_risk_level(value: str) -> RiskLevel:
    normalized = _RISK_LEVEL_ALIASES.get((value or "").strip().lower()) or _RISK_LEVEL_ALIASES.get((value or "").strip())
    if not normalized:
        normalized = "medium"
    try:
        return RiskLevel(normalized)
    except Exception:
        return RiskLevel.medium


def _normalize_tree_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"decision_tree": {"nodes": []}}

    decision_tree = payload.get("decision_tree")
    if not isinstance(decision_tree, dict):
        decision_tree = {"nodes": payload.get("nodes", [])}

    raw_nodes = decision_tree.get("nodes")
    if not isinstance(raw_nodes, list):
        raw_nodes = []

    normalized_nodes: List[Dict[str, Any]] = []
    used_ids = set()
    for idx, raw_node in enumerate(raw_nodes, start=1):
        if not isinstance(raw_node, dict):
            continue
        node_id = str(raw_node.get("id") or "dt_{0}".format(idx)).strip() or "dt_{0}".format(idx)
        if node_id in used_ids:
            node_id = "{0}_{1}".format(node_id, idx)
        used_ids.add(node_id)

        node_type = _NODE_TYPE_ALIASES.get(str(raw_node.get("type", "")).strip().lower()) or _NODE_TYPE_ALIASES.get(
            str(raw_node.get("type", "")).strip()
        )
        node_type = node_type or ("root" if len(normalized_nodes) == 0 else "branch")

        risk_level = _RISK_LEVEL_ALIASES.get(str(raw_node.get("risk_level", "")).strip().lower()) or _RISK_LEVEL_ALIASES.get(
            str(raw_node.get("risk_level", "")).strip()
        )
        risk_level = risk_level or "medium"

        normalized_nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "content": str(raw_node.get("content") or "未命名节点").strip() or "未命名节点",
                "parent_id": raw_node.get("parent_id"),
                "risk_level": risk_level,
            }
        )

    if normalized_nodes:
        root_id = normalized_nodes[0]["id"]
        normalized_nodes[0]["type"] = "root"
        normalized_nodes[0]["parent_id"] = None
        seen_ids = {root_id}
        for node in normalized_nodes[1:]:
            parent_id = node.get("parent_id")
            if not parent_id or parent_id not in seen_ids:
                node["parent_id"] = root_id
            if node.get("type") == "root":
                node["type"] = "condition"
            seen_ids.add(node["id"])

    return {"decision_tree": {"nodes": normalized_nodes}}


def _append_message(
    db: Session,
    session_id: int,
    role: str,
    content: str,
    message_type: str,
    tree_snapshot: Optional[Dict[str, Any]] = None,
) -> RuleTreeMessage:
    msg = RuleTreeMessage(
        session_id=session_id,
        role=role,
        content=content,
        message_type=message_type,
        tree_snapshot=_json_dumps(tree_snapshot) if tree_snapshot is not None else None,
    )
    db.add(msg)
    db.flush()
    return msg


def _compute_tree_diff_summary(node_changes: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"added": 0, "deleted": 0, "modified": 0, "unchanged": 0}
    for item in node_changes:
        status = item.get("status")
        if status in summary:
            summary[status] += 1
    return summary


def compute_tree_diff(old_tree: Dict[str, Any], new_tree: Dict[str, Any]) -> Dict[str, Any]:
    old_nodes = (old_tree or {}).get("decision_tree", {}).get("nodes", [])
    new_nodes = (new_tree or {}).get("decision_tree", {}).get("nodes", [])
    old_map = {node.get("id"): node for node in old_nodes if isinstance(node, dict) and node.get("id")}
    new_map = {node.get("id"): node for node in new_nodes if isinstance(node, dict) and node.get("id")}

    all_ids = sorted(set(old_map.keys()) | set(new_map.keys()))
    node_changes: List[Dict[str, Any]] = []

    for node_id in all_ids:
        old_node = old_map.get(node_id)
        new_node = new_map.get(node_id)
        if old_node and not new_node:
            node_changes.append({"id": node_id, "status": "deleted", "previous": old_node, "current": None})
            continue
        if new_node and not old_node:
            node_changes.append({"id": node_id, "status": "added", "previous": None, "current": new_node})
            continue
        changed_fields = []
        for field in ["type", "content", "risk_level", "parent_id"]:
            if (old_node or {}).get(field) != (new_node or {}).get(field):
                changed_fields.append(field)
        if changed_fields:
            node_changes.append(
                {
                    "id": node_id,
                    "status": "modified",
                    "previous": old_node,
                    "current": new_node,
                    "changed_fields": changed_fields,
                }
            )
        else:
            node_changes.append({"id": node_id, "status": "unchanged", "previous": old_node, "current": new_node})

    return {
        "summary": _compute_tree_diff_summary(node_changes),
        "node_changes": node_changes,
    }


def compute_requirement_diff(old_text: str, new_text: str) -> str:
    diff = difflib.unified_diff(
        (old_text or "").splitlines(),
        (new_text or "").splitlines(),
        fromfile="旧版需求",
        tofile="新版需求",
        lineterm="",
    )
    return "\n".join(diff)


def _regenerate_paths(db: Session, requirement_id: int) -> None:
    sync_rule_paths(db, requirement_id)


def _import_tree_to_requirement(db: Session, requirement_id: int, tree_json: Dict[str, Any]) -> int:
    existing_nodes = (
        db.query(RuleNode)
        .filter(
            RuleNode.requirement_id == requirement_id,
            RuleNode.status != NodeStatus.deleted,
        )
        .all()
    )
    for node in existing_nodes:
        node.status = NodeStatus.deleted
        node.version += 1
    db.query(RiskItem).filter(RiskItem.requirement_id == requirement_id).delete()
    db.flush()

    nodes = (tree_json or {}).get("decision_tree", {}).get("nodes", [])
    id_map: Dict[str, str] = {}
    pending_nodes = list(nodes)
    imported = 0

    while pending_nodes:
        progressed = False
        next_round = []
        for item in pending_nodes:
            source_parent_id = item.get("parent_id")
            if source_parent_id and source_parent_id not in id_map:
                next_round.append(item)
                continue

            node = RuleNode(
                id=str(uuid.uuid4()),
                requirement_id=requirement_id,
                parent_id=id_map.get(source_parent_id),
                node_type=_to_node_type(item.get("type", "branch")),
                content=str(item.get("content") or "").strip() or "未命名节点",
                risk_level=_to_risk_level(item.get("risk_level", "medium")),
                status=NodeStatus.active,
            )
            db.add(node)
            db.flush()
            id_map[item.get("id") or str(imported + 1)] = node.id
            imported += 1
            progressed = True

        if not progressed:
            for item in next_round:
                node = RuleNode(
                    id=str(uuid.uuid4()),
                    requirement_id=requirement_id,
                    parent_id=None,
                    node_type=_to_node_type(item.get("type", "branch")),
                    content=str(item.get("content") or "").strip() or "未命名节点",
                    risk_level=_to_risk_level(item.get("risk_level", "medium")),
                    status=NodeStatus.active,
                )
                db.add(node)
                db.flush()
                imported += 1
            break

        pending_nodes = next_round

    _regenerate_paths(db, requirement_id)
    return imported


def _get_session_with_requirement(db: Session, session_id: int) -> Tuple[RuleTreeSession, Requirement]:
    session = db.query(RuleTreeSession).filter(RuleTreeSession.id == session_id).first()
    if not session:
        raise ValueError("session not found")
    requirement = db.query(Requirement).filter(Requirement.id == session.requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")
    return session, requirement


def create_session(db: Session, requirement_id: int, title: str) -> RuleTreeSession:
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    session = RuleTreeSession(
        requirement_id=requirement_id,
        title=(title or "规则树会话").strip() or "规则树会话",
        status=RuleTreeSessionStatus.active,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, requirement_id: int) -> List[RuleTreeSession]:
    return (
        db.query(RuleTreeSession)
        .filter(RuleTreeSession.requirement_id == requirement_id)
        .order_by(RuleTreeSession.id.desc())
        .all()
    )


def get_session_detail(db: Session, session_id: int) -> Tuple[RuleTreeSession, List[RuleTreeMessage]]:
    session = db.query(RuleTreeSession).filter(RuleTreeSession.id == session_id).first()
    if not session:
        raise ValueError("session not found")
    messages = (
        db.query(RuleTreeMessage)
        .filter(RuleTreeMessage.session_id == session_id)
        .order_by(RuleTreeMessage.id.asc())
        .all()
    )
    return session, messages


def build_messages_for_llm(db: Session, session_id: int, limit: int = 12) -> List[Dict[str, str]]:
    messages = (
        db.query(RuleTreeMessage)
        .filter(RuleTreeMessage.session_id == session_id)
        .order_by(RuleTreeMessage.id.asc())
        .all()
    )
    history = messages[-max(limit, 0) :] if limit > 0 else []
    return [{"role": item.role, "content": item.content} for item in history]


def _vision_preprocess(llm: Any, image_path: str, description: str) -> str:
    """Extract architecture understanding from a flowchart image via vision LLM."""
    image_url = llm.image_to_base64_url(image_path)
    user_prompt = VISION_USER_TEMPLATE.format(description=description or "无")
    user_content = [
        {"type": "text", "text": user_prompt},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]
    understanding = llm.chat_with_vision(
        system_prompt=VISION_SYSTEM_PROMPT, user_content=user_content
    )
    return (understanding or description or "")[:4000]


def _persist_progress(
    db: Session,
    session: RuleTreeSession,
    *,
    status: RuleTreeSessionStatus,
    last_error: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> None:
    progress_message, progress_percent = _STAGE_PROGRESS[status.value]
    session.status = status
    session.progress_stage = status.value
    session.progress_message = progress_message
    session.progress_percent = progress_percent
    session.last_error = last_error
    if session.current_task_started_at is None:
        session.current_task_started_at = datetime.utcnow()
    if status in {RuleTreeSessionStatus.completed, RuleTreeSessionStatus.failed, RuleTreeSessionStatus.interrupted}:
        session.current_task_finished_at = datetime.utcnow()
    else:
        session.current_task_finished_at = None
    db.commit()
    db.refresh(session)
    if progress_callback:
        progress_callback(status.value)


def run_rule_tree_generation_task(
    session_id: int,
    requirement_text: str,
    title: Optional[str] = None,
    image_path: Optional[str] = None,
    llm_client: Optional[Any] = None,
    db_session_factory: Callable[[], Session] = SessionLocal,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> None:
    db = db_session_factory()
    try:
        session, _ = _get_session_with_requirement(db, session_id)
        if title:
            session.title = title.strip() or session.title
        _persist_progress(
            db,
            session,
            status=RuleTreeSessionStatus.generating,
            progress_callback=progress_callback,
        )

        llm = llm_client or LLMClient()
        effective_text = requirement_text
        if image_path:
            vision_understanding = _vision_preprocess(llm, image_path, requirement_text)
            effective_text = (
                "{req}\n\n【流程图解析结果】\n{vision}".format(req=requirement_text, vision=vision_understanding)
            )

        wrapped_requirement = GENERATE_USER_TEMPLATE.format(requirement_text=effective_text)
        base_messages = [
            {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
            {"role": "user", "content": wrapped_requirement},
        ]
        generated_payload = llm.chat_with_messages(base_messages, response_format={"type": "json_object"})
        generated_tree = _normalize_tree_payload(generated_payload)
        session.generated_tree_snapshot = _json_dumps(generated_tree)
        _append_message(db, session_id, "user", requirement_text, "generate")
        _append_message(db, session_id, "assistant", _json_dumps(generated_tree), "generate", tree_snapshot=generated_tree)
        _persist_progress(
            db,
            session,
            status=RuleTreeSessionStatus.reviewing,
            progress_callback=progress_callback,
        )

        review_messages = base_messages + [
            {"role": "assistant", "content": _json_dumps(generated_tree)},
            {"role": "user", "content": REVIEW_USER_PROMPT},
        ]
        reviewed_payload = llm.chat_with_messages(review_messages, response_format={"type": "json_object"})
        reviewed_tree = _normalize_tree_payload(reviewed_payload)
        session.reviewed_tree_snapshot = _json_dumps(reviewed_tree)
        _append_message(db, session_id, "user", REVIEW_USER_PROMPT, "review")
        _append_message(db, session_id, "assistant", _json_dumps(reviewed_tree), "review", tree_snapshot=reviewed_tree)
        _persist_progress(
            db,
            session,
            status=RuleTreeSessionStatus.saving,
            progress_callback=progress_callback,
        )
        _persist_progress(
            db,
            session,
            status=RuleTreeSessionStatus.completed,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        db.rollback()
        session = db.query(RuleTreeSession).filter(RuleTreeSession.id == session_id).first()
        if session:
            _persist_progress(
                db,
                session,
                status=RuleTreeSessionStatus.failed,
                last_error=str(exc),
                progress_callback=progress_callback,
            )
        else:
            db.close()
            raise
    finally:
        db.close()


def _launch_generation_worker(
    *,
    session_id: int,
    requirement_text: str,
    title: Optional[str],
    image_path: Optional[str],
    llm_client: Optional[Any] = None,
) -> None:
    worker = threading.Thread(
        target=run_rule_tree_generation_task,
        kwargs={
            "session_id": session_id,
            "requirement_text": requirement_text,
            "title": title,
            "image_path": image_path,
            "llm_client": llm_client,
            "db_session_factory": SessionLocal,
        },
        daemon=True,
    )
    worker.start()


def generate_with_review(
    db: Session,
    session_id: int,
    requirement_text: str,
    title: Optional[str] = None,
    image_path: Optional[str] = None,
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    session, _ = _get_session_with_requirement(db, session_id)
    if title:
        session.title = title.strip() or session.title

    llm = llm_client or LLMClient()

    effective_text = requirement_text
    if image_path:
        vision_understanding = _vision_preprocess(llm, image_path, requirement_text)
        effective_text = (
            "{req}\n\n【流程图解析结果】\n{vision}"
            .format(req=requirement_text, vision=vision_understanding)
        )

    wrapped_requirement = GENERATE_USER_TEMPLATE.format(requirement_text=effective_text)
    base_messages = [
        {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
        {"role": "user", "content": wrapped_requirement},
    ]
    generated_payload = llm.chat_with_messages(base_messages, response_format={"type": "json_object"})
    generated_tree = _normalize_tree_payload(generated_payload)

    review_messages = base_messages + [
        {"role": "assistant", "content": _json_dumps(generated_tree)},
        {"role": "user", "content": REVIEW_USER_PROMPT},
    ]
    reviewed_payload = llm.chat_with_messages(review_messages, response_format={"type": "json_object"})
    reviewed_tree = _normalize_tree_payload(reviewed_payload)

    _append_message(db, session_id, "user", requirement_text, "generate")
    _append_message(db, session_id, "assistant", _json_dumps(generated_tree), "generate", tree_snapshot=generated_tree)
    _append_message(db, session_id, "user", REVIEW_USER_PROMPT, "review")
    _append_message(db, session_id, "assistant", _json_dumps(reviewed_tree), "review", tree_snapshot=reviewed_tree)
    db.commit()
    db.refresh(session)

    return {
        "session": session,
        "generated_tree": generated_tree,
        "reviewed_tree": reviewed_tree,
        "diff": compute_tree_diff(generated_tree, reviewed_tree),
    }


def incremental_update(
    db: Session,
    session_id: int,
    new_requirement_text: str,
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    session, _ = _get_session_with_requirement(db, session_id)
    if not session.confirmed_tree_snapshot:
        raise ValueError("confirmed snapshot required before incremental update")

    old_requirement_text = session.requirement_text_snapshot or ""
    base_tree = _json_loads(session.confirmed_tree_snapshot, {"decision_tree": {"nodes": []}})
    requirement_diff = compute_requirement_diff(old_requirement_text, new_requirement_text)

    llm = llm_client or LLMClient()
    user_prompt = INCREMENTAL_UPDATE_USER_TEMPLATE.format(
        old_requirement=old_requirement_text,
        new_requirement=new_requirement_text,
        auto_diff=requirement_diff or "（无差异）",
        current_rule_tree_json=_json_dumps(base_tree),
    )
    messages = [
        {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    updated_payload = llm.chat_with_messages(messages, response_format={"type": "json_object"})
    updated_tree = _normalize_tree_payload(updated_payload)
    node_diff = compute_tree_diff(base_tree, updated_tree)

    _append_message(db, session_id, "user", user_prompt, "incremental_update")
    _append_message(
        db,
        session_id,
        "assistant",
        _json_dumps(updated_tree),
        "incremental_update",
        tree_snapshot=updated_tree,
    )
    db.commit()
    db.refresh(session)

    return {
        "session": session,
        "updated_tree": updated_tree,
        "requirement_diff": requirement_diff,
        "node_diff": node_diff,
    }


def start_generation(
    db: Session,
    session_id: int,
    requirement_text: str,
    title: Optional[str] = None,
    image_path: Optional[str] = None,
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    session, _ = _get_session_with_requirement(db, session_id)
    if session.status in _IN_PROGRESS_SESSION_STATUSES:
        raise RuleTreeSessionConflictError("当前会话生成中，请稍后再试")

    normalized_text = (requirement_text or "").strip()
    if not normalized_text:
        raise ValueError("requirement_text is required")

    if title:
        session.title = title.strip() or session.title

    session.status = RuleTreeSessionStatus.generating
    session.requirement_text_snapshot = normalized_text
    session.progress_stage = RuleTreeSessionStatus.generating.value
    session.progress_message = "已接受生成任务，准备开始生成规则树"
    session.progress_percent = 5
    session.last_error = None
    session.generated_tree_snapshot = None
    session.reviewed_tree_snapshot = None
    session.current_task_started_at = datetime.utcnow()
    session.current_task_finished_at = None
    db.commit()
    db.refresh(session)

    _launch_generation_worker(
        session_id=session.id,
        requirement_text=normalized_text,
        title=session.title,
        image_path=image_path,
        llm_client=llm_client,
    )

    return {
        "accepted": True,
        "session": session,
    }


def confirm_tree(
    db: Session,
    session_id: int,
    tree_json: Dict[str, Any],
    requirement_text: str,
) -> Dict[str, Any]:
    session, _ = _get_session_with_requirement(db, session_id)
    normalized_tree = _normalize_tree_payload(tree_json)
    normalized_text = (requirement_text or "").strip()
    normalized_tree_json = _json_dumps(normalized_tree)

    if (
        session.status == RuleTreeSessionStatus.confirmed
        and (session.confirmed_tree_snapshot or "") == normalized_tree_json
        and (session.requirement_text_snapshot or "") == normalized_text
    ):
        return {"ok": True, "session": session, "imported_nodes": 0}

    imported_nodes = _import_tree_to_requirement(db, session.requirement_id, normalized_tree)
    session.confirmed_tree_snapshot = normalized_tree_json
    session.requirement_text_snapshot = normalized_text
    session.status = RuleTreeSessionStatus.confirmed
    _append_message(
        db,
        session_id,
        "user",
        "confirm",
        "confirm",
        tree_snapshot=normalized_tree,
    )
    db.commit()
    db.refresh(session)
    return {"ok": True, "session": session, "imported_nodes": imported_nodes}
