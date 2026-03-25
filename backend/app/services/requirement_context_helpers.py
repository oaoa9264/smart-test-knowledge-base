"""Pure helpers for requirement context retrieval.

Only depends on models and basic types — no service-layer imports.
"""

from typing import List

from sqlalchemy.orm import Session

from app.models.entities import Requirement, RequirementInput


def list_requirement_inputs(
    db: Session,
    requirement_id: int,
) -> List[RequirementInput]:
    return (
        db.query(RequirementInput)
        .filter(RequirementInput.requirement_id == requirement_id)
        .order_by(RequirementInput.created_at.asc(), RequirementInput.id.asc())
        .all()
    )


def build_product_context_query_text(
    requirement: Requirement,
    inputs: List[RequirementInput],
) -> str:
    parts = [requirement.raw_text or ""]
    for item in inputs:
        content = (item.content or "").strip()
        if not content or content == (requirement.raw_text or "").strip():
            continue
        label = item.source_label or ""
        input_type = item.input_type.value if hasattr(item.input_type, "value") else item.input_type
        parts.append(
            "[{type}]{label_part} {content}".format(
                type=input_type,
                label_part="（来源：{0}）".format(label) if label else "",
                content=content,
            )
        )
    return "\n".join(part for part in parts if part.strip())
