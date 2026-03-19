import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.entities import ProductDoc, ProductDocChunk, Project, Requirement
from app.services.llm_client import LLMClient
from app.services.prompts.module_analysis import (
    MODULE_ANALYSIS_SYSTEM_PROMPT,
    MODULE_ANALYSIS_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)


@dataclass
class ModuleAnalysisResult:
    matched_modules: List[str] = field(default_factory=list)
    related_modules: List[str] = field(default_factory=list)
    module_analysis: str = ""


def _build_module_catalog(chunks: List[ProductDocChunk]) -> str:
    """Build a numbered module catalog from chunk titles (deduplicated)."""
    seen = set()
    lines: List[str] = []
    for chunk in chunks:
        title = chunk.title
        if title in seen or title == "(intro)":
            continue
        seen.add(title)
        lines.append("- {0}".format(title))
    return "\n".join(lines) if lines else "(empty)"


def analyze_requirement_modules(
    db: Session,
    requirement: Requirement,
    llm_client: Optional[Any] = None,
) -> Optional[ModuleAnalysisResult]:
    """Use LLM to identify which product modules a requirement touches."""
    project = db.query(Project).filter(Project.id == requirement.project_id).first()
    if not project or not project.product_code:
        return None

    doc = db.query(ProductDoc).filter(
        ProductDoc.product_code == project.product_code
    ).first()
    if not doc:
        return None

    chunks = (
        db.query(ProductDocChunk)
        .filter(ProductDocChunk.product_doc_id == doc.id)
        .order_by(ProductDocChunk.sort_order)
        .all()
    )
    if not chunks:
        return None

    module_catalog = _build_module_catalog(chunks)
    if module_catalog == "(empty)":
        return None

    provider = os.getenv("ANALYZER_PROVIDER", "mock").lower()
    if provider != "llm":
        return _mock_module_analysis(chunks, requirement.raw_text)

    try:
        llm = llm_client or LLMClient()
        user_prompt = MODULE_ANALYSIS_USER_TEMPLATE.format(
            module_catalog=module_catalog,
            requirement_text=requirement.raw_text,
        )
        payload = llm.chat_with_json(
            system_prompt=MODULE_ANALYSIS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return _parse_module_analysis(payload, chunks)
    except Exception as exc:
        logger.warning(
            "Module analysis LLM failed (%s: %s), returning empty result",
            type(exc).__name__, exc,
        )
        return ModuleAnalysisResult()


def _parse_module_analysis(
    payload: Any,
    chunks: List[ProductDocChunk],
) -> ModuleAnalysisResult:
    if not isinstance(payload, dict):
        return ModuleAnalysisResult()

    valid_titles = {c.title for c in chunks}

    matched = payload.get("matched_modules", [])
    if not isinstance(matched, list):
        matched = []
    matched = [t for t in matched if isinstance(t, str) and t in valid_titles]

    related = payload.get("related_modules", [])
    if not isinstance(related, list):
        related = []
    related = [t for t in related if isinstance(t, str) and t in valid_titles and t not in matched]

    analysis = str(payload.get("module_analysis", ""))

    return ModuleAnalysisResult(
        matched_modules=matched,
        related_modules=related,
        module_analysis=analysis,
    )


def _mock_module_analysis(
    chunks: List[ProductDocChunk],
    requirement_text: str,
) -> ModuleAnalysisResult:
    """Lightweight keyword-based mock when LLM is unavailable."""
    from app.services.product_doc_service import _extract_keywords_from_text

    req_keywords = set(kw.lower() for kw in _extract_keywords_from_text(requirement_text))
    if not req_keywords:
        titles = [c.title for c in chunks[:2] if c.title != "(intro)"]
        return ModuleAnalysisResult(
            matched_modules=titles,
            related_modules=[],
            module_analysis="mock: no keywords extracted",
        )

    scored = []
    seen_titles = set()
    for chunk in chunks:
        if chunk.title in seen_titles or chunk.title == "(intro)":
            continue
        seen_titles.add(chunk.title)
        title_words = set(kw.lower() for kw in _extract_keywords_from_text(chunk.title))
        overlap = len(req_keywords & title_words)
        if overlap > 0:
            scored.append((overlap, chunk.title))

    scored.sort(key=lambda x: x[0], reverse=True)
    matched = [t for _, t in scored[:3]]
    related = [t for _, t in scored[3:5]]

    return ModuleAnalysisResult(
        matched_modules=matched,
        related_modules=related,
        module_analysis="mock: keyword-overlap based module matching",
    )
