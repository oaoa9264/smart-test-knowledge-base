import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.entities import (
    DocUpdateStatus,
    ProductDoc,
    ProductDocChunk,
    ProductDocUpdate,
    RiskItem,
)
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset(
    "的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 自己 这"
    " 他 她 它 们 那 被 从 把 让 用 可以 什么 没 与 及 等 但 又 或 为 对 以 通过 进行 使用 如果"
    " 可以 需要 支持 包括 根据 其中 同时 以及 此时 当前 相关 不同 所有 其他 该 以下 如下".split()
)


def _extract_keywords_from_text(text: str) -> List[str]:
    """Extract keywords from Chinese text using regex-based extraction."""
    text = re.sub(r"[#*\-|`\[\]()（）《》]", " ", text)

    cn_words = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    en_words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)

    keywords = []
    seen = set()
    for w in cn_words + en_words:
        w_lower = w.lower()
        if w_lower in _STOP_WORDS or w_lower in seen or len(w) < 2:
            continue
        seen.add(w_lower)
        keywords.append(w)

    return keywords[:50]


def _parse_markdown_into_chunks(content: str) -> List[Dict[str, Any]]:
    """Split markdown content by ## and ### headings into chunks."""
    lines = content.split("\n")
    chunks: List[Dict[str, Any]] = []
    current_title = ""
    current_lines: List[str] = []
    chunk_index = 0

    for line in lines:
        heading_match = re.match(r"^(#{2,3})\s+(.+)", line)
        if heading_match:
            if current_title and current_lines:
                chunk_text = "\n".join(current_lines).strip()
                if chunk_text:
                    stage_key = "stage_{0}".format(chunk_index)
                    keywords = _extract_keywords_from_text(current_title + " " + chunk_text)
                    chunks.append({
                        "stage_key": stage_key,
                        "title": current_title,
                        "content": chunk_text,
                        "sort_order": chunk_index,
                        "keywords": ",".join(keywords),
                    })
                    chunk_index += 1
            current_title = heading_match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_title and current_lines:
        chunk_text = "\n".join(current_lines).strip()
        if chunk_text:
            stage_key = "stage_{0}".format(chunk_index)
            keywords = _extract_keywords_from_text(current_title + " " + chunk_text)
            chunks.append({
                "stage_key": stage_key,
                "title": current_title,
                "content": chunk_text,
                "sort_order": chunk_index,
                "keywords": ",".join(keywords),
            })

    return chunks


def import_product_doc(
    db: Session,
    file_path: str,
    product_code: str,
    name: str,
    description: str = "",
) -> ProductDoc:
    """Import a Markdown product document, parse into chunks and store."""
    if not os.path.isfile(file_path):
        raise ValueError("file not found: {0}".format(file_path))

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    existing = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if existing:
        db.query(ProductDocChunk).filter(ProductDocChunk.product_doc_id == existing.id).delete()
        existing.name = name
        existing.description = description
        existing.file_path = file_path
        existing.version = existing.version + 1
        existing.updated_at = datetime.utcnow()
        doc = existing
    else:
        doc = ProductDoc(
            product_code=product_code,
            name=name,
            description=description,
            file_path=file_path,
            version=1,
        )
        db.add(doc)
    db.flush()

    raw_chunks = _parse_markdown_into_chunks(content)
    for chunk_data in raw_chunks:
        chunk = ProductDocChunk(
            product_doc_id=doc.id,
            stage_key=chunk_data["stage_key"],
            title=chunk_data["title"],
            content=chunk_data["content"],
            sort_order=chunk_data["sort_order"],
            keywords=chunk_data["keywords"],
        )
        db.add(chunk)

    db.commit()
    db.refresh(doc)
    return doc


def import_product_doc_from_text(
    db: Session,
    content: str,
    product_code: str,
    name: str,
    description: str = "",
    file_path: str = "",
) -> ProductDoc:
    """Import from raw text content instead of a file path."""
    existing = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if existing:
        db.query(ProductDocChunk).filter(ProductDocChunk.product_doc_id == existing.id).delete()
        existing.name = name
        existing.description = description
        existing.file_path = file_path
        existing.version = existing.version + 1
        existing.updated_at = datetime.utcnow()
        doc = existing
    else:
        doc = ProductDoc(
            product_code=product_code,
            name=name,
            description=description,
            file_path=file_path,
            version=1,
        )
        db.add(doc)
    db.flush()

    raw_chunks = _parse_markdown_into_chunks(content)
    for chunk_data in raw_chunks:
        chunk = ProductDocChunk(
            product_doc_id=doc.id,
            stage_key=chunk_data["stage_key"],
            title=chunk_data["title"],
            content=chunk_data["content"],
            sort_order=chunk_data["sort_order"],
            keywords=chunk_data["keywords"],
        )
        db.add(chunk)

    db.commit()
    db.refresh(doc)
    return doc


