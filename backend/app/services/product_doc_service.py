import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.entities import (
    DocUpdateStatus,
    EvidenceBlock,
    EvidenceStatus,
    ProductDoc,
    ProductDocChunk,
    ProductDocUpdate,
    RiskItem,
)
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

def _calc_kw_score(title: str, keywords: str, req_keywords: Set[str]) -> float:
    """Calculate keyword overlap score between a chunk and requirement keywords.

    Pure function — does not depend on ORM objects.
    """
    if not req_keywords:
        return 0.0
    chunk_kw_str = (keywords or "") + "," + title
    chunk_keywords = set(kw.lower().strip() for kw in chunk_kw_str.split(",") if kw.strip())
    overlap = len(req_keywords & chunk_keywords)
    title_words = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z_]\w{2,}", title.lower()))
    title_overlap = len(req_keywords & title_words)
    return overlap + title_overlap * 2.0


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


_CHUNK_MAX_CHARS = 3000


def _parse_markdown_into_chunks(content: str) -> List[Dict[str, Any]]:
    """Split markdown by ## sections, keeping ### subsections together.

    Strategy:
    - A ``##`` heading opens a new primary section; all ``###`` blocks
      underneath it are collected into the same chunk.
    - If a primary section exceeds ``_CHUNK_MAX_CHARS`` it is split at
      ``###`` boundaries, with each sub-chunk retaining ``parent_title``.
    - Content before the first ``##`` heading is emitted as its own chunk.
    """
    lines = content.split("\n")

    sections: List[Dict[str, Any]] = []
    current_h2_title = ""
    current_lines: List[str] = []

    def _flush_section() -> None:
        if not current_lines:
            return
        text = "\n".join(current_lines).strip()
        if text:
            sections.append({
                "title": current_h2_title,
                "content": text,
                "heading_level": 2 if current_h2_title else None,
            })

    for line in lines:
        h2_match = re.match(r"^##\s+(.+)", line)
        if h2_match and not line.startswith("###"):
            _flush_section()
            current_h2_title = h2_match.group(1).strip()
            current_lines = [line]
            continue

        current_lines.append(line)

    _flush_section()

    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for section in sections:
        title = section["title"]
        text = section["content"]
        heading_level = section["heading_level"]

        if len(text) <= _CHUNK_MAX_CHARS:
            keywords = _extract_keywords_from_text(title + " " + text)
            chunks.append({
                "stage_key": "stage_{0}".format(chunk_index),
                "title": title or "(intro)",
                "content": text,
                "sort_order": chunk_index,
                "keywords": ",".join(keywords),
                "parent_title": None,
                "heading_level": heading_level,
            })
            chunk_index += 1
            continue

        sub_sections = re.split(r"(?=^###\s+)", text, flags=re.MULTILINE)
        buf: List[str] = []
        buf_len = 0
        sub_title = title

        for part in sub_sections:
            part_stripped = part.strip()
            if not part_stripped:
                continue

            h3_match = re.match(r"^###\s+(.+)", part_stripped.split("\n", 1)[0])
            if h3_match:
                sub_title = h3_match.group(1).strip()

            if buf and buf_len + len(part_stripped) > _CHUNK_MAX_CHARS:
                merged = "\n\n".join(buf).strip()
                keywords = _extract_keywords_from_text(title + " " + merged)
                chunks.append({
                    "stage_key": "stage_{0}".format(chunk_index),
                    "title": title or "(intro)",
                    "content": merged,
                    "sort_order": chunk_index,
                    "keywords": ",".join(keywords),
                    "parent_title": title if title else None,
                    "heading_level": 3,
                })
                chunk_index += 1
                buf = []
                buf_len = 0

            buf.append(part_stripped)
            buf_len += len(part_stripped)

        if buf:
            merged = "\n\n".join(buf).strip()
            keywords = _extract_keywords_from_text(title + " " + merged)
            is_sub = chunk_index > 0 and any(
                c["parent_title"] == title for c in chunks
            )
            chunks.append({
                "stage_key": "stage_{0}".format(chunk_index),
                "title": title or "(intro)",
                "content": merged,
                "sort_order": chunk_index,
                "keywords": ",".join(keywords),
                "parent_title": title if is_sub else None,
                "heading_level": 3 if is_sub else heading_level,
            })
            chunk_index += 1

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
    _sync_product_doc_chunks(db, doc.id, raw_chunks)

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
    _sync_product_doc_chunks(db, doc.id, raw_chunks)

    db.commit()
    db.refresh(doc)
    return doc


