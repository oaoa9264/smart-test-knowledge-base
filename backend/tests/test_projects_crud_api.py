import uuid

from fastapi.testclient import TestClient

from app.main import app


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
