from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from uuid import uuid4

from app.core.database import SessionLocal
from app.models.entities import (
    AnalysisStage,
    EvidenceBlock,
    EvidenceCreatedFrom,
    EffectiveRequirementField,
    EffectiveRequirementSnapshot,
    InputType,
    NodeType,
    ProductDoc,
    Project,
    Requirement,
    RequirementInput,
    RiskCategory,
    RiskDecision,
    RiskItem,
    RiskLevel,
    RiskSource,
    RiskValidity,
    RuleNode,
    SnapshotStatus,
    SourceType,
)
from app.services import effective_requirement_service, predev_analyzer, prerelease_auditor, risk_service


def _create_requirement_with_root() -> int:
    db = SessionLocal()
    try:
        project = Project(name="risk-{0}".format(uuid4().hex[:8]), description="risk test")
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="风险分析需求",
            raw_text="用户提交表单，如果字段为空则给出提示。",
            source_type=SourceType.prd,
        )
        db.add(requirement)
        db.flush()

        db.add(
            RuleNode(
                id="root-{0}".format(uuid4().hex[:8]),
                requirement_id=requirement.id,
                parent_id=None,
                node_type=NodeType.root,
                content="用户提交表单",
                risk_level=RiskLevel.medium,
            )
        )
        db.commit()
        return requirement.id
    finally:
        db.close()


def test_analyze_risks_merges_overlapping_requests(monkeypatch):
    """Overlapping analyze_risks calls should coalesce: only one LLM call fires."""
    requirement_id = _create_requirement_with_root()
    started_event = Event()
    release_event = Event()
    second_call_event = Event()
    call_count_lock = Lock()
    call_count = {"value": 0}

    fake_risks = [
        {
            "id": "risk_1",
            "related_node_id": None,
            "category": "flow_gap",
            "risk_level": "high",
            "description": "缺少空值处理",
            "suggestion": "补充空值校验",
        },
        {
            "id": "risk_2",
            "related_node_id": None,
            "category": "boundary",
            "risk_level": "medium",
            "description": "缺少长度边界",
            "suggestion": "补充边界值测试",
        },
    ]

    def fake_call_llm_for_risks(raw_text, tree_nodes_text, llm_client=None, product_context=None, module_result=None):
        del raw_text, tree_nodes_text, llm_client, product_context, module_result
        with call_count_lock:
            call_count["value"] += 1
            current_count = call_count["value"]
        if current_count == 1:
            started_event.set()
            release_event.wait(timeout=2)
        else:
            second_call_event.set()
        return list(fake_risks)

    monkeypatch.setattr(risk_service, "_call_llm_for_risks", fake_call_llm_for_risks)

    def run_analysis():
        db = SessionLocal()
        try:
            return risk_service.analyze_risks(db=db, requirement_id=requirement_id)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_one = executor.submit(run_analysis)
        assert started_event.wait(timeout=1), "first analysis never started"

        future_two = executor.submit(run_analysis)
        assert not second_call_event.wait(timeout=0.2), "overlapping analysis should not start a second LLM call"

        release_event.set()
        result_one = future_one.result(timeout=2)
        result_two = future_two.result(timeout=2)

    db = SessionLocal()
    try:
        saved_risks = db.query(RiskItem).filter(RiskItem.requirement_id == requirement_id).all()
    finally:
        db.close()

    assert call_count["value"] == 1
    assert len(result_one) == len(fake_risks)
    assert len(result_two) == len(fake_risks)
    assert len(saved_risks) == len(fake_risks)
    assert {item.description for item in saved_risks} == {item["description"] for item in fake_risks}


def test_ledger_updates_existing_risks_instead_of_recreating(monkeypatch):
    """Running analysis twice with same risks should update last_analysis_at, not create duplicates."""
    requirement_id = _create_requirement_with_root()

    fake_risks = [
        {
            "id": "risk_1",
            "related_node_id": None,
            "category": "flow_gap",
            "risk_level": "high",
            "description": "缺少空值处理",
            "suggestion": "补充空值校验",
        },
    ]

    monkeypatch.setattr(
        risk_service,
        "_call_llm_for_risks",
        lambda *a, **kw: list(fake_risks),
    )

    db = SessionLocal()
    try:
        result_first = risk_service.analyze_risks(db=db, requirement_id=requirement_id)
        first_ids = {r.id for r in result_first}
        first_created_at = {r.id: r.created_at for r in result_first}

        result_second = risk_service.analyze_risks(db=db, requirement_id=requirement_id)
        second_ids = {r.id for r in result_second}

        all_risks = db.query(RiskItem).filter(RiskItem.requirement_id == requirement_id).all()
    finally:
        db.close()

    assert first_ids == second_ids, "same risks should keep the same IDs across runs"
    assert len(all_risks) == 1, "no duplicate risks should exist"
    for r in all_risks:
        assert r.last_analysis_at is not None
        assert r.created_at == first_created_at[r.id], "created_at should not change"


