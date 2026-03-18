from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.entities import (
    DocUpdateStatus,
    EvidenceBlock,
    EvidenceCreatedFrom,
    EvidenceStatus,
    EvidenceType,
    NodeType,
    ProductDoc,
    ProductDocChunk,
    ProductDocUpdate,
    Project,
    Requirement,
    RiskCategory,
    RiskDecision,
    RiskItem,
    RiskLevel,
    RiskSource,
    RiskValidity,
    RuleNode,
    SourceType,
)
from app.services import evidence_service, product_doc_service


client = TestClient(app)


def _create_product_doc_with_chunks() -> str:
    """Create a product doc with chunks and return the product_code."""
    db = SessionLocal()
    try:
        product_code = "test-ev-{0}".format(uuid4().hex[:8])
        doc = ProductDoc(
            product_code=product_code,
            name="Test Product",
            description="For evidence tests",
        )
        db.add(doc)
        db.flush()

        chunks_data = [
            ("订单管理", "订单提交后进入待审核状态，审核通过后流转到已通过，审核拒绝则为已拒绝。"),
            ("用户权限", "管理员角色可以修改用户信息，操作员只能查看。"),
            ("字段校验", "手机号必须为11位数字，邮箱需符合标准格式校验。"),
        ]
        from app.services.product_doc_service import _extract_keywords_from_text
        for idx, (title, content) in enumerate(chunks_data):
            kw_list = _extract_keywords_from_text(title + " " + content)
            chunk = ProductDocChunk(
                product_doc_id=doc.id,
                stage_key="stage_{0}".format(idx),
                title=title,
                content=content,
                sort_order=idx,
                keywords=",".join(kw_list),
            )
            db.add(chunk)

        db.commit()
        return product_code
    finally:
        db.close()


def _create_risk_item_with_project(product_code: str) -> str:
    """Create a project + requirement + risk item and return the risk_id."""
    db = SessionLocal()
    try:
        project = Project(
            name="ev-proj-{0}".format(uuid4().hex[:8]),
            description="evidence test project",
            product_code=product_code,
        )
        db.add(project)
        db.flush()

        requirement = Requirement(
            project_id=project.id,
            title="Evidence Test Req",
            raw_text="测试需求用于验证证据功能。",
            source_type=SourceType.prd,
        )
        db.add(requirement)
        db.flush()

        root = RuleNode(
            id="root-{0}".format(uuid4().hex[:8]),
            requirement_id=requirement.id,
            parent_id=None,
            node_type=NodeType.root,
            content="测试根节点",
            risk_level=RiskLevel.medium,
        )
        db.add(root)
        db.flush()

        risk = RiskItem(
            id=str(uuid4()),
            requirement_id=requirement.id,
            related_node_id=None,
            category=RiskCategory.flow_gap,
            risk_level=RiskLevel.high,
            risk_source=RiskSource.rule_tree,
            description="测试风险描述",
            suggestion="测试建议",
            decision=RiskDecision.pending,
            validity=RiskValidity.active,
        )
        db.add(risk)
        db.commit()
        return risk.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Bootstrap tests
# ---------------------------------------------------------------------------

def test_bootstrap_creates_evidence_from_chunks():
    """bootstrap_evidence_from_chunks should create evidence for each chunk."""
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        blocks = evidence_service.bootstrap_evidence_from_chunks(
            db=db, product_code=product_code,
        )
        assert len(blocks) > 0

        for b in blocks:
            assert b.created_from == EvidenceCreatedFrom.ai_bootstrap
            assert b.status == EvidenceStatus.draft
            assert b.statement != ""
            assert b.chunk_id is not None
    finally:
        db.close()


def test_bootstrap_is_idempotent():
    """Running bootstrap twice should not create duplicate evidence."""
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        blocks_first = evidence_service.bootstrap_evidence_from_chunks(
            db=db, product_code=product_code,
        )
        count_first = len(blocks_first)
        assert count_first > 0

        blocks_second = evidence_service.bootstrap_evidence_from_chunks(
            db=db, product_code=product_code,
        )
        assert len(blocks_second) == 0, "second bootstrap should not create more evidence"

        doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
        total = db.query(EvidenceBlock).filter(EvidenceBlock.product_doc_id == doc.id).count()
        assert total == count_first
    finally:
        db.close()


