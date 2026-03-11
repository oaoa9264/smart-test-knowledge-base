from datetime import datetime

from app.core.database import SessionLocal
from app.main import recover_interrupted_rule_tree_sessions
from app.models.entities import Project, Requirement, RuleTreeSession, RuleTreeSessionStatus, SourceType
from app.schemas.rule_tree_session import RuleTreeSessionRead


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