def test_ledger_creates_new_risk_for_different_description(monkeypatch):
    """A new risk description should result in a new RiskItem, not an update."""
    requirement_id = _create_requirement_with_root()

    risks_round1 = [
        {
            "id": "risk_1",
            "related_node_id": None,
            "category": "flow_gap",
            "risk_level": "high",
            "description": "缺少空值处理",
            "suggestion": "补充空值校验",
        },
    ]
    risks_round2 = [
        {
            "id": "risk_1",
            "related_node_id": None,
            "category": "flow_gap",
            "risk_level": "high",
            "description": "缺少空值处理",
            "suggestion": "补充空值校验",
        },
        {
            "id": "risk_new",
            "related_node_id": None,
            "category": "boundary",
            "risk_level": "medium",
            "description": "缺少长度边界检查",
            "suggestion": "增加长度上限校验",
        },
    ]

    call_count = {"value": 0}

    def fake_llm(*a, **kw):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return list(risks_round1)
        return list(risks_round2)

    monkeypatch.setattr(risk_service, "_call_llm_for_risks", fake_llm)

    db = SessionLocal()
    try:
        result1 = risk_service.analyze_risks(db=db, requirement_id=requirement_id)
        assert len(result1) == 1

        risk_service._finish_requirement_analysis(
            requirement_id,
            risk_service._ANALYSIS_STATES.get(requirement_id, risk_service._AnalysisState()),
            None,
        )

        result2 = risk_service.analyze_risks(db=db, requirement_id=requirement_id)
        assert len(result2) == 2

        all_risks = db.query(RiskItem).filter(RiskItem.requirement_id == requirement_id).all()
    finally:
        db.close()

    assert len(all_risks) == 2
    descriptions = {r.description for r in all_risks}
    assert "缺少空值处理" in descriptions
    assert "缺少长度边界检查" in descriptions


def test_new_risks_have_validity_active(monkeypatch):
    """Newly created risks should have validity=active."""
    requirement_id = _create_requirement_with_root()

    monkeypatch.setattr(
        risk_service,
        "_call_llm_for_risks",
        lambda *a, **kw: [
            {
                "id": "r1",
                "related_node_id": None,
                "category": "input_validation",
                "risk_level": "medium",
                "description": "未明确输入为空时的处理逻辑",
                "suggestion": "建议增加空值校验",
            },
        ],
    )

    db = SessionLocal()
    try:
        results = risk_service.analyze_risks(db=db, requirement_id=requirement_id)
    finally:
        db.close()

    assert len(results) == 1
    assert results[0].validity == RiskValidity.active


def test_ledger_reopens_and_refreshes_existing_closed_risk():
    """A matched closed risk should reopen and refresh mutable fields."""
    requirement_id = _create_requirement_with_root()

    db = SessionLocal()
    try:
        existing = RiskItem(
            id=str(uuid4()),
            requirement_id=requirement_id,
            related_node_id=None,
            category=RiskCategory.flow_gap,
            risk_level=RiskLevel.medium,
            risk_source=RiskSource.rule_tree,
            description="缺少空值处理",
            suggestion="旧建议",
            decision=RiskDecision.pending,
            validity=RiskValidity.resolved,
        )
        db.add(existing)
        db.commit()

        result = risk_service.save_risks_to_ledger(
            db=db,
            requirement_id=requirement_id,
            raw_risks=[
                {
                    "category": "flow_gap",
                    "risk_level": "critical",
                    "description": "缺少空值处理",
                    "suggestion": "新建议",
                    "risk_source": "rule_tree",
                }
            ],
            valid_node_ids=set(),
            analysis_stage="pre_dev",
            origin_snapshot_id=123,
        )

        assert len(result) == 1
        db.refresh(existing)
        assert result[0].id == existing.id
        assert existing.validity == RiskValidity.reopened
        assert existing.risk_level == RiskLevel.critical
        assert existing.suggestion == "新建议"
        assert existing.last_seen_snapshot_id == 123
        assert existing.analysis_stage == AnalysisStage.pre_dev
    finally:
        db.close()


