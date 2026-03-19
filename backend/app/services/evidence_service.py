import logging
import os
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    EvidenceBlock,
    EvidenceCreatedFrom,
    EvidenceStatus,
    EvidenceType,
    ProductDoc,
    ProductDocChunk,
    RiskItem,
)
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_VALID_EVIDENCE_TYPES = {e.value for e in EvidenceType}


def _compute_chunk_content_hash(chunk_title: str, chunk_content: str) -> str:
    payload = "{0}\n{1}".format(chunk_title.strip(), chunk_content.strip())
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def bootstrap_evidence_from_chunks(
    db: Session,
    product_code: str,
    llm_client: Optional[Any] = None,
) -> List[EvidenceBlock]:
    """AI-extract structured evidence blocks from existing ProductDocChunks.

    For each chunk that does not yet have evidence, ask the LLM (or mock)
    to produce zero or more evidence statements.  Results are persisted as
    EvidenceBlock rows with ``created_from=ai_bootstrap``.
    """
    doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if not doc:
        raise ValueError("product doc not found for code: {0}".format(product_code))

    chunks = (
        db.query(ProductDocChunk)
        .filter(ProductDocChunk.product_doc_id == doc.id)
        .order_by(ProductDocChunk.sort_order)
        .all()
    )
    if not chunks:
        return []

    existing_blocks = (
        db.query(EvidenceBlock)
        .filter(
            EvidenceBlock.product_doc_id == doc.id,
            EvidenceBlock.chunk_id.isnot(None),
        )
        .all()
    )
    existing_by_chunk: Dict[int, List[EvidenceBlock]] = {}
    for block in existing_blocks:
        if block.chunk_id is None:
            continue
        existing_by_chunk.setdefault(block.chunk_id, []).append(block)

    new_blocks: List[EvidenceBlock] = []
    for chunk in chunks:
        chunk_hash = _compute_chunk_content_hash(chunk.title, chunk.content)
        chunk_blocks = existing_by_chunk.get(chunk.id, [])
        active_blocks = [block for block in chunk_blocks if block.status != EvidenceStatus.rejected]

        if any(block.chunk_content_hash == chunk_hash for block in active_blocks):
            continue

        for block in active_blocks:
            block.status = EvidenceStatus.rejected

        raw_evidences = _extract_evidence_from_chunk(
            chunk_title=chunk.title,
            chunk_content=chunk.content,
            llm_client=llm_client,
        )

        for ev in raw_evidences:
            evidence_type_str = ev.get("evidence_type", "field_rule")
            if evidence_type_str not in _VALID_EVIDENCE_TYPES:
                evidence_type_str = "field_rule"

            block = EvidenceBlock(
                product_doc_id=doc.id,
                chunk_id=chunk.id,
                evidence_type=EvidenceType(evidence_type_str),
                module_name=ev.get("module_name") or chunk.title,
                statement=ev.get("statement", ""),
                status=EvidenceStatus.draft,
                source_span=ev.get("source_span"),
                chunk_content_hash=chunk_hash,
                created_from=EvidenceCreatedFrom.ai_bootstrap,
            )
            db.add(block)
            new_blocks.append(block)

    db.commit()
    for b in new_blocks:
        db.refresh(b)
    return new_blocks


def create_evidence_from_clarification(
    db: Session,
    risk_item_id: str,
    statement: str,
    evidence_type: str = "field_rule",
    module_name: Optional[str] = None,
) -> EvidenceBlock:
    """Create an evidence block from a risk clarification conclusion.

    This is called when a risk clarification produces a reusable piece of
    product knowledge that should be indexed for future retrieval.
    """
    risk = db.query(RiskItem).filter(RiskItem.id == risk_item_id).first()
    if not risk:
        raise ValueError("risk item not found")

    from app.models.entities import Project, Requirement

    requirement = db.query(Requirement).filter(Requirement.id == risk.requirement_id).first()
    if not requirement:
        raise ValueError("requirement not found")

    project = db.query(Project).filter(Project.id == requirement.project_id).first()
    if not project or not project.product_code:
        raise ValueError("project has no product_code")

    doc = db.query(ProductDoc).filter(ProductDoc.product_code == project.product_code).first()
    if not doc:
        raise ValueError("product doc not found")

    if evidence_type not in _VALID_EVIDENCE_TYPES:
        raise ValueError("invalid evidence_type: {0}".format(evidence_type))

    source_ref = "risk:{0}".format(risk.id)
    block = (
        db.query(EvidenceBlock)
        .filter(
            EvidenceBlock.product_doc_id == doc.id,
            EvidenceBlock.created_from == EvidenceCreatedFrom.risk_clarification,
            EvidenceBlock.source_span == source_ref,
        )
        .order_by(EvidenceBlock.id.asc())
        .first()
    )
    if block is None:
        block = EvidenceBlock(
            product_doc_id=doc.id,
            chunk_id=None,
            evidence_type=EvidenceType(evidence_type),
            module_name=module_name or "",
            statement=statement,
            status=EvidenceStatus.draft,
            source_span=source_ref,
            created_from=EvidenceCreatedFrom.risk_clarification,
        )
        db.add(block)
    else:
        block.evidence_type = EvidenceType(evidence_type)
        block.statement = statement
        block.status = EvidenceStatus.draft
        block.source_span = source_ref
        if module_name is not None:
            block.module_name = module_name
    db.commit()
    db.refresh(block)
    return block


