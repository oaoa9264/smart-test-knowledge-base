import json
from fastapi.testclient import TestClient

from typing import List, Optional, Tuple
from uuid import uuid4

from app.core.database import SessionLocal
from app.main import app
from app.models.entities import (
    AnalysisStage,
    EffectiveRequirementField,
    EffectiveRequirementSnapshot,
    InputType,
    NodeType,
    ProductDoc,
    ProductDocChunk,
    Project,
    Requirement,
    RequirementInput,
    RiskLevel,
    SnapshotStatus,
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


def _create_requirement_with_product_context(
    *,
    product_code: str,
    raw_text: str = "用户提交表单，如果字段为空则给出提示。",
    extra_inputs: Optional[List[Tuple[str, str, Optional[str]]]] = None,
    matched_chains: Optional[List[str]] = None,
) -> int:
    db = SessionLocal()
    try:
        project = Project(
            name="effective-pc-{0}".format(uuid4().hex[:8]),
            description="effective requirement product context test",
            product_code=product_code,
        )
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="有效需求产品知识测试",
            raw_text=raw_text,
            source_type=SourceType.prd,
            matched_chains=json.dumps(matched_chains, ensure_ascii=False) if matched_chains else None,
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


def test_build_review_product_context_skips_module_analysis_when_matched_chains_exist(monkeypatch):
    product_code = "review-chain-{0}".format(uuid4().hex[:8])

    db = SessionLocal()
    try:
        doc = ProductDoc(product_code=product_code, name="Review Context Product", description="d")
        db.add(doc)
        db.flush()
        db.add(
            ProductDocChunk(
                product_doc_id=doc.id,
                stage_key="stage_0",
                title="系统事实档案",
                content="事实档案内容",
                sort_order=0,
                chain_key="overview",
            )
        )
        db.commit()
    finally:
        db.close()

    requirement_id = _create_requirement_with_product_context(
        product_code=product_code,
        matched_chains=["send-report"],
        extra_inputs=[("pm_addendum", "补充：需要支持失败重试。", "pm")],
    )

    db = SessionLocal()
    try:
        requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
        inputs = effective_requirement_service.list_requirement_inputs(db, requirement_id)

        captured = {}

        def _boom(*args, **kwargs):
            raise AssertionError("module analysis should not run when matched_chains exist")

        def _fake_chain_chunks(db, product_code, requirement_text, *, matched_chains, max_chunks, matched_modules, related_modules, use_evidence=True):
            del db, product_code, max_chunks, use_evidence
            captured["requirement_text"] = requirement_text
            captured["matched_chains"] = matched_chains
            captured["matched_modules"] = matched_modules
            captured["related_modules"] = related_modules
            return [type("Chunk", (), {"title": "系统事实档案", "content": "事实档案内容"})()]

        monkeypatch.setattr(effective_requirement_service, "analyze_requirement_modules", _boom)
        monkeypatch.setattr(effective_requirement_service, "get_chain_aware_chunks", _fake_chain_chunks)

        context = effective_requirement_service._build_review_product_context(
            db,
            requirement,
            inputs,
        )

        assert context == "### 系统事实档案\n事实档案内容"
        assert captured["matched_chains"] == ["send-report"]
        assert captured["matched_modules"] is None
        assert captured["related_modules"] is None
    finally:
        db.close()


def test_build_review_product_context_uses_formal_inputs_in_retrieval_query(monkeypatch):
    product_code = "review-inputs-{0}".format(uuid4().hex[:8])

    db = SessionLocal()
    try:
        doc = ProductDoc(product_code=product_code, name="Review Inputs Product", description="d")
        db.add(doc)
        db.flush()
        db.add(
            ProductDocChunk(
                product_doc_id=doc.id,
                stage_key="stage_0",
                title="提现流程",
                content="提现相关说明",
                sort_order=0,
                chain_key="overview",
            )
        )
        db.commit()
    finally:
        db.close()

    requirement_id = _create_requirement_with_product_context(
        product_code=product_code,
        raw_text="用户发起提现申请。",
        extra_inputs=[
            ("pm_addendum", "补充：提现失败后要展示失败原因。", "pm"),
            ("review_note", "评审：单笔提现金额不能超过5万。", "review"),
        ],
    )

    db = SessionLocal()
    try:
        requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
        inputs = effective_requirement_service.list_requirement_inputs(db, requirement_id)

        captured = {}

        def _fake_module_analysis(*args, **kwargs):
            del args, kwargs
            return type(
                "ModuleResult",
                (),
                {"matched_modules": ["提现流程"], "related_modules": ["异常处理"]},
            )()

        def _fake_chain_chunks(db, product_code, requirement_text, *, matched_chains, max_chunks, matched_modules, related_modules, use_evidence=True):
            del db, product_code, matched_chains, max_chunks, matched_modules, related_modules, use_evidence
            captured["requirement_text"] = requirement_text
            return [type("Chunk", (), {"title": "提现流程", "content": "提现相关说明"})()]

        monkeypatch.setattr(effective_requirement_service, "analyze_requirement_modules", _fake_module_analysis)
        monkeypatch.setattr(effective_requirement_service, "get_chain_aware_chunks", _fake_chain_chunks)

        effective_requirement_service._build_review_product_context(
            db,
            requirement,
            inputs,
        )

        assert "用户发起提现申请。" in captured["requirement_text"]
        assert "补充：提现失败后要展示失败原因。" in captured["requirement_text"]
        assert "评审：单笔提现金额不能超过5万。" in captured["requirement_text"]
    finally:
        db.close()


def test_parse_review_payload_drops_rollout_strategy_field():
    payload = {
        "summary": "摘要",
        "fields": [
            {
                "field_key": "goal",
                "value": "保留的目标",
                "derivation": "explicit",
                "confidence": 0.95,
                "source_refs": "原始需求",
            },
            {
                "field_key": "rollout_strategy",
                "value": "灰度上线后再全量",
                "derivation": "explicit",
                "confidence": 0.8,
                "source_refs": "评审备注",
            },
        ],
        "risks": [],
    }

    parsed = effective_requirement_service._parse_review_payload(payload)

    assert [field["field_key"] for field in parsed["fields"]] == ["goal"]
    assert all(field["value"] != "灰度上线后再全量" for field in parsed["fields"])


def test_latest_snapshot_api_hides_rollout_strategy_fields():
    requirement_id = _create_requirement_with_inputs()

    db = SessionLocal()
    try:
        snapshot = EffectiveRequirementSnapshot(
            requirement_id=requirement_id,
            stage=AnalysisStage.review,
            status=SnapshotStatus.draft,
            summary="测试快照",
        )
        db.add(snapshot)
        db.flush()

        db.add(
            EffectiveRequirementField(
                snapshot_id=snapshot.id,
                field_key="goal",
                value="展示主目标",
                sort_order=0,
            )
        )
        db.add(
            EffectiveRequirementField(
                snapshot_id=snapshot.id,
                field_key="rollout_strategy",
                value="先灰度后全量",
                sort_order=1,
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/requirements/{0}/snapshots/latest".format(requirement_id))

    assert resp.status_code == 200
    payload = resp.json()
    assert [field["field_key"] for field in payload["fields"]] == ["goal"]
    assert all(field["value"] != "先灰度后全量" for field in payload["fields"])


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
