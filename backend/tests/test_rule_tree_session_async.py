from datetime import datetime

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app, recover_interrupted_rule_tree_sessions
from app.models.entities import Project, Requirement, RuleTreeSession, RuleTreeSessionStatus, SourceType
from app.schemas.rule_tree_session import RuleTreeSessionRead
from app.services import rule_tree_session as rule_tree_session_service


def _create_requirement_and_session(
    session_status: RuleTreeSessionStatus = RuleTreeSessionStatus.active,
) -> RuleTreeSession:
    db = SessionLocal()
    project = Project(name="异步规则树项目-{0}".format(datetime.utcnow().timestamp()), description="rule tree async")
    db.add(project)
    db.flush()

    requirement = Requirement(
        project_id=project.id,
        title="登录需求",
        raw_text="原始需求",
        source_type=SourceType.prd,
    )
    db.add(requirement)
    db.flush()

    session = RuleTreeSession(
        requirement_id=requirement.id,
        title="规则树会话",
        status=session_status,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    db.expunge(session)
    db.close()
    return session


def test_session_schema_exposes_async_fields():
    created_at = datetime.utcnow()
    started_at = datetime.utcnow()
    finished_at = datetime.utcnow()
    session = RuleTreeSession(
        id=1,
        requirement_id=2,
        title="异步生成会话",
        status=RuleTreeSessionStatus.generating,
        confirmed_tree_snapshot='{"decision_tree":{"nodes":[]}}',
        requirement_text_snapshot="需求快照",
        progress_stage="reviewing",
        progress_message="正在复核生成结果",
        progress_percent=80,
        last_error="最近一次错误",
        generated_tree_snapshot='{"decision_tree":{"nodes":[{"id":"n1"}]}}',
        reviewed_tree_snapshot='{"decision_tree":{"nodes":[{"id":"n1"},{"id":"n2"}]}}',
        current_task_started_at=started_at,
        current_task_finished_at=finished_at,
        created_at=created_at,
        updated_at=finished_at,
    )

    payload = RuleTreeSessionRead.from_orm(session)

    assert payload.status == "generating"
    assert payload.progress_stage == "reviewing"
    assert payload.progress_message == "正在复核生成结果"
    assert payload.progress_percent == 80
    assert payload.last_error == "最近一次错误"
    assert payload.generated_tree_snapshot == '{"decision_tree":{"nodes":[{"id":"n1"}]}}'
    assert payload.reviewed_tree_snapshot == '{"decision_tree":{"nodes":[{"id":"n1"},{"id":"n2"}]}}'
    assert payload.current_task_started_at == started_at
    assert payload.current_task_finished_at == finished_at


def test_startup_recovery_marks_in_progress_sessions_interrupted():
    db = SessionLocal()
    project = Project(name="异步规则树项目", description="startup recovery")
    db.add(project)
    db.flush()

    requirement = Requirement(
        project_id=project.id,
        title="登录需求",
        raw_text="原始需求",
        source_type=SourceType.prd,
    )
    db.add(requirement)
    db.flush()

    generating = RuleTreeSession(
        requirement_id=requirement.id,
        title="生成中",
        status=RuleTreeSessionStatus.generating,
        progress_stage="generating",
        progress_message="正在生成规则树",
    )
    reviewing = RuleTreeSession(
        requirement_id=requirement.id,
        title="复核中",
        status=RuleTreeSessionStatus.reviewing,
        progress_stage="reviewing",
        progress_message="正在复核规则树",
    )
    saving = RuleTreeSession(
        requirement_id=requirement.id,
        title="保存中",
        status=RuleTreeSessionStatus.saving,
        progress_stage="saving",
        progress_message="正在保存规则树",
    )
    completed = RuleTreeSession(
        requirement_id=requirement.id,
        title="已完成",
        status=RuleTreeSessionStatus.completed,
        progress_stage="completed",
        progress_message="已完成",
    )
    db.add_all([generating, reviewing, saving, completed])
    db.commit()
    db.close()

    updated_count = recover_interrupted_rule_tree_sessions()

    verify_db = SessionLocal()
    sessions = verify_db.query(RuleTreeSession).order_by(RuleTreeSession.id.asc()).all()
    verify_db.close()

    assert updated_count == 3
    assert [item.status for item in sessions] == [
        RuleTreeSessionStatus.interrupted,
        RuleTreeSessionStatus.interrupted,
        RuleTreeSessionStatus.interrupted,
        RuleTreeSessionStatus.completed,
    ]
    assert [item.progress_stage for item in sessions[:3]] == ["interrupted", "interrupted", "interrupted"]
    assert all(item.current_task_finished_at is not None for item in sessions[:3])
    assert all(item.last_error == "服务重启导致任务中断，请重新发起生成" for item in sessions[:3])


def test_generate_returns_immediately(monkeypatch):
    session = _create_requirement_and_session()
    launch_calls = []

    def _fake_launch(*, session_id, requirement_text, title, image_path, llm_client=None):
        launch_calls.append(
            {
                "session_id": session_id,
                "requirement_text": requirement_text,
                "title": title,
                "image_path": image_path,
            }
        )

    monkeypatch.setattr(rule_tree_session_service, "_launch_generation_worker", _fake_launch)

    with TestClient(app) as client:
        response = client.post(
            "/api/rules/sessions/{0}/generate".format(session.id),
            data={"requirement_text": "新的需求文本", "title": "新的会话标题"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["session"]["status"] == "generating"
    assert body["session"]["title"] == "新的会话标题"
    assert body["session"]["requirement_text_snapshot"] == "新的需求文本"
    assert body["session"]["progress_stage"] == "generating"
    assert body["session"]["progress_message"] == "已接受生成任务，准备开始生成规则树"
    assert body["session"]["current_task_started_at"] is not None
    assert launch_calls == [
        {
            "session_id": session.id,
            "requirement_text": "新的需求文本",
            "title": "新的会话标题",
            "image_path": None,
        }
    ]


def test_duplicate_generate_returns_conflict():
    with TestClient(app) as client:
        session = _create_requirement_and_session(RuleTreeSessionStatus.generating)
        response = client.post(
            "/api/rules/sessions/{0}/generate".format(session.id),
            data={"requirement_text": "重复提交的需求文本"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "当前会话生成中，请稍后再试"
