from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from uuid import uuid4

from app.core.database import SessionLocal
from app.models.entities import NodeType, Project, Requirement, RiskItem, RiskLevel, RuleNode, SourceType
from app.services import risk_service


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


def test_analyze_risks_merges_overlapping_requests_and_replaces_previous_results(monkeypatch):
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

    def fake_call_llm_for_risks(raw_text, tree_nodes_text, llm_client=None, product_context=None):
        del raw_text, tree_nodes_text, llm_client, product_context
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