def test_clarify_risk_upserts_derived_input_and_evidence():
    """Repeated clarification should update, not duplicate, derived input/evidence."""
    db = SessionLocal()
    try:
        product_code = "clarify-doc-{0}".format(uuid4().hex[:8])
        doc = ProductDoc(product_code=product_code, name="Clarify Doc", description="d")
        db.add(doc)
        db.flush()

        project = Project(
            name="clarify-{0}".format(uuid4().hex[:8]),
            description="clarify test",
            product_code=product_code,
        )
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="澄清需求",
            raw_text="用户提交后需要校验。",
            source_type=SourceType.prd,
        )
        db.add(requirement)
        db.flush()

        risk = RiskItem(
            id=str(uuid4()),
            requirement_id=requirement.id,
            related_node_id=None,
            category=RiskCategory.product_knowledge,
            risk_level=RiskLevel.high,
            risk_source=RiskSource.product_knowledge,
            description="缺少产品规则说明",
            suggestion="补充产品规则",
            decision=RiskDecision.pending,
            validity=RiskValidity.active,
        )
        db.add(risk)
        db.commit()

        risk_service.clarify_risk(db=db, risk_id=risk.id, clarification_text="旧澄清", doc_update_needed=False)
        risk_service.clarify_risk(db=db, risk_id=risk.id, clarification_text="新澄清", doc_update_needed=False)

        inputs = (
            db.query(RequirementInput)
            .filter(
                RequirementInput.requirement_id == requirement.id,
                RequirementInput.input_type == InputType.test_clarification,
                RequirementInput.source_label == "risk:{0}".format(risk.id),
            )
            .all()
        )
        evidences = (
            db.query(EvidenceBlock)
            .filter(
                EvidenceBlock.product_doc_id == doc.id,
                EvidenceBlock.created_from == EvidenceCreatedFrom.risk_clarification,
                EvidenceBlock.source_span == "risk:{0}".format(risk.id),
            )
            .all()
        )

        assert len(inputs) == 1
        assert inputs[0].content == "新澄清"
        assert len(evidences) == 1
        assert evidences[0].statement == "新澄清"
    finally:
        db.close()


def test_delete_risk_cleans_up_clarification_derivatives():
    """Deleting a clarified risk should remove its derived input and evidence rows."""
    db = SessionLocal()
    try:
        product_code = "delete-risk-doc-{0}".format(uuid4().hex[:8])
        doc = ProductDoc(product_code=product_code, name="Delete Risk Doc", description="d")
        db.add(doc)
        db.flush()

        project = Project(
            name="delete-risk-{0}".format(uuid4().hex[:8]),
            description="delete risk test",
            product_code=product_code,
        )
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="删除风险需求",
            raw_text="用户提交后需要校验。",
            source_type=SourceType.prd,
        )
        db.add(requirement)
        db.flush()

        risk = RiskItem(
            id=str(uuid4()),
            requirement_id=requirement.id,
            related_node_id=None,
            category=RiskCategory.product_knowledge,
            risk_level=RiskLevel.high,
            risk_source=RiskSource.product_knowledge,
            description="缺少产品规则说明",
            suggestion="补充产品规则",
            decision=RiskDecision.pending,
            validity=RiskValidity.active,
        )
        db.add(risk)
        db.commit()

        risk_service.clarify_risk(db=db, risk_id=risk.id, clarification_text="待删除澄清", doc_update_needed=False)
        risk_service.delete_risk(db=db, risk_id=risk.id)

        input_count = (
            db.query(RequirementInput)
            .filter(
                RequirementInput.requirement_id == requirement.id,
                RequirementInput.input_type == InputType.test_clarification,
                RequirementInput.source_label == "risk:{0}".format(risk.id),
            )
            .count()
        )
        evidence_count = (
            db.query(EvidenceBlock)
            .filter(
                EvidenceBlock.product_doc_id == doc.id,
                EvidenceBlock.created_from == EvidenceCreatedFrom.risk_clarification,
                EvidenceBlock.source_span == "risk:{0}".format(risk.id),
            )
            .count()
        )

        assert input_count == 0
        assert evidence_count == 0
    finally:
        db.close()


