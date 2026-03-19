import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import (
    NodeStatus,
    Project,
    Requirement,
    RuleNode,
    RulePath,
    TestCase,
    TestPlanSession,
    TestPlanSessionStatus,
)
from app.schemas.test_plan import (
    GeneratedTestCase,
    TestCaseConfirmRequest,
    TestCaseConfirmResponse,
    TestCaseGenRequest,
    TestCaseGenResponse,
    TestPlanRequest,
    TestPlanResponse,
    TestPlanSessionCreate,
    TestPlanSessionListResponse,
    TestPlanSessionResponse,
    TestPlanUpdateRequest,
    TestPoint,
)
from app.services.test_plan_generator import generate_test_cases, generate_test_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/test-plan", tags=["test-plan"])


def _load_nodes_and_paths(db: Session, requirement_id: int):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    db_nodes = (
        db.query(RuleNode)
        .filter(
            RuleNode.requirement_id == requirement_id,
            RuleNode.status != NodeStatus.deleted,
        )
        .all()
    )
    if not db_nodes:
        raise HTTPException(status_code=400, detail="rule tree is empty")

    nodes = [
        {
            "id": n.id,
            "content": n.content,
            "node_type": n.node_type.value if hasattr(n.node_type, "value") else str(n.node_type),
            "risk_level": n.risk_level.value if hasattr(n.risk_level, "value") else str(n.risk_level),
            "parent_id": n.parent_id,
        }
        for n in db_nodes
    ]

    db_paths = db.query(RulePath).filter(RulePath.requirement_id == requirement_id).all()
    paths = [
        p.node_sequence.split(",") if p.node_sequence else []
        for p in db_paths
    ]

    return requirement, nodes, paths


def _session_to_response(session: TestPlanSession) -> TestPlanSessionResponse:
    test_points = None
    if session.test_points_json:
        try:
            test_points = [TestPoint(**tp) for tp in json.loads(session.test_points_json)]
        except Exception:
            test_points = None

    generated_cases = None
    if session.generated_cases_json:
        try:
            generated_cases = [GeneratedTestCase(**tc) for tc in json.loads(session.generated_cases_json)]
        except Exception:
            generated_cases = None

    confirmed_case_ids = None
    if session.confirmed_case_ids_json:
        try:
            confirmed_case_ids = json.loads(session.confirmed_case_ids_json)
        except Exception:
            confirmed_case_ids = None

    return TestPlanSessionResponse(
        id=session.id,
        requirement_id=session.requirement_id,
        status=session.status.value if hasattr(session.status, "value") else str(session.status),
        plan_markdown=session.plan_markdown,
        test_points=test_points,
        generated_cases=generated_cases,
        confirmed_case_ids=confirmed_case_ids,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else "",
    )


def _archive_active_sessions(db: Session, requirement_id: int):
    """Archive any active (non-terminal) sessions for a requirement."""
    active_statuses = [
        TestPlanSessionStatus.plan_generating,
        TestPlanSessionStatus.plan_generated,
        TestPlanSessionStatus.cases_generating,
        TestPlanSessionStatus.cases_generated,
    ]
    db.query(TestPlanSession).filter(
        TestPlanSession.requirement_id == requirement_id,
        TestPlanSession.status.in_(active_statuses),
    ).update(
        {TestPlanSession.status: TestPlanSessionStatus.archived},
        synchronize_session="fetch",
    )


