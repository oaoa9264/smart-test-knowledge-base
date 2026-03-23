"""Hierarchical knowledge base importer.

Parses the knowledge_base/products/ directory structure and batch-imports
all domain files into ProductDoc + ProductDocChunk records with chain_key
metadata for chain-aware retrieval.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.entities import ProductDoc, ProductDocChunk
from app.services.product_doc_service import (
    _extract_keywords_from_text,
    _parse_markdown_into_chunks,
)

logger = logging.getLogger(__name__)

_OVERVIEW_KEYWORDS = ("fact-archive", "事实档案")
_COMMON_CONCEPTS_KEYWORDS = ("公共概念说明", "跨链路公共概念")


@dataclass
class ChainFileInfo:
    chain_key: str
    display_name: str
    chain_type: str  # "overview" | "chain" | "common-concepts"
    file_path: str  # absolute path


@dataclass
class DomainConfig:
    domain_name: str
    product_code: str
    domain_dir: str  # absolute path
    files: List[ChainFileInfo] = field(default_factory=list)


@dataclass
class ChainInfo:
    chain_key: str
    display_name: str
    chain_type: str
    chunk_count: int


def _derive_chain_type(filename: str) -> str:
    name_lower = filename.lower()
    if any(kw in name_lower for kw in _OVERVIEW_KEYWORDS):
        return "overview"
    if any(kw in filename for kw in _COMMON_CONCEPTS_KEYWORDS):
        return "common-concepts"
    return "chain"


def _derive_chain_key(filename: str, chain_type: str) -> str:
    if chain_type == "overview":
        return "overview"
    if chain_type == "common-concepts":
        return "common-concepts"
    return os.path.splitext(filename)[0]


def _derive_product_code(domain_dir: str, files: List[str]) -> Optional[str]:
    """Extract product_code slug from the fact-archive / 事实档案 filename."""
    for f in files:
        if any(kw in f for kw in _OVERVIEW_KEYWORDS) and f.endswith(".md"):
            name = os.path.splitext(f)[0]
            name = re.sub(r"-fact-archive$", "", name)
            name = re.sub(r"-事实档案$", "", name)
            return name
    # Fallback: use directory name
    return os.path.basename(domain_dir)


def _derive_display_name(filename: str, chain_type: str) -> str:
    """Build a human-readable display name from filename."""
    name = os.path.splitext(filename)[0]
    if chain_type == "overview":
        return "系统事实档案"
    if chain_type == "common-concepts":
        return "跨链路公共概念"
    # Strip domain prefix: everything before the first hyphen
    # e.g. "闪信-发送与回执" → "发送与回执"
    # e.g. "flashservice-send-report" → "send-report" (legacy)
    idx = name.find("-")
    if idx > 0:
        name = name[idx + 1:]
    return name


def parse_knowledge_base_directory(kb_root: str) -> List[DomainConfig]:
    """Scan knowledge_base/products/ and return structured domain configs."""
    if not os.path.isdir(kb_root):
        return []

    domains: List[DomainConfig] = []
    for entry in sorted(os.listdir(kb_root)):
        domain_dir = os.path.join(kb_root, entry)
        if not os.path.isdir(domain_dir):
            continue

        md_files = [f for f in os.listdir(domain_dir) if f.endswith(".md")]
        if not md_files:
            continue

        product_code = _derive_product_code(domain_dir, md_files)
        if not product_code:
            continue

        chain_files = []
        for f in sorted(md_files):
            chain_type = _derive_chain_type(f)
            chain_key = _derive_chain_key(f, chain_type)
            display_name = _derive_display_name(f, chain_type)
            chain_files.append(ChainFileInfo(
                chain_key=chain_key,
                display_name=display_name,
                chain_type=chain_type,
                file_path=os.path.join(domain_dir, f),
            ))

        domains.append(DomainConfig(
            domain_name=entry,
            product_code=product_code,
            domain_dir=domain_dir,
            files=chain_files,
        ))

    return domains


def _read_file_content(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def import_domain(
    db: Session,
    domain: DomainConfig,
) -> ProductDoc:
    """Import a single domain's files into ProductDoc + ProductDocChunks."""
    existing = db.query(ProductDoc).filter(
        ProductDoc.product_code == domain.product_code
    ).first()

    if existing:
        existing.name = domain.domain_name
        existing.version = existing.version + 1
        existing.updated_at = datetime.utcnow()
        doc = existing
    else:
        doc = ProductDoc(
            product_code=domain.product_code,
            name=domain.domain_name,
            description="知识库导入: {0}".format(domain.domain_name),
            version=1,
        )
        db.add(doc)
    db.flush()

    all_chunks: List[Dict[str, Any]] = []
    global_sort = 0

    for chain_file in domain.files:
        content = _read_file_content(chain_file.file_path)
        raw_chunks = _parse_markdown_into_chunks(content)

        rel_path = os.path.relpath(
            chain_file.file_path,
            os.path.dirname(os.path.dirname(chain_file.file_path)),
        )

        for chunk_data in raw_chunks:
            chunk_data["chain_key"] = chain_file.chain_key
            chunk_data["source_file"] = rel_path
            chunk_data["sort_order"] = global_sort
            chunk_data["stage_key"] = "stage_{0}".format(global_sort)
            global_sort += 1
            all_chunks.append(chunk_data)

    _sync_domain_chunks(db, doc.id, all_chunks)
    db.commit()
    db.refresh(doc)

    chunk_count = db.query(ProductDocChunk).filter(
        ProductDocChunk.product_doc_id == doc.id
    ).count()
    logger.info(
        "Imported domain %s (product_code=%s): %d chunks from %d files",
        domain.domain_name,
        domain.product_code,
        chunk_count,
        len(domain.files),
    )
    return doc