def test_risk_to_node_is_idempotent():
    """Converting the same accepted risk twice should return the same node."""
    requirement_id = _create_requirement_with_root()

    db = SessionLocal()
    try:
        risk = RiskItem(
            id=str(uuid4()),
            requirement_id=requirement_id,
            related_node_id=None,
            category=RiskCategory.flow_gap,
            risk_level=RiskLevel.high,
            risk_source=RiskSource.rule_tree,
            description="重复转节点风险",
            suggestion="补充异常节点",
            decision=RiskDecision.accepted,
            validity=RiskValidity.active,
        )
        db.add(risk)
        db.commit()

        first_node = risk_service.risk_to_node(db=db, risk_id=risk.id)
        second_node = risk_service.risk_to_node(db=db, risk_id=risk.id)

        db.refresh(risk)
        all_nodes = db.query(RuleNode).filter(RuleNode.requirement_id == requirement_id).all()

        assert first_node.id == second_node.id
        assert len(all_nodes) == 2
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers for review-snapshot tests (no rule tree required)
# ---------------------------------------------------------------------------

def _create_requirement_no_tree() -> int:
    db = SessionLocal()
    try:
        project = Project(name="review-{0}".format(uuid4().hex[:8]), description="review test")
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="评审需求",
            raw_text="用户提交表单，如果字段为空则给出提示。",
            source_type=SourceType.prd,
        )
        db.add(requirement)
        db.commit()
        return requirement.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase 2: review-stage snapshot tests
# ---------------------------------------------------------------------------

def test_generate_review_snapshot_without_rule_tree():
    """Review snapshot generation should work without any rule tree nodes."""
    requirement_id = _create_requirement_no_tree()

    db = SessionLocal()
    try:
        result = effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement_id,
        )

        snapshot = result["snapshot"]
        risks = result["risks"]
        hints = result["clarification_hints"]

        assert snapshot is not None
        assert snapshot.stage == AnalysisStage.review
        assert snapshot.summary != ""

        fields = (
            db.query(EffectiveRequirementField)
            .filter(EffectiveRequirementField.snapshot_id == snapshot.id)
            .all()
        )
        assert len(fields) > 0
        assert len(risks) > 0
        assert isinstance(hints, list)
    finally:
        db.close()


def test_review_snapshot_fields_have_derivation_and_source_refs():
    """Every field in a review snapshot must carry derivation, confidence, and source_refs."""
    requirement_id = _create_requirement_no_tree()

    db = SessionLocal()
    try:
        result = effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement_id,
        )

        fields = (
            db.query(EffectiveRequirementField)
            .filter(EffectiveRequirementField.snapshot_id == result["snapshot"].id)
            .all()
        )

        for f in fields:
            assert f.derivation is not None, "field {0} missing derivation".format(f.field_key)
            assert f.confidence is not None, "field {0} missing confidence".format(f.field_key)
            assert f.source_refs is not None and f.source_refs != "", \
                "field {0} missing source_refs".format(f.field_key)
    finally:
        db.close()


def test_review_snapshot_creates_risks_with_review_stage():
    """Risks generated by review snapshot should have analysis_stage=review."""
    requirement_id = _create_requirement_no_tree()

    db = SessionLocal()
    try:
        result = effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement_id,
        )
        risks = result["risks"]

        assert len(risks) > 0
        for r in risks:
            assert r.analysis_stage == AnalysisStage.review
            assert r.origin_snapshot_id == result["snapshot"].id
            assert r.validity == RiskValidity.active
    finally:
        db.close()


def test_superseded_marking_for_stale_risks():
    """Old active risks not seen in a new review analysis should be marked superseded."""
    requirement_id = _create_requirement_no_tree()

    db = SessionLocal()
    try:
        result1 = effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement_id,
        )
        first_risk_ids = {r.id for r in result1["risks"]}
        assert len(first_risk_ids) > 0

        old_mock = effective_requirement_service._mock_review_analysis

        def different_mock(raw_text, has_product_context=False):
            return {
                "summary": "完全不同的需求总结。",
                "fields": [
                    {
                        "field_key": "goal",
                        "value": "全新目标",
                        "derivation": "explicit",
                        "confidence": 0.9,
                        "source_refs": "新输入",
                    },
                ],
                "risks": [
                    {
                        "category": "security",
                        "risk_level": "critical",
                        "description": "一条全新的安全风险，与之前风险完全不同",
                        "suggestion": "进行安全审计",
                        "risk_source": "rule_tree",
                    },
                ],
            }

        effective_requirement_service._mock_review_analysis = different_mock
        try:
            result2 = effective_requirement_service.generate_review_snapshot(
                db=db, requirement_id=requirement_id,
            )
        finally:
            effective_requirement_service._mock_review_analysis = old_mock

        all_risks = db.query(RiskItem).filter(
            RiskItem.requirement_id == requirement_id,
        ).all()

        superseded_ids = set()
        active_ids = set()
        for r in all_risks:
            if r.validity == RiskValidity.superseded:
                superseded_ids.add(r.id)
            elif r.validity == RiskValidity.active:
                active_ids.add(r.id)

        assert first_risk_ids.issubset(superseded_ids), \
            "old risks should be marked superseded"
        assert len(active_ids) > 0, "new risks should be active"
        assert active_ids.isdisjoint(first_risk_ids), \
            "new active risks should not include old risk IDs"
    finally:
        db.close()