def test_bootstrap_refreshes_evidence_when_chunk_content_changes():
    """Chunk content changes should trigger evidence regeneration for that chunk."""
    db = SessionLocal()
    try:
        product_code = "refresh-ev-{0}".format(uuid4().hex[:8])
        product_doc_service.import_product_doc_from_text(
            db=db,
            content="## 订单管理\n订单状态流转规则。",
            product_code=product_code,
            name="Refresh Evidence Test",
        )

        first_blocks = evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)
        assert len(first_blocks) == 1
        assert first_blocks[0].evidence_type == EvidenceType.state_rule

        product_doc_service.import_product_doc_from_text(
            db=db,
            content="## 订单管理\n手机号格式校验规则。",
            product_code=product_code,
            name="Refresh Evidence Test",
        )

        second_blocks = evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)
        assert len(second_blocks) == 1
        assert second_blocks[0].evidence_type == EvidenceType.field_rule
    finally:
        db.close()


def test_bootstrap_recreates_evidence_when_all_existing_are_rejected():
    """Rejected evidence should not permanently block future bootstrap runs."""
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        first_blocks = evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)
        assert first_blocks

        for block in first_blocks:
            block.status = EvidenceStatus.rejected
        db.commit()

        second_blocks = evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)
        assert len(second_blocks) > 0
        assert all(block.status == EvidenceStatus.draft for block in second_blocks)
    finally:
        db.close()


def test_manual_chunk_update_rejects_stale_evidence():
    """Editing a chunk should immediately invalidate evidence extracted from its old content."""
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        blocks = evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)
        assert blocks

        chunk_id = blocks[0].chunk_id
        assert chunk_id is not None
    finally:
        db.close()

    resp = client.put(
        f"/api/product-docs/{product_code}/chunks/{chunk_id}",
        json={"content": "手机号必须为11位数字，不能为空。"},
    )
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        chunk_blocks = (
            db.query(EvidenceBlock)
            .filter(EvidenceBlock.chunk_id == chunk_id)
            .all()
        )
        assert chunk_blocks
        assert all(block.status == EvidenceStatus.rejected for block in chunk_blocks)
    finally:
        db.close()


def test_apply_doc_update_rejects_stale_chunk_evidence():
    """Applying a doc update should invalidate evidence tied to the old chunk content."""
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        blocks = evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)
        assert blocks
        chunk_id = blocks[0].chunk_id
        assert chunk_id is not None

        doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
        update = ProductDocUpdate(
            product_doc_id=doc.id,
            chunk_id=chunk_id,
            risk_item_id=None,
            original_content="旧内容",
            suggested_content="手机号必须为11位数字，不能为空。",
            status=DocUpdateStatus.pending,
        )
        db.add(update)
        db.commit()
        db.refresh(update)

        product_doc_service.apply_doc_update(db=db, update_id=update.id)

        chunk_blocks = (
            db.query(EvidenceBlock)
            .filter(EvidenceBlock.chunk_id == chunk_id)
            .all()
        )
        assert chunk_blocks
        assert all(block.status == EvidenceStatus.rejected for block in chunk_blocks)
    finally:
        db.close()


def test_bootstrap_raises_for_missing_doc():
    db = SessionLocal()
    try:
        try:
            evidence_service.bootstrap_evidence_from_chunks(db=db, product_code="nonexistent")
            assert False, "should have raised ValueError"
        except ValueError:
            pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Create from clarification tests
# ---------------------------------------------------------------------------

def test_create_evidence_from_clarification():
    product_code = _create_product_doc_with_chunks()
    risk_id = _create_risk_item_with_project(product_code)

    db = SessionLocal()
    try:
        block = evidence_service.create_evidence_from_clarification(
            db=db,
            risk_item_id=risk_id,
            statement="订单审核通过后不可回退到待审核状态",
            evidence_type="state_rule",
            module_name="订单管理",
        )

        assert block.id is not None
        assert block.created_from == EvidenceCreatedFrom.risk_clarification
        assert block.evidence_type == EvidenceType.state_rule
        assert "订单审核" in block.statement
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Retrieval tests
# ---------------------------------------------------------------------------

def test_get_relevant_evidence_returns_matching_blocks():
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)

        results = evidence_service.get_relevant_evidence(
            db=db,
            product_code=product_code,
            requirement_text="订单状态流转的审核规则",
            module_names=["订单管理"],
        )
        assert len(results) > 0
        assert any("订单管理" in (b.module_name or "") for b in results)
    finally:
        db.close()


def test_get_relevant_evidence_excludes_rejected():
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)

        doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
        all_blocks = db.query(EvidenceBlock).filter(EvidenceBlock.product_doc_id == doc.id).all()
        for b in all_blocks:
            b.status = EvidenceStatus.rejected
        db.commit()

        results = evidence_service.get_relevant_evidence(
            db=db,
            product_code=product_code,
            requirement_text="订单管理",
        )
        assert len(results) == 0
    finally:
        db.close()