def _sync_domain_chunks(
    db: Session,
    product_doc_id: int,
    raw_chunks: List[Dict[str, Any]],
) -> None:
    """Replace all chunks for a product_doc with the new set."""
    from app.models.entities import EvidenceBlock

    # Delete old chunks and detach evidence
    existing_chunk_ids = [
        row[0] for row in
        db.query(ProductDocChunk.id)
        .filter(ProductDocChunk.product_doc_id == product_doc_id)
        .all()
    ]
    if existing_chunk_ids:
        (
            db.query(EvidenceBlock)
            .filter(
                EvidenceBlock.product_doc_id == product_doc_id,
                EvidenceBlock.chunk_id.in_(existing_chunk_ids),
            )
            .update({"chunk_id": None}, synchronize_session=False)
        )
        db.query(ProductDocChunk).filter(
            ProductDocChunk.product_doc_id == product_doc_id
        ).delete(synchronize_session=False)
        db.flush()

    # Insert new chunks
    for chunk_data in raw_chunks:
        chunk = ProductDocChunk(
            product_doc_id=product_doc_id,
            stage_key=chunk_data["stage_key"],
            title=chunk_data["title"],
            content=chunk_data["content"],
            sort_order=chunk_data["sort_order"],
            keywords=chunk_data.get("keywords", ""),
            parent_title=chunk_data.get("parent_title"),
            heading_level=chunk_data.get("heading_level"),
            chain_key=chunk_data.get("chain_key"),
            source_file=chunk_data.get("source_file"),
        )
        db.add(chunk)


def import_all_domains(
    db: Session,
    kb_root: str,
) -> List[ProductDoc]:
    """Scan knowledge_base/products/ and import all domains."""
    domains = parse_knowledge_base_directory(kb_root)
    if not domains:
        logger.warning("No domains found in %s", kb_root)
        return []

    docs = []
    for domain in domains:
        try:
            doc = import_domain(db, domain)
            docs.append(doc)
        except Exception as exc:
            logger.error(
                "Failed to import domain %s: %s",
                domain.domain_name,
                exc,
            )
            db.rollback()
    return docs


def list_chains_for_product(
    db: Session,
    product_code: str,
) -> List[ChainInfo]:
    """Return available chains for a product_code, for the frontend selector."""
    doc = db.query(ProductDoc).filter(
        ProductDoc.product_code == product_code
    ).first()
    if not doc:
        return []

    chunks = (
        db.query(ProductDocChunk)
        .filter(ProductDocChunk.product_doc_id == doc.id)
        .all()
    )

    chain_map: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks:
        key = chunk.chain_key or "overview"
        if key not in chain_map:
            # Derive display name and type from the first chunk of this chain
            if key == "overview" or chunk.chain_key is None:
                chain_type = "overview"
                display_name = "系统事实档案"
            elif key == "common-concepts":
                chain_type = "common-concepts"
                display_name = "跨链路公共概念"
            else:
                chain_type = "chain"
                source = chunk.source_file or ""
                basename = os.path.splitext(os.path.basename(source))[0] if source else key
                display_name = _derive_display_name(basename + ".md", "chain")

            chain_map[key] = {
                "chain_key": key,
                "display_name": display_name,
                "chain_type": chain_type,
                "chunk_count": 0,
            }
        chain_map[key]["chunk_count"] += 1

    result = sorted(
        [ChainInfo(**v) for v in chain_map.values()],
        key=lambda c: (
            0 if c.chain_type == "overview" else 1 if c.chain_type == "chain" else 2,
            c.chain_key,
        ),
    )
    return result