def test_review_snapshot_supersedes_reopened_risks_when_unseen():
    """Review rerun should supersede previously reopened risks that no longer appear."""
    requirement_id = _create_requirement_no_tree()

    db = SessionLocal()
    try:
        reopened_risk = RiskItem(
            id=str(uuid4()),
            requirement_id=requirement_id,
            related_node_id=None,
            category=RiskCategory.flow_gap,
            risk_level=RiskLevel.high,
            risk_source=RiskSource.rule_tree,
            description="旧的 reopen 风险",
            suggestion="旧建议",
            decision=RiskDecision.pending,
            validity=RiskValidity.reopened,
        )
        db.add(reopened_risk)
        db.commit()

        old_mock = effective_requirement_service._mock_review_analysis

        def empty_risk_mock(raw_text, has_product_context=False):
            return {
                "summary": "无风险结果",
                "fields": [
                    {
                        "field_key": "goal",
                        "value": "目标",
                        "derivation": "explicit",
                        "confidence": 1.0,
                        "source_refs": "原始需求",
                    },
                ],
                "risks": [],
            }

        effective_requirement_service._mock_review_analysis = empty_risk_mock
        try:
            effective_requirement_service.generate_review_snapshot(db=db, requirement_id=requirement_id)
        finally:
            effective_requirement_service._mock_review_analysis = old_mock

        db.refresh(reopened_risk)
        assert reopened_risk.validity == RiskValidity.superseded
    finally:
        db.close()


def test_review_snapshot_supersedes_previous_review_snapshot():
    """A new review snapshot should supersede the previous review snapshot."""
    requirement_id = _create_requirement_no_tree()

    db = SessionLocal()
    try:
        first = effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement_id,
        )["snapshot"]
        second = effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement_id,
        )["snapshot"]

        db.refresh(first)
        db.refresh(second)

        assert first.status == SnapshotStatus.superseded
        assert second.status == SnapshotStatus.draft
    finally:
        db.close()


def test_review_snapshot_with_formal_inputs():
    """Formal inputs should be incorporated into the snapshot context."""
    db = SessionLocal()
    try:
        project = Project(
            name="input-{0}".format(uuid4().hex[:8]),
            description="formal input test",
        )
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="带补充输入的需求",
            raw_text="用户提交表单，如果字段为空则给出提示。",
            source_type=SourceType.prd,
        )
        db.add(requirement)
        db.flush()

        db.add(RequirementInput(
            requirement_id=requirement.id,
            input_type=InputType.pm_addendum,
            content="补充说明：表单提交后需要显示成功提示，3秒后自动关闭。",
            source_label="产品经理口头确认",
        ))
        db.add(RequirementInput(
            requirement_id=requirement.id,
            input_type=InputType.test_clarification,
            content="测试确认：空值校验需覆盖所有必填字段。",
        ))
        db.commit()

        result = effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement.id,
        )

        snapshot = result["snapshot"]
        assert snapshot.based_on_input_ids is not None
        input_ids = snapshot.based_on_input_ids.split(",")
        assert len(input_ids) == 2
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers for predev-analyzer tests (requires rule tree + review snapshot)
# ---------------------------------------------------------------------------