def test_get_relevant_evidence_falls_back_when_scores_are_zero():
    """Existing non-rejected evidence should still be returned in cold-start scenarios."""
    db = SessionLocal()
    try:
        product_code = "cold-ev-{0}".format(uuid4().hex[:8])
        doc = ProductDoc(product_code=product_code, name="Cold Evidence Product", description="cold start")
        db.add(doc)
        db.flush()

        db.add(
            EvidenceBlock(
                product_doc_id=doc.id,
                chunk_id=None,
                evidence_type=EvidenceType.field_rule,
                module_name="模块A",
                statement="规则A",
                status=EvidenceStatus.draft,
                created_from=EvidenceCreatedFrom.manual_edit,
            )
        )
        db.commit()

        results = evidence_service.get_relevant_evidence(
            db=db,
            product_code=product_code,
            requirement_text="",
        )
        assert len(results) == 1
        assert results[0].statement == "规则A"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Update / verify / reject tests
# ---------------------------------------------------------------------------

def test_update_evidence():
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        blocks = evidence_service.bootstrap_evidence_from_chunks(
            db=db, product_code=product_code,
        )
        block_id = blocks[0].id

        updated = evidence_service.update_evidence(
            db=db,
            evidence_id=block_id,
            statement="更新后的证据声明",
            evidence_type="exception_rule",
        )
        assert updated.statement == "更新后的证据声明"
        assert updated.evidence_type == EvidenceType.exception_rule
        assert updated.created_from == EvidenceCreatedFrom.manual_edit
    finally:
        db.close()


def test_verify_and_reject_evidence():
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        blocks = evidence_service.bootstrap_evidence_from_chunks(
            db=db, product_code=product_code,
        )
        assert len(blocks) >= 2

        verified = evidence_service.verify_evidence(db=db, evidence_id=blocks[0].id)
        assert verified.status == EvidenceStatus.verified

        rejected = evidence_service.reject_evidence(db=db, evidence_id=blocks[1].id)
        assert rejected.status == EvidenceStatus.rejected
    finally:
        db.close()


def test_update_evidence_api_returns_400_for_invalid_type():
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        blocks = evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)
        evidence_id = blocks[0].id
    finally:
        db.close()

    resp = client.put(
        f"/api/evidence/{evidence_id}",
        json={"evidence_type": "bad_type"},
    )
    assert resp.status_code == 400
    assert "invalid evidence_type" in resp.json()["detail"].lower()


def test_create_evidence_from_clarification_rejects_invalid_type():
    product_code = _create_product_doc_with_chunks()
    risk_id = _create_risk_item_with_project(product_code)

    resp = client.post(
        "/api/evidence/from-clarification",
        json={
            "risk_item_id": risk_id,
            "statement": "订单审核通过后不可回退到待审核状态",
            "evidence_type": "bad_type",
        },
    )
    assert resp.status_code == 400
    assert "invalid evidence_type" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Evidence-first chunk retrieval integration test
# ---------------------------------------------------------------------------

def test_get_relevant_chunks_prefers_evidence_backed():
    """Chunks with associated evidence should be prioritized in retrieval."""
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)

        doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
        order_blocks = (
            db.query(EvidenceBlock)
            .join(ProductDocChunk, EvidenceBlock.chunk_id == ProductDocChunk.id)
            .filter(
                EvidenceBlock.product_doc_id == doc.id,
                ProductDocChunk.title == "订单管理",
            )
            .all()
        )
        for b in order_blocks:
            b.status = EvidenceStatus.verified
        db.commit()

        chunks_with_ev = product_doc_service.get_relevant_chunks(
            db=db,
            product_code=product_code,
            requirement_text="订单审核流程",
            max_chunks=3,
            matched_modules=["订单管理"],
            use_evidence=True,
        )
        titles_ev = [c.title for c in chunks_with_ev]
        assert "订单管理" in titles_ev

        chunks_no_ev = product_doc_service.get_relevant_chunks(
            db=db,
            product_code=product_code,
            requirement_text="订单审核流程",
            max_chunks=3,
            matched_modules=["订单管理"],
            use_evidence=False,
        )
        titles_no_ev = [c.title for c in chunks_no_ev]
        assert "订单管理" in titles_no_ev

        ev_score_idx = next(
            (i for i, c in enumerate(chunks_with_ev) if c.title == "订单管理"),
            len(chunks_with_ev),
        )
        no_ev_score_idx = next(
            (i for i, c in enumerate(chunks_no_ev) if c.title == "订单管理"),
            len(chunks_no_ev),
        )
        assert ev_score_idx <= no_ev_score_idx, \
            "evidence-backed chunk should rank at least as high"
    finally:
        db.close()


