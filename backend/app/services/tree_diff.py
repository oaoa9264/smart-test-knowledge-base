import difflib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.entities import NodeStatus, Requirement, RuleNode, RuleTreeMessage, RuleTreeSession
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_LLM_DIFF_SUMMARY_SYSTEM_PROMPT = """
你是测试规则树版本分析专家。你会拿到 v1 和 v2 的完整上下文（需求文本、规则树节点、会话历史）。
请输出一段中文详细总结，重点覆盖：
1) 关键流程变化（新增/删除/修改）
2) 风险变化（风险等级变化、潜在回归点）
3) 对测试设计的影响（建议新增/回归的测试关注点）
要求：
- 只返回 JSON 对象
- 字段固定为 summary
- summary 必须是一个完整段落，不要分点
""".strip()

_LLM_SEMANTIC_DIFF_SYSTEM_PROMPT = """
你是测试规则树版本对比专家。你会拿到同一需求在不同版本下独立生成的两棵规则树（v1 和 v2）。
两棵树由 AI 各自独立生成，节点 ID 不存在对应关系，你需要从业务流程语义层面理解并对比。

请严格按以下 JSON 格式输出，不要输出其它内容：
{
  "flow_changes": [
    {
      "change_type": "added 或 removed 或 modified",
      "description": "用业务语言描述变更，不要出现节点 ID",
      "detail": "可选，更详细的说明",
      "impact": "low 或 medium 或 high"
    }
  ],
  "summary": "一句话总结两个版本的主要差异",
  "risk_notes": "可选，需要关注的回归风险"
}

关键约束：
1. 只输出实际变化的部分，不要描述未变化的流程
2. description 用业务语言，禁止出现节点 ID 或 UUID
3. 按变更影响从 high 到 low 排序
4. 如果两个版本的流程本质相同（只是措辞差异），flow_changes 留空数组，summary 标注为"无实质变化"
5. change_type 只能是 added / removed / modified 三选一
6. impact 只能是 low / medium / high 三选一
""".strip()


def _node_type_value(node: RuleNode) -> str:
    return node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)


def _risk_level_value(node: RuleNode) -> str:
    return node.risk_level.value if hasattr(node.risk_level, "value") else str(node.risk_level)


def _normalize_content(content: str) -> str:
    return (content or "").strip()


def _to_diff_item(node: RuleNode) -> Dict[str, Optional[str]]:
    return {
        "node_id": node.id,
        "node_type": _node_type_value(node),
        "content": node.content,
        "risk_level": _risk_level_value(node),
        "parent_id": node.parent_id,
    }


def _changed_fields(previous: RuleNode, current: RuleNode) -> List[str]:
    fields: List[str] = []
    if _node_type_value(previous) != _node_type_value(current):
        fields.append("node_type")
    if _normalize_content(previous.content) != _normalize_content(current.content):
        fields.append("content")
    if _risk_level_value(previous) != _risk_level_value(current):
        fields.append("risk_level")
    if (previous.parent_id or None) != (current.parent_id or None):
        fields.append("parent_id")
    return fields


def _exact_key(node: RuleNode) -> Tuple[str, str]:
    return _node_type_value(node), _normalize_content(node.content)


def _content_similarity(left: RuleNode, right: RuleNode) -> float:
    return difflib.SequenceMatcher(None, _normalize_content(left.content), _normalize_content(right.content)).ratio()


