from datetime import datetime
import json

from sqlalchemy import inspect
from fastapi.testclient import TestClient

import app.main as main_module
import app.models.entities as entities
import app.services.risk_analysis_task_service as risk_task_service
from app.core.database import SessionLocal, engine


def _create_requirement_id() -> int:
    db = SessionLocal()
    try:
        project = entities.Project(
            name="风险异步项目-{0}".format(datetime.utcnow().timestamp()),
            description="risk async",
        )
        db.add(project)
        db.flush()

        requirement = entities.Requirement(
            project_id=project.id,
            title="风险异步需求",
            raw_text="用户提交申请后需要经过评审、开发前检查和提测前审计。",
            source_type=entities.SourceType.prd,
        )
        db.add(requirement)
        db.commit()
        return requirement.id
    finally:
        db.close()


def _create_task(requirement_id: int, stage, status):
    task_cls = getattr(entities, "RiskAnalysisTask")
    db = SessionLocal()
    try:
        task = task_cls(
            requirement_id=requirement_id,
            stage=stage,
            status=status,
            progress_message="准备中",
            progress_percent=5,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task.id
    finally:
        db.close()


def test_risk_analysis_task_table_and_columns_exist():
    assert hasattr(entities, "RiskAnalysisTask"), "RiskAnalysisTask model should exist"

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert "risk_analysis_tasks" in table_names

    columns = {column["name"] for column in inspector.get_columns("risk_analysis_tasks")}
    assert {
        "requirement_id",
        "stage",
        "status",
        "progress_message",
        "progress_percent",
        "last_error",
        "snapshot_id",
        "result_json",
        "current_task_started_at",
        "current_task_finished_at",
    }.issubset(columns)


def test_recover_interrupted_risk_analysis_tasks_marks_in_progress_rows():
    assert hasattr(main_module, "recover_interrupted_risk_analysis_tasks"), (
        "startup recovery for risk analysis tasks should exist"
    )
    task_cls = getattr(entities, "RiskAnalysisTask", None)
    assert task_cls is not None, "RiskAnalysisTask model should exist"

    requirement_id = _create_requirement_id()

    db = SessionLocal()
    try:
        queued = task_cls(
            requirement_id=requirement_id,
            stage=entities.AnalysisStage.review,
            status="queued",
            progress_message="排队中",
        )
        running = task_cls(
            requirement_id=requirement_id,
            stage=entities.AnalysisStage.pre_dev,
            status="running",
            progress_message="执行中",
        )
        completed = task_cls(
            requirement_id=requirement_id,
            stage=entities.AnalysisStage.pre_release,
            status="completed",
            progress_message="已完成",
        )
        db.add_all([queued, running, completed])
        db.commit()
    finally:
        db.close()

    updated_count = main_module.recover_interrupted_risk_analysis_tasks()

    verify_db = SessionLocal()
    try:
        tasks = (
            verify_db.query(task_cls)
            .order_by(task_cls.id.asc())
            .all()
        )
        assert updated_count == 2
        assert [task.status for task in tasks] == ["interrupted", "interrupted", "completed"]
        assert all(task.current_task_finished_at is not None for task in tasks[:2])
        assert all(task.last_error == "服务重启导致任务中断，请重新发起分析" for task in tasks[:2])
    finally:
        verify_db.close()


def test_get_single_stage_task_returns_null_when_missing():
    requirement_id = _create_requirement_id()

    with TestClient(main_module.app) as client:
        response = client.get("/api/requirements/{0}/analysis-tasks/review".format(requirement_id))

    assert response.status_code == 200
    assert response.json() is None


def test_get_task_summary_returns_stage_mapping():
    requirement_id = _create_requirement_id()

    with TestClient(main_module.app) as client:
        response = client.get("/api/requirements/{0}/analysis-tasks".format(requirement_id))

    assert response.status_code == 200
    assert response.json() == {
        "review": None,
        "pre_dev": None,
        "pre_release": None,
    }


def test_get_single_stage_task_returns_latest_task():
    requirement_id = _create_requirement_id()
    task_cls = getattr(entities, "RiskAnalysisTask")

    db = SessionLocal()
    try:
        task = task_cls(
            requirement_id=requirement_id,
            stage=entities.AnalysisStage.review,
            status=entities.RiskAnalysisTaskStatus.completed,
            progress_message="已完成",
            progress_percent=100,
        )
        db.add(task)
        db.commit()
    finally:
        db.close()

    with TestClient(main_module.app) as client:
        response = client.get("/api/requirements/{0}/analysis-tasks/review".format(requirement_id))

    assert response.status_code == 200
    body = response.json()
    assert body["requirement_id"] == requirement_id
    assert body["stage"] == "review"
    assert body["status"] == "completed"
    assert body["progress_percent"] == 100


def test_start_review_task_returns_accepted():
    requirement_id = _create_requirement_id()

    with TestClient(main_module.app) as client:
        response = client.post("/api/requirements/{0}/analysis-tasks/review".format(requirement_id))

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["task"]["requirement_id"] == requirement_id
    assert body["task"]["stage"] == "review"
    assert body["task"]["status"] == "queued"


def test_duplicate_stage_start_returns_conflict():
    requirement_id = _create_requirement_id()
    task_cls = getattr(entities, "RiskAnalysisTask")

    with TestClient(main_module.app) as client:
        db = SessionLocal()
        try:
            task = task_cls(
                requirement_id=requirement_id,
                stage=entities.AnalysisStage.review,
                status=entities.RiskAnalysisTaskStatus.running,
                progress_message="执行中",
                progress_percent=45,
            )
            db.add(task)
            db.commit()
        finally:
            db.close()

        response = client.post("/api/requirements/{0}/analysis-tasks/review".format(requirement_id))

    assert response.status_code == 409
    assert response.json()["detail"] == "当前阶段分析进行中，请稍后再试"


def test_start_pre_dev_and_pre_release_tasks_return_accepted():
    requirement_id = _create_requirement_id()

    with TestClient(main_module.app) as client:
        pre_dev_resp = client.post("/api/requirements/{0}/analysis-tasks/pre_dev".format(requirement_id))
        pre_release_resp = client.post("/api/requirements/{0}/analysis-tasks/pre_release".format(requirement_id))

    assert pre_dev_resp.status_code == 200
    assert pre_dev_resp.json()["task"]["stage"] == "pre_dev"
    assert pre_release_resp.status_code == 200
    assert pre_release_resp.json()["task"]["stage"] == "pre_release"


def test_review_worker_persists_snapshot_and_result_json(monkeypatch):
    requirement_id = _create_requirement_id()
    task_id = _create_task(
        requirement_id=requirement_id,
        stage=entities.AnalysisStage.review,
        status=entities.RiskAnalysisTaskStatus.queued,
    )

    fake_result = {
        "snapshot": {
            "id": 101,
            "requirement_id": requirement_id,
            "stage": "review",
            "status": "draft",
            "summary": "评审摘要",
            "fields": [],
        },
        "risks": [],
        "clarification_hints": ["请补充异常处理"],
    }

    monkeypatch.setattr(risk_task_service, "generate_review_snapshot", lambda **_: fake_result)

    risk_task_service.run_risk_analysis_task(task_id=task_id, db_session_factory=SessionLocal)

    db = SessionLocal()
    try:
        task = db.query(entities.RiskAnalysisTask).filter(entities.RiskAnalysisTask.id == task_id).first()
        assert task.status == entities.RiskAnalysisTaskStatus.completed
        assert task.snapshot_id == 101
        assert task.current_task_finished_at is not None
        payload = json.loads(task.result_json)
        assert payload["snapshot"]["summary"] == "评审摘要"
        assert payload["clarification_hints"] == ["请补充异常处理"]
    finally:
        db.close()


def test_review_worker_serializes_snapshot_datetimes(monkeypatch):
    requirement_id = _create_requirement_id()
    task_id = _create_task(
        requirement_id=requirement_id,
        stage=entities.AnalysisStage.review,
        status=entities.RiskAnalysisTaskStatus.queued,
    )

    def _fake_review_result(**kwargs):
        del kwargs
        snapshot_created_at = datetime.utcnow()
        return {
            "snapshot": {
                "id": 101,
                "requirement_id": requirement_id,
                "stage": "review",
                "status": "draft",
                "based_on_input_ids": None,
                "summary": "带时间戳的评审快照",
                "base_snapshot_id": None,
                "created_at": snapshot_created_at,
                "fields": [],
            },
            "risks": [],
            "clarification_hints": [],
        }

    monkeypatch.setattr(risk_task_service, "generate_review_snapshot", _fake_review_result)

    risk_task_service.run_risk_analysis_task(task_id=task_id, db_session_factory=SessionLocal)

    verify_db = SessionLocal()
    try:
        task = verify_db.query(entities.RiskAnalysisTask).filter(entities.RiskAnalysisTask.id == task_id).first()
        assert task.status == entities.RiskAnalysisTaskStatus.completed
        payload = json.loads(task.result_json)
        assert payload["snapshot"]["id"] == 101
        assert isinstance(payload["snapshot"]["created_at"], str)
    finally:
        verify_db.close()


def test_pre_dev_and_pre_release_workers_persist_stage_specific_results(monkeypatch):
    requirement_id = _create_requirement_id()
    pre_dev_task_id = _create_task(
        requirement_id=requirement_id,
        stage=entities.AnalysisStage.pre_dev,
        status=entities.RiskAnalysisTaskStatus.queued,
    )
    pre_release_task_id = _create_task(
        requirement_id=requirement_id,
        stage=entities.AnalysisStage.pre_release,
        status=entities.RiskAnalysisTaskStatus.queued,
    )

    monkeypatch.setattr(
        risk_task_service,
        "analyze_for_predev",
        lambda **_: {
            "snapshot": {
                "id": 202,
                "requirement_id": requirement_id,
                "stage": "pre_dev",
                "status": "draft",
                "summary": "开发前摘要",
                "fields": [],
            },
            "risks": [],
            "conflicts": [{"conflict_type": "gap", "description": "存在冲突"}],
            "matched_evidence": [{"evidence_statement": "证据", "related_field_key": "goal", "match_type": "consistent"}],
        },
    )
    monkeypatch.setattr(
        risk_task_service,
        "audit_for_prerelease",
        lambda **_: {
            "closure_summary": "审计完成",
            "blocking_risks": [],
            "reopened_risks": [],
            "resolved_risks": [],
            "audit_notes": ["建议复核回归范围"],
        },
    )

    risk_task_service.run_risk_analysis_task(task_id=pre_dev_task_id, db_session_factory=SessionLocal)
    risk_task_service.run_risk_analysis_task(task_id=pre_release_task_id, db_session_factory=SessionLocal)

    db = SessionLocal()
    try:
        pre_dev_task = db.query(entities.RiskAnalysisTask).filter(entities.RiskAnalysisTask.id == pre_dev_task_id).first()
        pre_release_task = db.query(entities.RiskAnalysisTask).filter(entities.RiskAnalysisTask.id == pre_release_task_id).first()

        assert pre_dev_task.status == entities.RiskAnalysisTaskStatus.completed
        assert pre_dev_task.snapshot_id == 202
        assert json.loads(pre_dev_task.result_json)["conflicts"][0]["description"] == "存在冲突"

        assert pre_release_task.status == entities.RiskAnalysisTaskStatus.completed
        assert pre_release_task.snapshot_id is None
        assert json.loads(pre_release_task.result_json)["closure_summary"] == "审计完成"
    finally:
        db.close()


def test_worker_failure_sets_failed_state(monkeypatch):
    requirement_id = _create_requirement_id()
    task_id = _create_task(
        requirement_id=requirement_id,
        stage=entities.AnalysisStage.review,
        status=entities.RiskAnalysisTaskStatus.queued,
    )

    def _boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(risk_task_service, "generate_review_snapshot", _boom)

    risk_task_service.run_risk_analysis_task(task_id=task_id, db_session_factory=SessionLocal)

    db = SessionLocal()
    try:
        task = db.query(entities.RiskAnalysisTask).filter(entities.RiskAnalysisTask.id == task_id).first()
        assert task.status == entities.RiskAnalysisTaskStatus.failed
        assert "boom" in task.last_error
        assert task.current_task_finished_at is not None
    finally:
        db.close()