def _create_requirement_with_review_snapshot() -> int:
    """Create a requirement with a root node AND a review snapshot."""
    db = SessionLocal()
    try:
        project = Project(
            name="predev-{0}".format(uuid4().hex[:8]),
            description="predev test",
        )
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="开发前分析需求",
            raw_text="用户提交表单，如果字段为空则给出提示。",
            source_type=SourceType.prd,
        )
        db.add(requirement)
        db.flush()

        db.add(RuleNode(
            id="root-{0}".format(uuid4().hex[:8]),
            requirement_id=requirement.id,
            parent_id=None,
            node_type=NodeType.root,
            content="用户提交表单",
            risk_level=RiskLevel.medium,
        ))
        db.commit()

        effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement.id,
        )
        return requirement.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase 4: predev-analyzer tests
# ---------------------------------------------------------------------------

def test_predev_analysis_creates_predev_snapshot():
    """Pre-dev analysis should create a pre_dev stage snapshot based on review."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        result = predev_analyzer.analyze_for_predev(
            db=db, requirement_id=requirement_id,
        )

        snapshot = result["snapshot"]
        assert snapshot is not None
        assert snapshot.stage == AnalysisStage.pre_dev
        assert snapshot.base_snapshot_id is not None
        assert snapshot.summary != ""

        fields = (
            db.query(EffectiveRequirementField)
            .filter(EffectiveRequirementField.snapshot_id == snapshot.id)
            .all()
        )
        assert len(fields) > 0
    finally:
        db.close()


def test_predev_analysis_supersedes_review_snapshot():
    """After pre-dev analysis, the review snapshot should be marked superseded."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        from app.models.entities import SnapshotStatus

        review = effective_requirement_service.get_latest_snapshot(
            db, requirement_id, stage="review",
        )
        assert review is not None
        review_id = review.id

        predev_analyzer.analyze_for_predev(
            db=db, requirement_id=requirement_id,
        )

        db.refresh(review)
        assert review.status == SnapshotStatus.superseded
    finally:
        db.close()


def test_predev_analysis_produces_risks_with_predev_stage():
    """Risks from pre-dev analysis should have analysis_stage=pre_dev."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        result = predev_analyzer.analyze_for_predev(
            db=db, requirement_id=requirement_id,
        )
        risks = result["risks"]

        assert len(risks) > 0
        for r in risks:
            assert r.analysis_stage == AnalysisStage.pre_dev
            assert r.origin_snapshot_id == result["snapshot"].id
            assert r.validity == RiskValidity.active
    finally:
        db.close()


def test_predev_analysis_returns_conflicts():
    """Pre-dev analysis should detect and return conflict items."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        result = predev_analyzer.analyze_for_predev(
            db=db, requirement_id=requirement_id,
        )
        conflicts = result["conflicts"]

        assert isinstance(conflicts, list)
        assert len(conflicts) > 0
        for c in conflicts:
            assert "conflict_type" in c
            assert "description" in c
    finally:
        db.close()


def test_predev_analysis_uses_latest_effective_snapshot_as_base():
    """A second pre-dev run should fork from the latest pre-dev snapshot, not the review snapshot."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        first = predev_analyzer.analyze_for_predev(db=db, requirement_id=requirement_id)
        first_snapshot = first["snapshot"]

        second = predev_analyzer.analyze_for_predev(db=db, requirement_id=requirement_id)
        second_snapshot = second["snapshot"]

        db.refresh(first_snapshot)
        assert second_snapshot.base_snapshot_id == first_snapshot.id
        assert first_snapshot.status == SnapshotStatus.superseded
    finally:
        db.close()


def test_predev_analysis_requires_review_snapshot():
    """Pre-dev analysis should fail if no review snapshot exists."""
    requirement_id = _create_requirement_with_root()

    db = SessionLocal()
    try:
        try:
            predev_analyzer.analyze_for_predev(
                db=db, requirement_id=requirement_id,
            )
            assert False, "should have raised ValueError"
        except ValueError as exc:
            assert "review snapshot" in str(exc).lower()
    finally:
        db.close()


def test_predev_analysis_requires_rule_tree():
    """Pre-dev analysis should fail if no rule tree nodes exist."""
    requirement_id = _create_requirement_no_tree()

    db = SessionLocal()
    try:
        effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement_id,
        )

        try:
            predev_analyzer.analyze_for_predev(
                db=db, requirement_id=requirement_id,
            )
            assert False, "should have raised ValueError"
        except ValueError as exc:
            assert "rule tree" in str(exc).lower() or "rule_tree" in str(exc).lower()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase 5: prerelease-auditor tests
# ---------------------------------------------------------------------------

def test_prerelease_audit_returns_closure_summary():
    """Pre-release audit should return a closure summary and risk assessments."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        predev_analyzer.analyze_for_predev(
            db=db, requirement_id=requirement_id,
        )

        result = prerelease_auditor.audit_for_prerelease(
            db=db, requirement_id=requirement_id,
        )

        assert "closure_summary" in result
        assert result["closure_summary"] != ""
        assert isinstance(result["blocking_risks"], list)
        assert isinstance(result["reopened_risks"], list)
        assert isinstance(result["resolved_risks"], list)
        assert isinstance(result["audit_notes"], list)
    finally:
        db.close()