def _serialize_requirement_context(
    db: Session,
    requirement_id: int,
    message_limit: int = 16,
) -> Dict[str, Any]:
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id == requirement_id, RuleNode.status != NodeStatus.deleted)
        .order_by(RuleNode.id.asc())
        .all()
    )

    latest_session = (
        db.query(RuleTreeSession)
        .filter(RuleTreeSession.requirement_id == requirement_id)
        .order_by(RuleTreeSession.updated_at.desc(), RuleTreeSession.id.desc())
        .first()
    )

    session_messages: List[Dict[str, Any]] = []
    if latest_session:
        messages = (
            db.query(RuleTreeMessage)
            .filter(RuleTreeMessage.session_id == latest_session.id)
            .order_by(RuleTreeMessage.id.asc())
            .all()
        )
        history = messages[-max(message_limit, 0) :] if message_limit > 0 else []
        for item in history:
            session_messages.append(
                {
                    "role": item.role,
                    "message_type": item.message_type,
                    "content": item.content,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
            )

    return {
        "requirement": {
            "id": requirement.id,
            "title": requirement.title,
            "version": int(requirement.version or 1),
            "raw_text": requirement.raw_text,
        },
        "nodes": [_to_diff_item(node) for node in nodes],
        "latest_session": {
            "id": latest_session.id,
            "title": latest_session.title,
            "status": latest_session.status.value if hasattr(latest_session.status, "value") else str(latest_session.status),
        }
        if latest_session
        else None,
        "session_history": session_messages,
    }


def _serialize_tree_for_llm(db: Session, requirement_id: int) -> str:
    """Serialize a rule tree into a compact indented text representation for LLM consumption."""
    nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id == requirement_id, RuleNode.status != NodeStatus.deleted)
        .order_by(RuleNode.id.asc())
        .all()
    )

    children_map: Dict[Optional[str], List[RuleNode]] = {}
    for node in nodes:
        children_map.setdefault(node.parent_id, []).append(node)

    node_id_set = {node.id for node in nodes}
    roots = [n for n in nodes if not n.parent_id or n.parent_id not in node_id_set]

    lines: List[str] = []

    def _walk(node: RuleNode, depth: int) -> None:
        indent = "  " * depth
        node_type = _node_type_value(node)
        risk = _risk_level_value(node)
        content = _normalize_content(node.content)
        lines.append(f"{indent}- [{node_type}] {content} (风险: {risk})")
        for child in children_map.get(node.id, []):
            _walk(child, depth + 1)

    for root in roots:
        _walk(root, 0)

    return "\n".join(lines) if lines else "(空树)"


