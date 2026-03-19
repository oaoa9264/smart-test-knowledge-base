from fastapi.testclient import TestClient

from typing import List, Optional, Tuple
from uuid import uuid4

from app.core.database import SessionLocal
from app.main import app
from app.models.entities import (
    InputType,
    NodeType,
    Project,
    Requirement,
    RequirementInput,
    RiskLevel,
    RuleNode,
    SourceType,
)
from app.services import effective_requirement_service

client = TestClient(app)


def _create_requirement_with_inputs(
    raw_text: str = "用户提交表单，如果字段为空则给出提示。",
    extra_inputs: Optional[List[Tuple[str, str, Optional[str]]]] = None,
) -> int:
    db = SessionLocal()
    try:
        project = Project(
            name="effective-{0}".format(uuid4().hex[:8]),
            description="effective requirement service test",
        )
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="有效需求测试",
            raw_text=raw_text,
            source_type=SourceType.prd,
        )
        db.add(requirement)
        db.flush()

        if extra_inputs:
            for input_type, content, source_label in extra_inputs:
                db.add(
                    RequirementInput(
                        requirement_id=requirement.id,
                        input_type=InputType(input_type),
                        content=content,
                        source_label=source_label,
                    )
                )

        db.commit()
        return requirement.id
    finally:
        db.close()


def _create_requirement_with_root_and_snapshot(
    raw_text: str = "用户提交表单，如果字段为空则给出提示。",
    extra_inputs: Optional[List[Tuple[str, str, Optional[str]]]] = None,
) -> int:
    requirement_id = _create_requirement_with_inputs(raw_text=raw_text, extra_inputs=extra_inputs)

    db = SessionLocal()
    try:
        db.add(
            RuleNode(
                id="root-{0}".format(uuid4().hex[:8]),
                requirement_id=requirement_id,
                parent_id=None,
                node_type=NodeType.root,
                content="用户提交表单",
                risk_level=RiskLevel.medium,
            )
        )
        db.commit()
        effective_requirement_service.generate_review_snapshot(db=db, requirement_id=requirement_id)
        return requirement_id
    finally:
        db.close()


def test_compute_basis_hash_is_deterministic():
    requirement_id = _create_requirement_with_inputs(
        extra_inputs=[
            ("pm_addendum", "补充说明：提交成功后显示提示。", "pm"),
            ("review_note", "评审备注：需补充异常场景。", "review"),
        ]
    )

    db = SessionLocal()
    try:
        requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
        inputs = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == requirement_id)
            .all()
        )

        first = effective_requirement_service.compute_basis_hash(requirement, inputs)
        second = effective_requirement_service.compute_basis_hash(requirement, inputs)

        assert first == second
        assert first
    finally:
        db.close()


def test_compute_basis_hash_changes_when_raw_requirement_changes():
    requirement_id = _create_requirement_with_inputs(
        extra_inputs=[("pm_addendum", "补充说明：提交成功后显示提示。", "pm")]
    )

    db = SessionLocal()
    try:
        requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
        inputs = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == requirement_id)
            .all()
        )
        first = effective_requirement_service.compute_basis_hash(requirement, inputs)

        requirement.raw_text = "用户提交表单，如果字段为空则禁止提交。"
        db.flush()

        second = effective_requirement_service.compute_basis_hash(requirement, inputs)
        assert first != second
    finally:
        db.close()


def test_compute_basis_hash_changes_when_existing_input_content_changes():
    requirement_id = _create_requirement_with_inputs(
        extra_inputs=[("test_clarification", "测试确认：仅校验手机号。", "risk:1")]
    )

    db = SessionLocal()
    try:
        requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
        existing_input = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == requirement_id)
            .first()
        )
        inputs = [existing_input]
        first = effective_requirement_service.compute_basis_hash(requirement, inputs)

        input_id = existing_input.id
        existing_input.content = "测试确认：所有必填字段都要做空值校验。"
        db.flush()

        same_id_input = db.query(RequirementInput).filter(RequirementInput.id == input_id).first()
        second = effective_requirement_service.compute_basis_hash(requirement, [same_id_input])

        assert same_id_input.id == input_id
        assert first != second
    finally:
        db.close()


def test_generate_review_snapshot_persists_basis_hash():
    requirement_id = _create_requirement_with_inputs(
        extra_inputs=[
            ("pm_addendum", "补充说明：提交成功后显示提示。", "pm"),
            ("test_clarification", "测试确认：空值校验覆盖所有必填字段。", "risk:1"),
        ]
    )

    db = SessionLocal()
    try:
        result = effective_requirement_service.generate_review_snapshot(
            db=db,
            requirement_id=requirement_id,
        )
        snapshot = result["snapshot"]

        requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
        inputs = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == requirement_id)
            .order_by(RequirementInput.created_at.asc(), RequirementInput.id.asc())
            .all()
        )

        expected_hash = effective_requirement_service.compute_basis_hash(requirement, inputs)

        assert snapshot.based_on_input_ids is not None
        assert snapshot.basis_hash == expected_hash
    finally:
        db.close()


def test_get_latest_snapshot_marks_snapshot_stale_after_input_change():
    requirement_id = _create_requirement_with_root_and_snapshot(
        extra_inputs=[("pm_addendum", "补充说明：提交成功后显示提示。", "pm")]
    )

    db = SessionLocal()
    try:
        existing_input = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == requirement_id)
            .first()
        )
        existing_input.content = "补充说明：提交成功后要展示结果页。"
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/requirements/{0}/snapshots/latest".format(requirement_id))
    assert resp.status_code == 200
    assert resp.json()["is_stale"] is True


def test_predev_analysis_rejects_stale_snapshot_with_structured_error():
    requirement_id = _create_requirement_with_root_and_snapshot(
        extra_inputs=[("review_note", "评审备注：需补充异常场景。", "review")]
    )

    db = SessionLocal()
    try:
        requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
        requirement.raw_text = "用户提交表单，如果字段为空则禁止提交并提示。"
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/ai/risks/predev-analyze", json={"requirement_id": requirement_id})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "STALE_SNAPSHOT"


def test_prerelease_requires_snapshot_with_structured_error():
    requirement_id = _create_requirement_with_inputs()

    resp = client.post("/api/ai/risks/prerelease-audit", json={"requirement_id": requirement_id})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "NO_SNAPSHOT"


def test_prerelease_rejects_stale_snapshot_with_structured_error():
    requirement_id = _create_requirement_with_root_and_snapshot(
        extra_inputs=[("test_clarification", "测试确认：仅校验手机号。", "risk:1")]
    )

    db = SessionLocal()
    try:
        existing_input = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == requirement_id)
            .first()
        )
        existing_input.content = "测试确认：所有必填字段都要校验。"
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/ai/risks/prerelease-audit", json={"requirement_id": requirement_id})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "STALE_SNAPSHOT"