def test_prerelease_audit_identifies_blocking_risks():
    """Audit should flag at least one blocking risk when pending high-severity risks exist."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        predev_analyzer.analyze_for_predev(
            db=db, requirement_id=requirement_id,
        )

        risks = db.query(RiskItem).filter(
            RiskItem.requirement_id == requirement_id,
        ).all()
        assert len(risks) > 0, "pre-dev should produce risks"

        result = prerelease_auditor.audit_for_prerelease(
            db=db, requirement_id=requirement_id,
        )

        blocking = result["blocking_risks"]
        assert len(blocking) > 0, "should identify at least one blocking risk"
        for b in blocking:
            assert "risk_id" in b
            assert "reason" in b
            assert b["reason"] != ""
    finally:
        db.close()


def test_prerelease_audit_applies_resolved_transitions():
    """Audit should mark resolvable risks as resolved in the ledger."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        predev_analyzer.analyze_for_predev(
            db=db, requirement_id=requirement_id,
        )

        result = prerelease_auditor.audit_for_prerelease(
            db=db, requirement_id=requirement_id,
        )

        resolved_ids = {r["risk_id"] for r in result.get("resolved_risks", [])}
        if resolved_ids:
            for rid in resolved_ids:
                risk = db.query(RiskItem).filter(RiskItem.id == rid).first()
                if risk:
                    assert risk.validity == RiskValidity.resolved
                    assert risk.analysis_stage == AnalysisStage.pre_release
    finally:
        db.close()


def test_prerelease_audit_without_risks():
    """Audit on a requirement with no risks should return an empty result."""
    requirement_id = _create_requirement_no_tree()

    db = SessionLocal()
    try:
        effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement_id,
        )

        db.query(RiskItem).filter(
            RiskItem.requirement_id == requirement_id,
        ).delete()
        db.commit()

        result = prerelease_auditor.audit_for_prerelease(
            db=db, requirement_id=requirement_id,
        )

        assert result["closure_summary"] != ""
        assert len(result["blocking_risks"]) == 0
        assert len(result["reopened_risks"]) == 0
        assert len(result["resolved_risks"]) == 0
    finally:
        db.close()


def test_prerelease_audit_requires_snapshot():
    """Audit should fail if no snapshot exists."""
    requirement_id = _create_requirement_with_root()

    db = SessionLocal()
    try:
        try:
            prerelease_auditor.audit_for_prerelease(
                db=db, requirement_id=requirement_id,
            )
            assert False, "should have raised ValueError"
        except ValueError as exc:
            assert "snapshot" in str(exc).lower()
    finally:
        db.close()


def test_prerelease_audit_prefers_latest_snapshot_across_stages():
    """Audit should use the newest effective snapshot, even if it is a review snapshot."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        predev_snapshot = predev_analyzer.analyze_for_predev(
            db=db, requirement_id=requirement_id,
        )["snapshot"]
        latest_review_snapshot = effective_requirement_service.generate_review_snapshot(
            db=db, requirement_id=requirement_id,
        )["snapshot"]

        chosen = prerelease_auditor._get_best_snapshot(db, requirement_id)
        assert chosen is not None
        assert chosen.id == latest_review_snapshot.id
        assert chosen.id != predev_snapshot.id
    finally:
        db.close()


def test_prerelease_audit_summary_warns_when_blocking():
    """Closure summary should say not to release when there are blocking risks."""
    requirement_id = _create_requirement_with_review_snapshot()

    db = SessionLocal()
    try:
        predev_analyzer.analyze_for_predev(
            db=db, requirement_id=requirement_id,
        )

        result = prerelease_auditor.audit_for_prerelease(
            db=db, requirement_id=requirement_id,
        )

        if result["blocking_risks"]:
            assert "不建议提测" in result["closure_summary"]
    finally:
        db.close()