def test_reimport_product_doc_keeps_evidence_chunk_links_consistent():
    """Re-import should not leave evidence rows pointing at deleted chunk IDs."""
    db = SessionLocal()
    try:
        product_code = "reimport-ev-{0}".format(uuid4().hex[:8])
        original = """
## 订单管理
订单提交后进入待审核状态。

## 用户权限
管理员可以修改用户信息。
""".strip()
        updated = """
## 概述
这是新版概述。

## 用户权限
管理员可以修改用户信息，操作员只能查看。

## 订单管理
订单提交后进入待审核状态，审核通过后可进入已通过状态。
""".strip()

        product_doc_service.import_product_doc_from_text(
            db=db,
            content=original,
            product_code=product_code,
            name="Reimport Evidence Test",
        )
        blocks = evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)
        assert blocks, "bootstrap should create evidence before re-import"

        product_doc_service.import_product_doc_from_text(
            db=db,
            content=updated,
            product_code=product_code,
            name="Reimport Evidence Test",
        )

        doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
        linked_pairs = (
            db.query(EvidenceBlock, ProductDocChunk)
            .join(ProductDocChunk, EvidenceBlock.chunk_id == ProductDocChunk.id)
            .filter(EvidenceBlock.product_doc_id == doc.id)
            .all()
        )

        assert linked_pairs
        assert all(
            block.module_name in (chunk.title, chunk.parent_title)
            for block, chunk in linked_pairs
        )
    finally:
        db.close()


def test_get_relevant_chunks_returns_evidence_backed_chunks_first():
    """Evidence-backed ranking should be preserved in the returned order."""
    db = SessionLocal()
    try:
        product_code = "rank-ev-{0}".format(uuid4().hex[:8])
        doc = ProductDoc(
            product_code=product_code,
            name="Rank Test Product",
            description="For retrieval ordering tests",
        )
        db.add(doc)
        db.flush()

        chunk_a = ProductDocChunk(
            product_doc_id=doc.id,
            stage_key="stage_0",
            title="用户权限",
            content="管理员可以修改用户信息，操作员只能查看。",
            sort_order=0,
            keywords="用户权限,管理员,操作员",
        )
        chunk_b = ProductDocChunk(
            product_doc_id=doc.id,
            stage_key="stage_1",
            title="订单管理",
            content="订单提交后进入待审核状态，审核通过后可进入已通过状态。",
            sort_order=1,
            keywords="订单管理,订单,审核,状态",
        )
        db.add(chunk_a)
        db.add(chunk_b)
        db.flush()

        db.add(
            EvidenceBlock(
                product_doc_id=doc.id,
                chunk_id=chunk_b.id,
                evidence_type=EvidenceType.state_rule,
                module_name="订单管理",
                statement="订单审核通过后可进入已通过状态。",
                status=EvidenceStatus.verified,
                created_from=EvidenceCreatedFrom.ai_bootstrap,
            )
        )
        db.commit()

        chunks = product_doc_service.get_relevant_chunks(
            db=db,
            product_code=product_code,
            requirement_text="用户订单审核规则",
            max_chunks=2,
            matched_modules=["用户权限", "订单管理"],
            use_evidence=True,
        )

        assert [chunk.title for chunk in chunks][:1] == ["订单管理"]
    finally:
        db.close()


def test_get_relevant_chunks_falls_back_when_no_scores():
    """Cold-start retrieval should still return chunks when nothing scores positively."""
    db = SessionLocal()
    try:
        product_code = "fallback-empty-{0}".format(uuid4().hex[:8])
        doc = ProductDoc(
            product_code=product_code,
            name="Fallback Product",
            description="For cold-start fallback tests",
        )
        db.add(doc)
        db.flush()

        db.add(
            ProductDocChunk(
                product_doc_id=doc.id,
                stage_key="stage_0",
                title="普通模块",
                content="这里只有普通说明，没有术语关键词。",
                sort_order=0,
                keywords="普通模块,说明",
            )
        )
        db.commit()

        chunks = product_doc_service.get_relevant_chunks(
            db=db,
            product_code=product_code,
            requirement_text="",
            max_chunks=3,
            use_evidence=True,
        )

        assert len(chunks) == 1
        assert chunks[0].title == "普通模块"
    finally:
        db.close()


def test_delete_product_doc_cascades_evidence_blocks():
    """Deleting a product doc should remove its associated evidence rows."""
    product_code = _create_product_doc_with_chunks()

    db = SessionLocal()
    try:
        evidence_service.bootstrap_evidence_from_chunks(db=db, product_code=product_code)
        doc = db.query(ProductDoc).filter(ProductDoc.product_code == product_code).first()
        doc_id = doc.id
    finally:
        db.close()

    resp = client.delete(f"/api/product-docs/{product_code}")
    assert resp.status_code == 204

    db = SessionLocal()
    try:
        evidence_count = (
            db.query(EvidenceBlock)
            .filter(EvidenceBlock.product_doc_id == doc_id)
            .count()
        )
        assert evidence_count == 0
    finally:
        db.close()