def diff_trees_with_llm(db: Session, old_requirement_id: int, new_requirement_id: int) -> Dict[str, Any]:
    """Use LLM to perform semantic-level diff between two rule tree versions."""
    old_requirement = db.query(Requirement).filter(Requirement.id == old_requirement_id).first()
    new_requirement = db.query(Requirement).filter(Requirement.id == new_requirement_id).first()
    if not old_requirement or not new_requirement:
        raise ValueError("requirement not found")

    v1_tree = _serialize_tree_for_llm(db, old_requirement_id)
    v2_tree = _serialize_tree_for_llm(db, new_requirement_id)

    user_prompt = (
        "请对比以下两个版本的规则树，找出实质性的流程差异，返回 JSON：\n\n"
        f"【v1 规则树（v{int(old_requirement.version or 1)}）】\n{v1_tree}\n\n"
        f"【v2 规则树（v{int(new_requirement.version or 1)}）】\n{v2_tree}"
    )

    llm = LLMClient()
    payload = llm.chat_with_messages(
        [
            {"role": "system", "content": _LLM_SEMANTIC_DIFF_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    flow_changes = payload.get("flow_changes") or []
    summary = str(payload.get("summary") or "").strip()
    risk_notes = (payload.get("risk_notes") or None)
    if isinstance(risk_notes, str):
        risk_notes = risk_notes.strip() or None

    valid_change_types = {"added", "removed", "modified"}
    valid_impacts = {"low", "medium", "high"}
    sanitized_changes = []
    for change in flow_changes:
        if not isinstance(change, dict):
            continue
        ct = str(change.get("change_type", "")).strip()
        if ct not in valid_change_types:
            continue
        imp = str(change.get("impact", "medium")).strip()
        if imp not in valid_impacts:
            imp = "medium"
        sanitized_changes.append({
            "change_type": ct,
            "description": str(change.get("description", "")).strip(),
            "detail": (str(change.get("detail", "")).strip() or None),
            "impact": imp,
        })

    impact_order = {"high": 0, "medium": 1, "low": 2}
    sanitized_changes.sort(key=lambda c: impact_order.get(c["impact"], 1))

    return {
        "base_version": int(old_requirement.version or 1),
        "compare_version": int(new_requirement.version or 1),
        "flow_changes": sanitized_changes,
        "summary": summary or "无实质变化",
        "risk_notes": risk_notes,
    }


def diff_summary_with_llm(db: Session, old_requirement_id: int, new_requirement_id: int) -> Dict[str, Any]:
    old_requirement = db.query(Requirement).filter(Requirement.id == old_requirement_id).first()
    new_requirement = db.query(Requirement).filter(Requirement.id == new_requirement_id).first()
    if not old_requirement or not new_requirement:
        raise ValueError("requirement not found")

    base_context = _serialize_requirement_context(db=db, requirement_id=old_requirement_id)
    compare_context = _serialize_requirement_context(db=db, requirement_id=new_requirement_id)

    user_prompt = """请基于以下上下文对比两个规则树版本，并返回 JSON：
{{
  "summary": "<一段详细中文总结>"
}}

【v1 上下文】
{base_context}

【v2 上下文】
{compare_context}
""".format(
        base_context=json.dumps(base_context, ensure_ascii=False),
        compare_context=json.dumps(compare_context, ensure_ascii=False),
    )

    llm = LLMClient()
    payload = llm.chat_with_messages(
        [
            {"role": "system", "content": _LLM_DIFF_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    summary = str((payload or {}).get("summary") or "").strip()
    if not summary:
        raise ValueError("llm summary is empty")

    return {
        "base_version": int(old_requirement.version or 1),
        "compare_version": int(new_requirement.version or 1),
        "summary": summary,
    }


def diff_trees(db: Session, old_requirement_id: int, new_requirement_id: int) -> Dict:
    old_requirement = db.query(Requirement).filter(Requirement.id == old_requirement_id).first()
    new_requirement = db.query(Requirement).filter(Requirement.id == new_requirement_id).first()
    if not old_requirement or not new_requirement:
        raise ValueError("requirement not found")

    old_nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id == old_requirement_id, RuleNode.status != NodeStatus.deleted)
        .all()
    )
    new_nodes = (
        db.query(RuleNode)
        .filter(RuleNode.requirement_id == new_requirement_id, RuleNode.status != NodeStatus.deleted)
        .all()
    )

    matched_old: set = set()
    matched_new: set = set()
    node_changes: List[Dict] = []
    summary = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}

    exact_candidates: Dict[Tuple[str, str], List[int]] = {}
    for new_idx, new_node in enumerate(new_nodes):
        exact_candidates.setdefault(_exact_key(new_node), []).append(new_idx)

    for old_idx, old_node in enumerate(old_nodes):
        key = _exact_key(old_node)
        candidate_indexes = exact_candidates.get(key, [])
        if not candidate_indexes:
            continue
        new_idx = candidate_indexes.pop(0)
        matched_old.add(old_idx)
        matched_new.add(new_idx)
        current = new_nodes[new_idx]
        changed = _changed_fields(old_node, current)
        if changed:
            status = "modified"
            summary["modified"] += 1
        else:
            status = "unchanged"
            summary["unchanged"] += 1
        node_changes.append(
            {
                "status": status,
                "previous": _to_diff_item(old_node),
                "current": _to_diff_item(current),
                "changed_fields": changed or None,
            }
        )

    unmatched_old_indexes = [idx for idx in range(len(old_nodes)) if idx not in matched_old]
    unmatched_new_indexes = [idx for idx in range(len(new_nodes)) if idx not in matched_new]

    for old_idx in unmatched_old_indexes[:]:
        old_node = old_nodes[old_idx]
        best_new_idx: Optional[int] = None
        best_score = 0.0
        for new_idx in unmatched_new_indexes:
            new_node = new_nodes[new_idx]
            if _node_type_value(old_node) != _node_type_value(new_node):
                continue
            score = _content_similarity(old_node, new_node)
            if score > best_score:
                best_score = score
                best_new_idx = new_idx

        if best_new_idx is None or best_score <= 0.8:
            continue

        unmatched_old_indexes.remove(old_idx)
        unmatched_new_indexes.remove(best_new_idx)
        current = new_nodes[best_new_idx]
        changed = _changed_fields(old_node, current)
        if not changed:
            changed = ["content"]
        node_changes.append(
            {
                "status": "modified",
                "previous": _to_diff_item(old_node),
                "current": _to_diff_item(current),
                "changed_fields": changed,
            }
        )
        summary["modified"] += 1

    for old_idx in unmatched_old_indexes:
        old_node = old_nodes[old_idx]
        node_changes.append(
            {
                "status": "removed",
                "previous": _to_diff_item(old_node),
                "current": None,
                "changed_fields": None,
            }
        )
        summary["removed"] += 1

    for new_idx in unmatched_new_indexes:
        new_node = new_nodes[new_idx]
        node_changes.append(
            {
                "status": "added",
                "previous": None,
                "current": _to_diff_item(new_node),
                "changed_fields": None,
            }
        )
        summary["added"] += 1

    return {
        "base_version": int(old_requirement.version or 1),
        "compare_version": int(new_requirement.version or 1),
        "summary": summary,
        "node_changes": node_changes,
    }