def get_relevant_chunks(
    db: Session,
    product_code: str,
    requirement_text: str,
    max_chunks: int = 5,
    matched_modules: Optional[List[str]] = None,
    related_modules: Optional[List[str]] = None,
    use_evidence: bool = True,
) -> List[ProductDocChunk]:
    """Hybrid retrieval: evidence-first + module-directed + keyword-overlap.

    When *use_evidence* is True (default), evidence blocks are queried
    first.  Chunks that host matching evidence receive a large boost so
    that evidence-backed knowledge is surfaced preferentially.  When no
    evidence is available or insufficient, the original module + keyword
    scoring acts as fallback.
    """
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

    evidence_chunk_ids: Dict[int, float] = {}
    if use_evidence:
        evidence_chunk_ids = _score_chunks_by_evidence(
            db, doc.id, requirement_text, matched_modules,
        )

    req_keywords = set(kw.lower() for kw in _extract_keywords_from_text(requirement_text))

    matched_set = {t.lower() for t in (matched_modules or [])}
    related_set = {t.lower() for t in (related_modules or [])}

    base_chunks: List[ProductDocChunk] = []
    scored_chunks: List[Tuple[float, ProductDocChunk]] = []

    for chunk in chunks:
        title_lower = chunk.title.lower()

        is_base = any(kw in title_lower for kw in ("术语", "口径", "总览", "概述", "简介", "背景"))
        if is_base:
            base_chunks.append(chunk)
            continue

        evidence_score = evidence_chunk_ids.get(chunk.id, 0.0)

        module_score = 0.0
        effective_title = title_lower
        parent_lower = (chunk.parent_title or "").lower()
        if effective_title in matched_set or parent_lower in matched_set:
            module_score = 100.0
        elif effective_title in related_set or parent_lower in related_set:
            module_score = 50.0

        kw_score = _calc_kw_score(chunk.title, chunk.keywords or "", req_keywords)

        total_score = evidence_score + module_score + kw_score
        if total_score > 0:
            scored_chunks.append((total_score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)

    # --- Phase 1: generic-title diversity cap ---
    _GENERIC_TITLES = frozenset(("主要流程", "入口清单", "依赖表"))
    _MAX_GENERIC_PER_TITLE = 2

    generic_counts: Dict[str, int] = {}
    diversity_filtered: List[Tuple[float, ProductDocChunk]] = []
    overflow: List[Tuple[float, ProductDocChunk]] = []

    for score, chunk in scored_chunks:
        title_lower = chunk.title.lower()
        if title_lower in _GENERIC_TITLES:
            count = generic_counts.get(title_lower, 0)
            if count >= _MAX_GENERIC_PER_TITLE:
                overflow.append((score, chunk))
                continue
            generic_counts[title_lower] = count + 1
        diversity_filtered.append((score, chunk))

    top_chunks = [c for _, c in diversity_filtered[:max_chunks]]

    # --- Phase 2: related_modules hard guarantee ---
    related_in_top = any(
        (c.title.lower() in related_set or (c.parent_title or "").lower() in related_set)
        for c in top_chunks
    ) if related_set else True

    if not related_in_top and related_set:
        # Find best qualifying related chunk (must have kw_score > 0 or evidence_score > 0)
        best_related: Optional[ProductDocChunk] = None
        best_related_score = -1.0
        for score, chunk in diversity_filtered[max_chunks:] + overflow:
            title_lower = chunk.title.lower()
            parent_lower = (chunk.parent_title or "").lower()
            if title_lower not in related_set and parent_lower not in related_set:
                continue
            ev = evidence_chunk_ids.get(chunk.id, 0.0)
            kw = _calc_kw_score(chunk.title, chunk.keywords or "", req_keywords)
            if ev > 0 or kw > 0:
                if score > best_related_score:
                    best_related = chunk
                    best_related_score = score

        if best_related is not None:
            # Swap out the weakest generic-title item; if none, skip replacement
            swap_idx = None
            for i in range(len(top_chunks) - 1, -1, -1):
                if top_chunks[i].title.lower() in _GENERIC_TITLES:
                    swap_idx = i
                    break
            if swap_idx is not None:
                top_chunks[swap_idx] = best_related
            else:
                logger.info(
                    "related_modules fallback skipped: no generic-title item to swap out | "
                    "product_code=%s max_chunks=%d related_modules=%s "
                    "best_related_title=%s best_related_score=%.2f "
                    "top_chunk_titles=%s",
                    product_code,
                    max_chunks,
                    list(related_set),
                    best_related.title,
                    best_related_score,
                    [c.title for c in top_chunks],
                )

    remaining_slots = max(0, max_chunks - len(top_chunks))

    seen_ids = set()
    result: List[ProductDocChunk] = []
    for c in top_chunks + base_chunks[:remaining_slots]:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            result.append(c)
    if result:
        return result

    # Cold-start fallback: preserve previous behavior when nothing scores yet.
    for chunk in chunks[:max_chunks]:
        if chunk.id not in seen_ids:
            seen_ids.add(chunk.id)
            result.append(chunk)
    return result


def parse_matched_chains(requirement) -> Optional[List[str]]:
    """Parse the JSON matched_chains column from a Requirement."""
    raw = getattr(requirement, "matched_chains", None)
    if not raw:
        return None
    try:
        chains = json.loads(raw)
        return chains if isinstance(chains, list) and chains else None
    except (json.JSONDecodeError, TypeError):
        return None


_OVERVIEW_CHAIN_KEYS = frozenset({None, "overview"})
_BASE_TITLE_KEYWORDS = frozenset(("术语", "口径", "总览", "概述", "简介", "背景"))


def get_chain_aware_chunks(
    db: Session,
    product_code: str,
    requirement_text: str,
    matched_chains: Optional[List[str]] = None,
    max_chunks: int = 8,
    matched_modules: Optional[List[str]] = None,
    related_modules: Optional[List[str]] = None,
    use_evidence: bool = True,
) -> List[ProductDocChunk]:
    """Three-tier retrieval: overview + user-selected chains + keyword fallback.

    Tier 1: Overview / fact-archive chunks (always included)
    Tier 2: Chunks from user-selected chains + common-concepts
    Tier 3: Keyword-based scoring on remaining chunks (fills remaining slots)

    Falls back to ``get_relevant_chunks`` when *matched_chains* is empty.
    """
    if not matched_chains:
        return get_relevant_chunks(
            db,
            product_code,
            requirement_text,
            max_chunks=max_chunks,
            matched_modules=matched_modules,
            related_modules=related_modules,
            use_evidence=use_evidence,
        )

    doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
    if not doc:
        return []

    all_chunks = (
        db.query(ProductDocChunk)
        .filter(ProductDocChunk.product_doc_id == doc.id)
        .order_by(ProductDocChunk.sort_order)
        .all()
    )
    if not all_chunks:
        return []

    chain_set = set(matched_chains)

    tier1: List[ProductDocChunk] = []
    tier2: List[ProductDocChunk] = []
    tier3_candidates: List[ProductDocChunk] = []

    for chunk in all_chunks:
        ck = chunk.chain_key
        title_lower = chunk.title.lower()

        # Tier 1: overview / base knowledge
        is_overview = ck in _OVERVIEW_CHAIN_KEYS
        is_base = any(kw in title_lower for kw in _BASE_TITLE_KEYWORDS)
        if is_overview or is_base:
            tier1.append(chunk)
            continue

        # Tier 2: user-selected chains + common-concepts
        if ck in chain_set or ck == "common-concepts":
            tier2.append(chunk)
            continue

        # Tier 3 candidates: everything else
        tier3_candidates.append(chunk)

    # Combine tier 1 and tier 2
    combined: List[ProductDocChunk] = []
    seen_ids: Set[int] = set()

    for chunk in tier1 + tier2:
        if chunk.id not in seen_ids:
            seen_ids.add(chunk.id)
            combined.append(chunk)

    remaining_slots = max(0, max_chunks - len(combined))

    # Tier 3: keyword scoring on remaining candidates
    if remaining_slots > 0 and tier3_candidates:
        req_keywords = set(kw.lower() for kw in _extract_keywords_from_text(requirement_text))

        scored: List[Tuple[float, ProductDocChunk]] = []
        for chunk in tier3_candidates:
            if chunk.id in seen_ids:
                continue
            overlap = _calc_kw_score(chunk.title, chunk.keywords or "", req_keywords)
            if overlap > 0:
                scored.append((overlap, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        for _, chunk in scored[:remaining_slots]:
            if chunk.id not in seen_ids:
                seen_ids.add(chunk.id)
                combined.append(chunk)

    return combined[:max_chunks]

def _sync_product_doc_chunks(
    db: Session,
    product_doc_id: int,
    raw_chunks: List[Dict[str, Any]],
) -> None:
    existing_chunks = (
        db.query(ProductDocChunk)
        .filter(ProductDocChunk.product_doc_id == product_doc_id)
        .order_by(ProductDocChunk.sort_order.asc(), ProductDocChunk.id.asc())
        .all()
    )

    remaining_by_id = {chunk.id: chunk for chunk in existing_chunks}
    assigned_chunks: List[Optional[ProductDocChunk]] = [None] * len(raw_chunks)

    for index, chunk_data in enumerate(raw_chunks):
        title = chunk_data["title"]
        parent_title = chunk_data.get("parent_title")
        for chunk in existing_chunks:
            if chunk.id not in remaining_by_id:
                continue
            if chunk.title == title and chunk.parent_title == parent_title:
                assigned_chunks[index] = chunk
                remaining_by_id.pop(chunk.id, None)
                break

    for index, chunk_data in enumerate(raw_chunks):
        if assigned_chunks[index] is not None:
            continue
        stage_key = chunk_data["stage_key"]
        for chunk in existing_chunks:
            if chunk.id not in remaining_by_id:
                continue
            if chunk.stage_key == stage_key:
                assigned_chunks[index] = chunk
                remaining_by_id.pop(chunk.id, None)
                break

    for chunk_data, chunk in zip(raw_chunks, assigned_chunks):
        if chunk is None:
            chunk = ProductDocChunk(product_doc_id=product_doc_id)
            db.add(chunk)

        chunk.stage_key = chunk_data["stage_key"]
        chunk.title = chunk_data["title"]
        chunk.content = chunk_data["content"]
        chunk.sort_order = chunk_data["sort_order"]
        chunk.keywords = chunk_data["keywords"]
        chunk.parent_title = chunk_data.get("parent_title")
        chunk.heading_level = chunk_data.get("heading_level")
        chunk.chain_key = chunk_data.get("chain_key")
        chunk.source_file = chunk_data.get("source_file")

    stale_chunk_ids = list(remaining_by_id.keys())
    if stale_chunk_ids:
        (
            db.query(EvidenceBlock)
            .filter(
                EvidenceBlock.product_doc_id == product_doc_id,
                EvidenceBlock.chunk_id.in_(stale_chunk_ids),
            )
            .update({"chunk_id": None}, synchronize_session=False)
        )

        for chunk in existing_chunks:
            if chunk.id in stale_chunk_ids:
                db.delete(chunk)


def _score_chunks_by_evidence(
    db: Session,
    product_doc_id: int,
    requirement_text: str,
    module_names: Optional[List[str]] = None,
) -> Dict[int, float]:
    """Score chunk IDs based on their associated evidence blocks.

    Returns a dict of ``{chunk_id: bonus_score}`` where chunks hosting
    relevant evidence receive a significant boost.
    """
    from app.models.entities import EvidenceBlock, EvidenceStatus

    blocks = (
        db.query(EvidenceBlock)
        .filter(
            EvidenceBlock.product_doc_id == product_doc_id,
            EvidenceBlock.status != EvidenceStatus.rejected,
            EvidenceBlock.chunk_id.isnot(None),
        )
        .all()
    )
    if not blocks:
        return {}

    req_keywords = set(kw.lower() for kw in _extract_keywords_from_text(requirement_text))
    module_set = {m.lower() for m in (module_names or [])}

    chunk_scores: Dict[int, float] = {}
    for block in blocks:
        score = 0.0

        if block.status == EvidenceStatus.verified:
            score += 20.0

        if module_set and block.module_name and block.module_name.lower() in module_set:
            score += 80.0

        if req_keywords:
            stmt_kw = set(kw.lower() for kw in _extract_keywords_from_text(block.statement))
            mod_kw = set(kw.lower() for kw in _extract_keywords_from_text(block.module_name or ""))
            overlap = len(req_keywords & (stmt_kw | mod_kw))
            score += overlap * 3.0

        if score > 0 and block.chunk_id is not None:
            chunk_scores[block.chunk_id] = chunk_scores.get(block.chunk_id, 0.0) + score

    return chunk_scores


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
        except Exception as exc:
            logger.warning("Doc update LLM failed (%s: %s), returning empty result", type(exc).__name__, exc)
            suggested_content = ""
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


def invalidate_chunk_evidence(db: Session, chunk_id: int) -> None:
    """Reject evidence extracted from a chunk whose content has changed."""
    (
        db.query(EvidenceBlock)
        .filter(
            EvidenceBlock.chunk_id == chunk_id,
            EvidenceBlock.status != EvidenceStatus.rejected,
        )
        .update({"status": EvidenceStatus.rejected}, synchronize_session=False)
    )


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
            invalidate_chunk_evidence(db=db, chunk_id=chunk.id)
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