def get_relevant_evidence(
    db: Session,
    product_code: str,
    requirement_text: str,
    module_names: Optional[List[str]] = None,
    evidence_types: Optional[List[str]] = None,
    max_items: int = 10,
) -> List[EvidenceBlock]:
    """Retrieve evidence blocks relevant to a requirement.

    Priority logic:
    1. Filter by module_name if provided (exact match, case-insensitive).
    2. Filter by evidence_type if provided.
    3. Only return non-rejected evidence.
    4. Within matching set, prefer verified > draft.
    5. Keyword overlap scoring as tiebreaker.
    """
    doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if not doc:
        return []

    query = (
        db.query(EvidenceBlock)
        .filter(
            EvidenceBlock.product_doc_id == doc.id,
            EvidenceBlock.status != EvidenceStatus.rejected,
        )
    )

    if evidence_types:
        valid_types = [EvidenceType(t) for t in evidence_types if t in _VALID_EVIDENCE_TYPES]
        if valid_types:
            query = query.filter(EvidenceBlock.evidence_type.in_(valid_types))

    blocks = query.all()
    if not blocks:
        return []

    from app.services.product_doc_service import _extract_keywords_from_text

    req_keywords = set(kw.lower() for kw in _extract_keywords_from_text(requirement_text))
    module_set = {m.lower() for m in (module_names or [])}

    scored: List[tuple] = []
    for block in blocks:
        score = 0.0

        status_bonus = 10.0 if block.status == EvidenceStatus.verified else 0.0
        score += status_bonus

        if module_set and block.module_name:
            if block.module_name.lower() in module_set:
                score += 100.0

        if req_keywords:
            stmt_keywords = set(kw.lower() for kw in _extract_keywords_from_text(block.statement))
            module_kw = set(kw.lower() for kw in _extract_keywords_from_text(block.module_name or ""))
            overlap = len(req_keywords & (stmt_keywords | module_kw))
            score += overlap * 2.0

        if score > 0:
            scored.append((score, block))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return [b for _, b in scored[:max_items]]

    fallback = sorted(
        blocks,
        key=lambda block: (
            1 if block.status == EvidenceStatus.verified else 0,
            block.created_at or datetime.min,
            block.id or 0,
        ),
        reverse=True,
    )
    return fallback[:max_items]


def update_evidence(
    db: Session,
    evidence_id: int,
    statement: Optional[str] = None,
    evidence_type: Optional[str] = None,
    module_name: Optional[str] = None,
) -> EvidenceBlock:
    """Update an evidence block's content fields."""
    block = db.query(EvidenceBlock).filter(EvidenceBlock.id == evidence_id).first()
    if not block:
        raise ValueError("evidence block not found")

    if statement is not None:
        block.statement = statement
    if evidence_type is not None:
        if evidence_type not in _VALID_EVIDENCE_TYPES:
            raise ValueError("invalid evidence_type: {0}".format(evidence_type))
        block.evidence_type = EvidenceType(evidence_type)
    if module_name is not None:
        block.module_name = module_name

    if block.created_from != EvidenceCreatedFrom.manual_edit:
        block.created_from = EvidenceCreatedFrom.manual_edit

    db.commit()
    db.refresh(block)
    return block


def verify_evidence(db: Session, evidence_id: int) -> EvidenceBlock:
    """Mark an evidence block as verified."""
    block = db.query(EvidenceBlock).filter(EvidenceBlock.id == evidence_id).first()
    if not block:
        raise ValueError("evidence block not found")
    block.status = EvidenceStatus.verified
    db.commit()
    db.refresh(block)
    return block


def reject_evidence(db: Session, evidence_id: int) -> EvidenceBlock:
    """Mark an evidence block as rejected."""
    block = db.query(EvidenceBlock).filter(EvidenceBlock.id == evidence_id).first()
    if not block:
        raise ValueError("evidence block not found")
    block.status = EvidenceStatus.rejected
    db.commit()
    db.refresh(block)
    return block


