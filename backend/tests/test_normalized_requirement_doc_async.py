from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy import inspect

import app.main as main_module
import app.models.entities as entities
import app.services.normalized_requirement_doc_task_service as doc_task_service
from app.core.database import SessionLocal, engine


def _create_requirement_id(raw_text: str = "用户提交申请。") -> int:
    db = SessionLocal()
    try:
        project = entities.Project(
            name="规范化需求异步项目-{0}".format(datetime.utcnow().timestamp()),
            description="normalized doc async",
        )
        db.add(project)
        db.flush()

        requirement = entities.Requirement(
            project_id=project.id,
            title="规范化需求异步任务",
            raw_text=raw_text,
            source_type=entities.SourceType.prd,
        )
        db.add(requirement)
        db.flush()

        db.add(
            entities.RequirementInput(
                requirement_id=requirement.id,
                input_type=entities.InputType.pm_addendum,
                content="补充：用户提交后可查看状态。",
                source_label="pm",
            )
        )
        db.commit()
        return requirement.id
    finally:
        db.close()


def test_normalized_requirement_doc_task_table_and_columns_exist():
    assert hasattr(entities, "NormalizedRequirementDocTask")

    inspector = inspect(engine)
    assert "normalized_requirement_doc_tasks" in set(inspector.get_table_names())

    columns = {column["name"] for column in inspector.get_columns("normalized_requirement_doc_tasks")}
    assert {
        "requirement_id",
        "status",
        "progress_message",
        "progress_percent",
        "last_error",
        "basis_hash",
        "uses_fresh_snapshot",
        "snapshot_stale",
        "source_payload_json",
        "snapshot_payload_json",
        "result_markdown",
        "llm_provider",
        "current_task_started_at",
        "current_task_finished_at",
    }.issubset(columns)


def test_recover_interrupted_normalized_doc_tasks_marks_in_progress_rows():
    requirement_id = _create_requirement_id()
    requirement_id_2 = _create_requirement_id(raw_text="第二条需求")
    requirement_id_3 = _create_requirement_id(raw_text="第三条需求")
    task_cls = entities.NormalizedRequirementDocTask

    db = SessionLocal()
    try:
        queued = task_cls(requirement_id=requirement_id, status="queued", progress_message="排队中")
        running = task_cls(requirement_id=requirement_id_2, status="running", progress_message="执行中")
        completed = task_cls(requirement_id=requirement_id_3, status="completed", progress_message="已完成")
        db.add_all([queued, running, completed])
        db.commit()
    finally:
        db.close()

    updated_count = main_module.recover_interrupted_normalized_requirement_doc_tasks()

    verify_db = SessionLocal()
    try:
        tasks = verify_db.query(task_cls).order_by(task_cls.id.asc()).all()
        assert updated_count == 2
        assert [task.status for task in tasks] == ["interrupted", "interrupted", "completed"]
        assert all(task.current_task_finished_at is not None for task in tasks[:2])
        assert all(task.last_error == "服务重启导致任务中断，请重新发起生成" for task in tasks[:2])
    finally:
        verify_db.close()


def test_get_latest_normalized_doc_task_returns_null_when_missing():
    requirement_id = _create_requirement_id()

    with TestClient(main_module.app) as client:
        response = client.get("/api/requirements/{0}/normalized-doc-tasks/latest".format(requirement_id))

    assert response.status_code == 200
    assert response.json() is None


def test_start_normalized_doc_task_returns_locked_basis_metadata(monkeypatch):
    requirement_id = _create_requirement_id()
    monkeypatch.setattr(doc_task_service, "_launch_normalized_requirement_doc_task_worker", lambda task_id: None)

    with TestClient(main_module.app) as client:
        response = client.post("/api/requirements/{0}/normalized-doc-tasks".format(requirement_id))

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["task"]["requirement_id"] == requirement_id
    assert body["task"]["status"] == "queued"
    assert body["task"]["basis_hash"]
    assert body["task"]["uses_fresh_snapshot"] is False
    assert body["task"]["snapshot_stale"] is False
    assert body["task"]["source_payload_json"]
    assert body["task"]["snapshot_payload_json"] is None