def get_relevant_chunks(
    db: Session,
    product_code: str,
    requirement_text: str,
    max_chunks: int = 5,
) -> List[ProductDocChunk]:
    """Match relevant document chunks to a requirement using keyword overlap scoring."""
    doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if not doc:
        return []

    chunks = (
        db.query(ProductDocChunk)
        .filter(ProductDocChunk.product_doc_id == doc.id)
        .order_by(ProductDocChunk.sort_order)
        .all()
    )
    if not chunks:
        return []

    req_keywords = set(kw.lower() for kw in _extract_keywords_from_text(requirement_text))
    if not req_keywords:
        return chunks[:max_chunks]

    base_chunks = []
    scored_chunks: List[Tuple[float, ProductDocChunk]] = []

    for chunk in chunks:
        title_lower = chunk.title.lower()
        is_base = any(kw in title_lower for kw in ("术语", "口径", "总览", "概述", "简介", "背景"))
        if is_base:
            base_chunks.append(chunk)
            continue

        chunk_kw_str = (chunk.keywords or "") + "," + chunk.title
        chunk_keywords = set(kw.lower().strip() for kw in chunk_kw_str.split(",") if kw.strip())
        overlap = len(req_keywords & chunk_keywords)

        title_words = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z_]\w{2,}", chunk.title.lower()))
        title_overlap = len(req_keywords & title_words)
        score = overlap + title_overlap * 2.0

        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)

    remaining_slots = max(0, max_chunks - len(base_chunks))
    top_chunks = [c for _, c in scored_chunks[:remaining_slots]]

    result = base_chunks + top_chunks
    result.sort(key=lambda c: c.sort_order)
    return result


def suggest_doc_update(
    db: Session,
    product_doc_id: int,
    risk_item_id: Optional[str],
    clarification_text: str,
    supplement_text: Optional[str] = None,
    llm_client: Optional[Any] = None,
) -> ProductDocUpdate:
    """Generate an AI-suggested document update based on risk clarification."""
    doc = db.query(ProductDoc).filter(ProductDoc.id == product_doc_id).first()
    if not doc:
        raise ValueError("product doc not found")

    risk: Optional[RiskItem] = None
    query_text = ""

    if risk_item_id:
        risk = db.query(RiskItem).filter(RiskItem.id == risk_item_id).first()
        if not risk:
            raise ValueError("risk item not found")
        query_text = risk.description
    elif supplement_text and supplement_text.strip():
        query_text = supplement_text.strip()
    else:
        raise ValueError("either risk_item_id or supplement_text is required")

    chunks = get_relevant_chunks(db, doc.product_code, query_text, max_chunks=2)
    if not chunks:
        chunks = (
            db.query(ProductDocChunk)
            .filter(ProductDocChunk.product_doc_id == doc.id)
            .order_by(ProductDocChunk.sort_order.asc(), ProductDocChunk.id.asc())
            .limit(2)
            .all()
        )
    chunk = chunks[0] if chunks else None
    original_content = chunk.content if chunk else ""

    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider == "llm":
        try:
            llm = llm_client or LLMClient()
            system_prompt = (
                "你是产品文档维护专家。根据产品澄清说明和原始文档段落，"
                "生成更新后的文档段落。保持原文档的格式和风格，只修改需要变更的部分。"
                '严格输出 JSON 对象，格式为：{{"updated_content": "更新后的段落全文"}}'
            )
            user_prompt = (
                "【风险描述】\n{risk_desc}\n\n"
                "【产品澄清说明】\n{clarification}\n\n"
                "【原始文档段落】\n{original}\n\n"
                "请生成更新后的文档段落："
            ).format(
                risk_desc=query_text,
                clarification=clarification_text,
                original=original_content,
            )
            result = llm.chat_with_json(system_prompt=system_prompt, user_prompt=user_prompt)
            suggested_content = result.get("updated_content", "") if isinstance(result, dict) else str(result)
            if not suggested_content:
                suggested_content = "{original}\n\n【补充说明】{clarification}".format(
                    original=original_content, clarification=clarification_text
                )
        except Exception as exc:
            logger.warning("Doc update LLM failed (%s: %s), using placeholder", type(exc).__name__, exc)
            suggested_content = "{original}\n\n【补充说明】{clarification}".format(
                original=original_content, clarification=clarification_text
            )
    else:
        suggested_content = "{original}\n\n【补充说明】{clarification}".format(
            original=original_content, clarification=clarification_text
        )

    update = ProductDocUpdate(
        product_doc_id=product_doc_id,
        chunk_id=chunk.id if chunk else None,
        risk_item_id=risk_item_id,
        original_content=original_content,
        suggested_content=suggested_content,
        status=DocUpdateStatus.pending,
    )
    db.add(update)
    db.commit()
    db.refresh(update)
    return update


def apply_doc_update(db: Session, update_id: int) -> ProductDocUpdate:
    """Apply a pending doc update: update chunk content, bump version, refresh keywords."""
    update = db.query(ProductDocUpdate).filter(ProductDocUpdate.id == update_id).first()
    if not update:
        raise ValueError("update not found")
    if update.status != DocUpdateStatus.pending:
        raise ValueError("update is not in pending status")

    now = datetime.utcnow()

    if update.chunk_id and update.suggested_content:
        chunk = db.query(ProductDocChunk).filter(ProductDocChunk.id == update.chunk_id).first()
        if chunk:
            chunk.content = update.suggested_content
            chunk.keywords = ",".join(_extract_keywords_from_text(chunk.title + " " + chunk.content))

    doc = db.query(ProductDoc).filter(ProductDoc.id == update.product_doc_id).first()
    if doc:
        doc.version = doc.version + 1
        doc.updated_at = now

    update.status = DocUpdateStatus.approved
    update.reviewed_at = now
    update.applied_at = now
    db.commit()
    db.refresh(update)
    return update


def reject_doc_update(db: Session, update_id: int) -> ProductDocUpdate:
    """Reject a pending doc update."""
    update = db.query(ProductDocUpdate).filter(ProductDocUpdate.id == update_id).first()
    if not update:
        raise ValueError("update not found")
    if update.status != DocUpdateStatus.pending:
        raise ValueError("update is not in pending status")

    update.status = DocUpdateStatus.rejected
    update.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(update)
    return update