def _get_session_for_requirement(
    db: Session,
    session_id: Optional[int],
    requirement_id: int,
) -> Optional[TestPlanSession]:
    if not session_id:
        return None
    session = db.query(TestPlanSession).filter(TestPlanSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session.requirement_id != requirement_id:
        raise HTTPException(status_code=400, detail="session requirement mismatch")
    return session


# ===================== Session endpoints =====================


@router.get("/sessions", response_model=TestPlanSessionListResponse)
def list_sessions(
    requirement_id: int = Query(...),
    db: Session = Depends(get_db),
):
    sessions = (
        db.query(TestPlanSession)
        .filter(TestPlanSession.requirement_id == requirement_id)
        .order_by(TestPlanSession.created_at.desc())
        .all()
    )
    return TestPlanSessionListResponse(
        sessions=[_session_to_response(s) for s in sessions],
    )


@router.get("/sessions/{session_id}", response_model=TestPlanSessionResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
):
    session = db.query(TestPlanSession).filter(TestPlanSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_to_response(session)


@router.post("/sessions", response_model=TestPlanSessionResponse)
def create_session(
    payload: TestPlanSessionCreate,
    db: Session = Depends(get_db),
):
    requirement = db.query(Requirement).filter(Requirement.id == payload.requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    _archive_active_sessions(db, payload.requirement_id)

    session = TestPlanSession(
        requirement_id=payload.requirement_id,
        status=TestPlanSessionStatus.plan_generating,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return _session_to_response(session)


@router.put("/sessions/{session_id}/archive", response_model=TestPlanSessionResponse)
def archive_session(
    session_id: int,
    db: Session = Depends(get_db),
):
    session = db.query(TestPlanSession).filter(TestPlanSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    session.status = TestPlanSessionStatus.archived
    db.commit()
    db.refresh(session)

    return _session_to_response(session)


@router.put("/sessions/{session_id}/plan", response_model=TestPlanSessionResponse)
def update_session_plan(
    session_id: int,
    payload: TestPlanUpdateRequest,
    db: Session = Depends(get_db),
):
    """Allow users to edit and save a reviewed test plan."""
    session = db.query(TestPlanSession).filter(TestPlanSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    session.plan_markdown = payload.plan_markdown
    session.test_points_json = json.dumps(
        [tp.dict() for tp in payload.test_points], ensure_ascii=False,
    )
    session.generated_cases_json = None
    session.status = TestPlanSessionStatus.plan_generated
    db.commit()
    db.refresh(session)

    return _session_to_response(session)


# ===================== Generate / Confirm endpoints =====================


@router.post("/generate", response_model=TestPlanResponse)
def api_generate_test_plan(
    payload: TestPlanRequest,
    db: Session = Depends(get_db),
):
    _, nodes, paths = _load_nodes_and_paths(db, payload.requirement_id)

    session = _get_session_for_requirement(db, payload.session_id, payload.requirement_id)
    previous_status = session.status if session else None
    if session:
        session.status = TestPlanSessionStatus.plan_generating
        db.commit()

    try:
        result = generate_test_plan(nodes=nodes, paths=paths)
    except Exception as e:
        logger.exception("Failed to generate test plan")
        if session:
            if (
                previous_status == TestPlanSessionStatus.plan_generating
                and not session.plan_markdown
                and not session.test_points_json
            ):
                session.status = TestPlanSessionStatus.archived
            else:
                session.status = previous_status or TestPlanSessionStatus.archived
            db.commit()
        raise HTTPException(status_code=500, detail="生成测试方案失败: {0}".format(str(e)))

    test_points = [
        TestPoint(
            id=tp.get("id", "tp_0"),
            name=tp.get("name", ""),
            description=tp.get("description", ""),
            type=tp.get("type", "normal"),
            related_node_ids=tp.get("related_node_ids", []),
            priority=tp.get("priority", "medium"),
        )
        for tp in result.get("test_points", [])
    ]

    if session:
        if result.get("llm_status") == "failed":
            if (
                previous_status == TestPlanSessionStatus.plan_generating
                and not session.plan_markdown
                and not session.test_points_json
            ):
                session.status = TestPlanSessionStatus.archived
            else:
                session.status = previous_status or TestPlanSessionStatus.archived
        else:
            session.plan_markdown = result.get("markdown", "")
            session.test_points_json = json.dumps(
                [tp.dict() for tp in test_points], ensure_ascii=False,
            )
            session.generated_cases_json = None
            session.status = TestPlanSessionStatus.plan_generated
        db.commit()
        db.refresh(session)

    return TestPlanResponse(
        markdown=result.get("markdown", ""),
        test_points=test_points,
        llm_status=result.get("llm_status"),
        llm_provider=result.get("llm_provider"),
        llm_message=result.get("llm_message"),
        session_id=session.id if session else None,
    )


@router.post("/generate-cases", response_model=TestCaseGenResponse)
def api_generate_test_cases(
    payload: TestCaseGenRequest,
    db: Session = Depends(get_db),
):
    _, nodes, paths = _load_nodes_and_paths(db, payload.requirement_id)

    session = _get_session_for_requirement(db, payload.session_id, payload.requirement_id)
    previous_status = session.status if session else None
    if session:
        session.status = TestPlanSessionStatus.cases_generating
        db.commit()

    test_points_dicts = [tp.dict() for tp in payload.test_points]

    try:
        result = generate_test_cases(
            test_plan_markdown=payload.test_plan_markdown,
            test_points=test_points_dicts,
            nodes=nodes,
            paths=paths,
        )
    except Exception as e:
        logger.exception("Failed to generate test cases")
        if session:
            session.status = TestPlanSessionStatus.plan_generated
            db.commit()
        raise HTTPException(status_code=500, detail="生成测试用例失败: {0}".format(str(e)))

    generated = [
        GeneratedTestCase(
            title=c.get("title", ""),
            preconditions=c.get("preconditions", []),
            steps=c.get("steps", []),
            expected_result=c.get("expected_result", []),
            risk_level=c.get("risk_level", "medium"),
            related_node_ids=c.get("related_node_ids", []),
        )
        for c in result.get("test_cases", [])
    ]

    if session:
        if result.get("llm_status") == "failed":
            session.status = previous_status or TestPlanSessionStatus.plan_generated
        else:
            session.generated_cases_json = json.dumps(
                [g.dict() for g in generated], ensure_ascii=False,
            )
            session.status = TestPlanSessionStatus.cases_generated
        db.commit()
        db.refresh(session)

    return TestCaseGenResponse(
        test_cases=generated,
        llm_status=result.get("llm_status"),
        llm_provider=result.get("llm_provider"),
        llm_message=result.get("llm_message"),
        session_id=session.id if session else None,
    )


@router.post("/confirm-cases", response_model=TestCaseConfirmResponse)
def api_confirm_test_cases(
    payload: TestCaseConfirmRequest,
    db: Session = Depends(get_db),
):
    requirement = db.query(Requirement).filter(Requirement.id == payload.requirement_id).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="requirement not found")

    project = db.query(Project).filter(Project.id == requirement.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    session: Optional[TestPlanSession] = None
    if payload.session_id:
        session = db.query(TestPlanSession).filter(TestPlanSession.id == payload.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="session not found")
        if session.requirement_id != payload.requirement_id:
            raise HTTPException(status_code=400, detail="session requirement mismatch")
        if (
            session.status == TestPlanSessionStatus.confirmed
            and session.confirmed_case_ids_json
        ):
            try:
                existing_ids = json.loads(session.confirmed_case_ids_json)
            except Exception:
                existing_ids = []
            return TestCaseConfirmResponse(
                created_count=len(existing_ids),
                created_case_ids=existing_ids,
            )

    created_ids: List[int] = []
    for tc in payload.test_cases:
        case = TestCase(
            project_id=project.id,
            title=tc.title,
            precondition=tc.preconditions_as_text() if tc.preconditions else "",
            steps=tc.steps_as_text(),
            expected_result=tc.expected_result_as_text(),
            risk_level=tc.risk_level,
            status="active",
        )

        if tc.related_node_ids:
            requested_ids = {node_id for node_id in tc.related_node_ids if node_id}
            nodes = (
                db.query(RuleNode)
                .filter(
                    RuleNode.id.in_(requested_ids),
                    RuleNode.requirement_id == payload.requirement_id,
                    RuleNode.status != NodeStatus.deleted,
                )
                .all()
            )
            if len(nodes) != len(requested_ids):
                raise HTTPException(status_code=400, detail="invalid related_node_ids")
            case.bound_rule_nodes = nodes

        db.add(case)
        db.flush()
        created_ids.append(case.id)

    if session:
        session.confirmed_case_ids_json = json.dumps(created_ids)
        session.status = TestPlanSessionStatus.confirmed
        db.flush()

    db.commit()

    return TestCaseConfirmResponse(
        created_count=len(created_ids),
        created_case_ids=created_ids,
    )


@router.put("/sessions/{session_id}/cases", response_model=TestPlanSessionResponse)
def update_session_cases(
    session_id: int,
    cases: List[GeneratedTestCase],
    db: Session = Depends(get_db),
):
    """Update the generated_cases_json when user removes a case in the UI."""
    session = db.query(TestPlanSession).filter(TestPlanSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    session.generated_cases_json = json.dumps(
        [c.dict() for c in cases], ensure_ascii=False,
    )
    db.commit()
    db.refresh(session)

    return _session_to_response(session)