# ---------------------------------------------------------------------------
# LLM / Mock helpers
# ---------------------------------------------------------------------------

_EVIDENCE_BOOTSTRAP_SYSTEM_PROMPT = """
你是产品知识结构化专家。给定一段产品文档的标题和内容，
请从中提取可作为测试依据的结构化证据条目。

每条证据是一个独立的、可被引用的规则或约束陈述。

证据类型：
- precondition: 操作的前置条件
- state_rule: 状态流转规则
- field_rule: 字段取值规则或约束
- permission_rule: 权限控制规则
- exception_rule: 异常处理规则
- terminology: 业务术语定义

严格输出 JSON 对象，不要输出任何额外文本：
{
  "evidences": [
    {
      "evidence_type": "state_rule",
      "statement": "订单状态从'待审核'只能流转到'已通过'或'已拒绝'，不可跳过审核直接到'已发货'",
      "source_span": "原文中的对应片段（可选）"
    }
  ]
}

约束：
1) 只提取有明确测试价值的规则，跳过纯描述性文本
2) statement 用一句话说清规则，不要超过两句
3) 如果该段落没有可提取的证据，返回空数组 {"evidences": []}
""".strip()

_EVIDENCE_BOOTSTRAP_USER_TEMPLATE = """
【文档章节标题】
{chunk_title}

【文档内容】
{chunk_content}
""".strip()


def _extract_evidence_from_chunk(
    chunk_title: str,
    chunk_content: str,
    llm_client: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider != "llm":
        return _mock_evidence_extraction(chunk_title, chunk_content)

    try:
        llm = llm_client or LLMClient()
        user_prompt = _EVIDENCE_BOOTSTRAP_USER_TEMPLATE.format(
            chunk_title=chunk_title,
            chunk_content=chunk_content,
        )
        payload = llm.chat_with_json(
            system_prompt=_EVIDENCE_BOOTSTRAP_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return _parse_evidence_payload(payload, chunk_title)
    except Exception as exc:
        logger.warning(
            "Evidence extraction LLM failed (%s: %s), returning empty result",
            type(exc).__name__, exc,
        )
        return []


def _parse_evidence_payload(
    payload: Any,
    chunk_title: str,
) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    evidences = payload.get("evidences", [])
    if not isinstance(evidences, list):
        return []

    result = []
    for ev in evidences:
        if not isinstance(ev, dict):
            continue
        statement = str(ev.get("statement", "")).strip()
        if not statement:
            continue
        evidence_type = str(ev.get("evidence_type", "field_rule"))
        if evidence_type not in _VALID_EVIDENCE_TYPES:
            evidence_type = "field_rule"
        result.append({
            "evidence_type": evidence_type,
            "module_name": chunk_title,
            "statement": statement,
            "source_span": ev.get("source_span"),
        })
    return result


def _mock_evidence_extraction(
    chunk_title: str,
    chunk_content: str,
) -> List[Dict[str, Any]]:
    if not chunk_content.strip() or chunk_title == "(intro)":
        return []

    evidences = []

    if any(kw in chunk_content for kw in ("状态", "流转", "审核", "审批")):
        evidences.append({
            "evidence_type": "state_rule",
            "module_name": chunk_title,
            "statement": "{title}模块存在状态流转规则约束".format(title=chunk_title),
            "source_span": None,
        })

    if any(kw in chunk_content for kw in ("必填", "校验", "格式", "长度", "范围")):
        evidences.append({
            "evidence_type": "field_rule",
            "module_name": chunk_title,
            "statement": "{title}模块存在字段校验规则".format(title=chunk_title),
            "source_span": None,
        })

    if any(kw in chunk_content for kw in ("权限", "角色", "管理员", "操作员")):
        evidences.append({
            "evidence_type": "permission_rule",
            "module_name": chunk_title,
            "statement": "{title}模块存在权限控制规则".format(title=chunk_title),
            "source_span": None,
        })

    if any(kw in chunk_content for kw in ("前置条件", "前提", "需要先", "必须先")):
        evidences.append({
            "evidence_type": "precondition",
            "module_name": chunk_title,
            "statement": "{title}模块存在前置条件约束".format(title=chunk_title),
            "source_span": None,
        })

    if not evidences:
        evidences.append({
            "evidence_type": "field_rule",
            "module_name": chunk_title,
            "statement": "{title}模块的业务规则".format(title=chunk_title),
            "source_span": None,
        })

    return evidences