def test_task_uses_locked_payload_even_if_requirement_changes_after_start(monkeypatch):
    requirement_id = _create_requirement_id(raw_text="旧需求文本")
    monkeypatch.setattr(doc_task_service, "_launch_normalized_requirement_doc_task_worker", lambda task_id: None)

    with TestClient(main_module.app) as client:
        response = client.post("/api/requirements/{0}/normalized-doc-tasks".format(requirement_id))

    assert response.status_code == 200
    task_id = response.json()["task"]["id"]
    original_basis_hash = response.json()["task"]["basis_hash"]

    db = SessionLocal()
    try:
        requirement = db.query(entities.Requirement).filter(entities.Requirement.id == requirement_id).first()
        requirement.raw_text = "新需求文本"
        input_item = (
            db.query(entities.RequirementInput)
            .filter(entities.RequirementInput.requirement_id == requirement_id)
            .first()
        )
        input_item.content = "补充：已被修改"
        db.commit()
    finally:
        db.close()

    captured = {}

    def _fake_generate(*, source_payload, snapshot_payload, llm_client=None):
        del llm_client
        captured["source_payload"] = source_payload
        captured["snapshot_payload"] = snapshot_payload
        return {
            "markdown": "# 规范化需求异步任务\n",
            "llm_status": "success",
            "llm_provider": "fake",
            "llm_message": None,
        }

    monkeypatch.setattr(doc_task_service, "generate_normalized_requirement_doc_from_task_payloads", _fake_generate)

    doc_task_service.run_normalized_requirement_doc_task(task_id=task_id, db_session_factory=SessionLocal)

    verify_db = SessionLocal()
    try:
        task = (
            verify_db.query(entities.NormalizedRequirementDocTask)
            .filter(entities.NormalizedRequirementDocTask.id == task_id)
            .first()
        )
        assert task.status == entities.RiskAnalysisTaskStatus.completed
        assert task.basis_hash == original_basis_hash
        assert json.loads(task.source_payload_json)["raw_text"] == "旧需求文本"
        assert captured["source_payload"]["raw_text"] == "旧需求文本"
        assert captured["source_payload"]["formal_inputs"][0]["content"] == "补充：用户提交后可查看状态。"
    finally:
        verify_db.close()


def test_duplicate_normalized_doc_task_start_returns_conflict(monkeypatch):
    requirement_id = _create_requirement_id()
    monkeypatch.setattr(doc_task_service, "_launch_normalized_requirement_doc_task_worker", lambda task_id: None)

    with TestClient(main_module.app) as client:
        first = client.post("/api/requirements/{0}/normalized-doc-tasks".format(requirement_id))
        assert first.status_code == 200

        db = SessionLocal()
        try:
            task = db.query(entities.NormalizedRequirementDocTask).filter(
                entities.NormalizedRequirementDocTask.requirement_id == requirement_id
            ).first()
            task.status = entities.RiskAnalysisTaskStatus.running
            db.commit()
        finally:
            db.close()

        second = client.post("/api/requirements/{0}/normalized-doc-tasks".format(requirement_id))

    assert second.status_code == 409
    assert second.json()["detail"] == "规范化需求文档生成进行中，请稍后再试"


def test_normalized_doc_worker_persists_markdown_and_meta(monkeypatch):
    requirement_id = _create_requirement_id()
    db = SessionLocal()
    try:
        task_id = doc_task_service.start_normalized_requirement_doc_task(db, requirement_id).id
    finally:
        db.close()

    monkeypatch.setattr(
        doc_task_service,
        "generate_normalized_requirement_doc_from_task_payloads",
        lambda **_: {
            "markdown": "# 规范化需求异步任务\n\n## 1. 需求背景与目标\n\n用户提交申请。\n",
            "llm_status": "success",
            "llm_provider": "fake",
            "llm_message": None,
        },
    )

    doc_task_service.run_normalized_requirement_doc_task(task_id=task_id, db_session_factory=SessionLocal)

    db = SessionLocal()
    try:
        task = db.query(entities.NormalizedRequirementDocTask).filter(entities.NormalizedRequirementDocTask.id == task_id).first()
        assert task.status == entities.RiskAnalysisTaskStatus.completed
        assert task.result_markdown.startswith("# 规范化需求异步任务")
        assert task.llm_provider == "fake"
        assert task.current_task_finished_at is not None
    finally:
        db.close()


def test_normalized_doc_worker_failure_sets_failed_state(monkeypatch):
    requirement_id = _create_requirement_id()
    db = SessionLocal()
    try:
        task_id = doc_task_service.start_normalized_requirement_doc_task(db, requirement_id).id
    finally:
        db.close()

    def _boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(doc_task_service, "generate_normalized_requirement_doc_from_task_payloads", _boom)

    doc_task_service.run_normalized_requirement_doc_task(task_id=task_id, db_session_factory=SessionLocal)

    db = SessionLocal()
    try:
        task = db.query(entities.NormalizedRequirementDocTask).filter(entities.NormalizedRequirementDocTask.id == task_id).first()
        assert task.status == entities.RiskAnalysisTaskStatus.failed
        assert "boom" in task.last_error
        assert task.current_task_finished_at is not None
    finally:
        db.close()
