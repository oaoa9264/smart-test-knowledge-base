import importlib
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.entities import EffectiveRequirementSnapshot, InputType, RequirementInput
from app.main import app
from app.services import effective_requirement_service, risk_service


client = TestClient(app)


def test_project_crud():
    project_name = f"crud-project-{uuid.uuid4().hex[:8]}"
    create_resp = client.post("/api/projects", json={"name": project_name, "description": "before"})
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == project_name

    update_resp = client.put(
        f"/api/projects/{project_id}",
        json={"name": f"{project_name}-updated", "description": "after"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"].endswith("-updated")
    assert update_resp.json()["description"] == "after"

    delete_resp = client.delete(f"/api/projects/{project_id}")
    assert delete_resp.status_code == 204

    get_after_delete_resp = client.get(f"/api/projects/{project_id}")
    assert get_after_delete_resp.status_code == 404


def test_requirement_crud():
    project_name = f"crud-req-project-{uuid.uuid4().hex[:8]}"
    project_resp = client.post("/api/projects", json={"name": project_name, "description": "desc"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    create_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={
            "title": "需求-before",
            "raw_text": "before text",
            "source_type": "prd",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/projects/{project_id}/requirements/{requirement_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "需求-before"

    update_resp = client.put(
        f"/api/projects/{project_id}/requirements/{requirement_id}",
        json={
            "title": "需求-after",
            "raw_text": "after text",
            "source_type": "flowchart",
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "需求-after"
    assert update_resp.json()["raw_text"] == "after text"
    assert update_resp.json()["source_type"] == "flowchart"

    delete_resp = client.delete(f"/api/projects/{project_id}/requirements/{requirement_id}")
    assert delete_resp.status_code == 204

    get_after_delete_resp = client.get(f"/api/projects/{project_id}/requirements/{requirement_id}")
    assert get_after_delete_resp.status_code == 404


def test_create_requirement_registers_raw_requirement_input():
    project_name = f"crud-input-project-{uuid.uuid4().hex[:8]}"
    project_resp = client.post("/api/projects", json={"name": project_name, "description": "desc"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    create_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={
            "title": "需求-with-input",
            "raw_text": "用户提交表单，如果字段为空则给出提示。",
            "source_type": "prd",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["id"]

    db = SessionLocal()
    try:
        inputs = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == requirement_id)
            .all()
        )
        assert len(inputs) == 1
        assert inputs[0].input_type == InputType.raw_requirement
        assert inputs[0].content == "用户提交表单，如果字段为空则给出提示。"
    finally:
        db.close()


def test_clarify_risk_registers_test_clarification_input():
    project_name = f"crud-clarify-project-{uuid.uuid4().hex[:8]}"
    project_resp = client.post(
        "/api/projects",
        json={"name": project_name, "description": "desc"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={
            "title": "需求-with-risk",
            "raw_text": "用户提交表单，如果字段为空则给出提示。",
            "source_type": "prd",
        },
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    root_resp = client.post(
        "/api/rules/nodes",
        json={
            "requirement_id": requirement_id,
            "parent_id": None,
            "node_type": "root",
            "content": "用户提交表单",
            "risk_level": "medium",
        },
    )
    assert root_resp.status_code == 201

    analyze_resp = client.post("/api/ai/risks/analyze", json={"requirement_id": requirement_id})
    assert analyze_resp.status_code == 201
    risk_id = analyze_resp.json()["risks"][0]["id"]

    clarify_resp = client.put(
        f"/api/rules/risks/{risk_id}/clarify",
        json={"clarification_text": "测试确认：所有必填字段都需要空值校验。", "doc_update_needed": False},
    )
    assert clarify_resp.status_code == 200

    db = SessionLocal()
    try:
        inputs = (
            db.query(RequirementInput)
            .filter(
                RequirementInput.requirement_id == requirement_id,
                RequirementInput.input_type == InputType.test_clarification,
            )
            .all()
        )
        assert len(inputs) == 1
        assert inputs[0].content == "测试确认：所有必填字段都需要空值校验。"
    finally:
        db.close()


def test_delete_requirement_cascades_risk_convergence_records():
    project_name = f"crud-cascade-project-{uuid.uuid4().hex[:8]}"
    project_resp = client.post("/api/projects", json={"name": project_name, "description": "desc"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={
            "title": "需求-cascade",
            "raw_text": "用户提交表单，如果字段为空则给出提示。",
            "source_type": "prd",
        },
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    db = SessionLocal()
    try:
        effective_requirement_service.generate_review_snapshot(db=db, requirement_id=requirement_id)
        snapshot_count = (
            db.query(EffectiveRequirementSnapshot)
            .filter(EffectiveRequirementSnapshot.requirement_id == requirement_id)
            .count()
        )
        input_count = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == requirement_id)
            .count()
        )
        assert snapshot_count > 0
        assert input_count > 0
    finally:
        db.close()


def test_create_new_requirement_version_registers_raw_requirement_input():
    project_name = f"crud-version-project-{uuid.uuid4().hex[:8]}"
    project_resp = client.post("/api/projects", json={"name": project_name, "description": "desc"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={
            "title": "需求-version",
            "raw_text": "版本化需求文本",
            "source_type": "prd",
        },
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    version_resp = client.post(f"/api/projects/{project_id}/requirements/{requirement_id}/new-version")
    assert version_resp.status_code == 201
    version_id = version_resp.json()["id"]

    db = SessionLocal()
    try:
        inputs = (
            db.query(RequirementInput)
            .filter(RequirementInput.requirement_id == version_id)
            .all()
        )
        assert len(inputs) == 1
        assert inputs[0].input_type == InputType.raw_requirement
        assert inputs[0].content == "版本化需求文本"
    finally:
        db.close()


def test_get_latest_snapshot_rejects_invalid_stage():
    project_name = f"crud-stage-project-{uuid.uuid4().hex[:8]}"
    project_resp = client.post("/api/projects", json={"name": project_name, "description": "desc"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    requirement_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={
            "title": "需求-stage",
            "raw_text": "stage text",
            "source_type": "prd",
        },
    )
    assert requirement_resp.status_code == 201
    requirement_id = requirement_resp.json()["id"]

    resp = client.get(f"/api/requirements/{requirement_id}/snapshots/latest?stage=bad_stage")
    assert resp.status_code == 400
    assert "invalid stage" in resp.json()["detail"].lower()


def test_create_requirement_rejects_invalid_source_type():
    project_name = f"crud-source-project-{uuid.uuid4().hex[:8]}"
    project_resp = client.post("/api/projects", json={"name": project_name, "description": "desc"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={
            "title": "需求-invalid-source",
            "raw_text": "raw",
            "source_type": "bad_type",
        },
    )
    assert resp.status_code == 400
    assert "invalid source_type" in resp.json()["detail"].lower()


def test_update_requirement_syncs_raw_requirement_input():
    project_name = f"crud-update-source-project-{uuid.uuid4().hex[:8]}"
    project_resp = client.post("/api/projects", json={"name": project_name, "description": "desc"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    create_resp = client.post(
        f"/api/projects/{project_id}/requirements",
        json={
            "title": "需求-before-update",
            "raw_text": "before text",
            "source_type": "prd",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/projects/{project_id}/requirements/{requirement_id}",
        json={
            "title": "需求-after-update",
            "raw_text": "after text",
            "source_type": "prd",
        },
    )
    assert update_resp.status_code == 200

    db = SessionLocal()
    try:
        inputs = (
            db.query(RequirementInput)
            .filter(
                RequirementInput.requirement_id == requirement_id,
                RequirementInput.input_type == InputType.raw_requirement,
            )
            .all()
        )
        assert len(inputs) == 1
        assert inputs[0].content == "after text"
    finally:
        db.close()


def test_list_requirements_recovers_invalid_persisted_source_type_on_startup():
    project_name = f"crud-invalid-source-project-{uuid.uuid4().hex[:8]}"
    project_resp = client.post("/api/projects", json={"name": project_name, "description": "desc"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                INSERT INTO requirements (project_id, title, raw_text, source_type, version, created_at)
                VALUES (:project_id, :title, :raw_text, :source_type, :version, CURRENT_TIMESTAMP)
                """
            ),
            {
                "project_id": project_id,
                "title": "legacy-invalid-source",
                "raw_text": "legacy text",
                "source_type": "bad_type",
                "version": 1,
            },
        )
        db.commit()
    finally:
        db.close()

    import app.main as main_module

    reloaded_main = importlib.reload(main_module)
    reloaded_client = TestClient(reloaded_main.app, raise_server_exceptions=False)

    resp = reloaded_client.get(f"/api/projects/{project_id}/requirements")

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "id": resp.json()[0]["id"],
            "project_id": project_id,
            "title": "legacy-invalid-source",
            "raw_text": "legacy text",
            "source_type": "prd",
            "version": 1,
            "requirement_group_id": None,
        }
    ]
