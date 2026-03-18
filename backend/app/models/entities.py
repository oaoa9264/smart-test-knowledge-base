import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class SourceType(str, enum.Enum):
    prd = "prd"
    flowchart = "flowchart"
    api_doc = "api_doc"


class NodeType(str, enum.Enum):
    root = "root"
    condition = "condition"
    branch = "branch"
    action = "action"
    exception = "exception"


class RiskLevel(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class NodeStatus(str, enum.Enum):
    active = "active"
    modified = "modified"
    deleted = "deleted"


class TestCaseStatus(str, enum.Enum):
    active = "active"
    needs_review = "needs_review"
    invalidated = "invalidated"


class AnalysisStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    imported = "imported"


class RiskCategory(str, enum.Enum):
    input_validation = "input_validation"
    flow_gap = "flow_gap"
    data_integrity = "data_integrity"
    boundary = "boundary"
    security = "security"
    product_knowledge = "product_knowledge"


class RiskSource(str, enum.Enum):
    rule_tree = "rule_tree"
    product_knowledge = "product_knowledge"


class RiskDecision(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    ignored = "ignored"


class DocUpdateStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class InputType(str, enum.Enum):
    raw_requirement = "raw_requirement"
    pm_addendum = "pm_addendum"
    test_clarification = "test_clarification"
    review_note = "review_note"


class AnalysisStage(str, enum.Enum):
    review = "review"
    pre_dev = "pre_dev"
    pre_release = "pre_release"


class SnapshotStatus(str, enum.Enum):
    draft = "draft"
    confirmed = "confirmed"
    superseded = "superseded"


class Derivation(str, enum.Enum):
    explicit = "explicit"
    inferred = "inferred"
    missing = "missing"
    contradicted = "contradicted"


class EvidenceType(str, enum.Enum):
    precondition = "precondition"
    state_rule = "state_rule"
    field_rule = "field_rule"
    permission_rule = "permission_rule"
    exception_rule = "exception_rule"
    terminology = "terminology"


class EvidenceStatus(str, enum.Enum):
    draft = "draft"
    verified = "verified"
    rejected = "rejected"


class EvidenceCreatedFrom(str, enum.Enum):
    ai_bootstrap = "ai_bootstrap"
    risk_clarification = "risk_clarification"
    manual_edit = "manual_edit"


class RiskValidity(str, enum.Enum):
    active = "active"
    superseded = "superseded"
    reopened = "reopened"
    resolved = "resolved"


class RecoMode(str, enum.Enum):
    full = "FULL"
    change = "CHANGE"


class RuleTreeSessionStatus(str, enum.Enum):
    active = "active"
    generating = "generating"
    reviewing = "reviewing"
    saving = "saving"
    completed = "completed"
    failed = "failed"
    interrupted = "interrupted"
    confirmed = "confirmed"
    archived = "archived"


class TestPlanSessionStatus(str, enum.Enum):
    plan_generating = "plan_generating"
    plan_generated = "plan_generated"
    cases_generating = "cases_generating"
    cases_generated = "cases_generated"
    confirmed = "confirmed"
    archived = "archived"


case_rule_node_assoc = Table(
    "case_rule_node_assoc",
    Base.metadata,
    Column("testcase_id", ForeignKey("test_cases.id"), primary_key=True),
    Column("rule_node_id", ForeignKey("rule_nodes.id"), primary_key=True),
)

case_rule_path_assoc = Table(
    "case_rule_path_assoc",
    Base.metadata,
    Column("testcase_id", ForeignKey("test_cases.id"), primary_key=True),
    Column("rule_path_id", ForeignKey("rule_paths.id"), primary_key=True),
)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    product_code = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    requirements = relationship("Requirement", back_populates="project", cascade="all, delete-orphan")
    testcases = relationship("TestCase", back_populates="project", cascade="all, delete-orphan")
    architecture_analyses = relationship(
        "ArchitectureAnalysis",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    raw_text = Column(Text, nullable=False)
    source_type = Column(Enum(SourceType), default=SourceType.prd, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    requirement_group_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="requirements")
    rule_nodes = relationship("RuleNode", back_populates="requirement", cascade="all, delete-orphan")
    rule_paths = relationship("RulePath", back_populates="requirement", cascade="all, delete-orphan")
    architecture_analyses = relationship("ArchitectureAnalysis", back_populates="requirement")
    reco_runs = relationship("RecoRun", back_populates="requirement", cascade="all, delete-orphan")
    risk_items = relationship("RiskItem", back_populates="requirement", cascade="all, delete-orphan")
    rule_tree_sessions = relationship("RuleTreeSession", back_populates="requirement", cascade="all, delete-orphan")
    test_plan_sessions = relationship("TestPlanSession", back_populates="requirement", cascade="all, delete-orphan")
    requirement_inputs = relationship(
        "RequirementInput",
        back_populates="requirement",
        cascade="all, delete-orphan",
    )
    effective_requirement_snapshots = relationship(
        "EffectiveRequirementSnapshot",
        back_populates="requirement",
        cascade="all, delete-orphan",
    )


class RuleNode(Base):
    __tablename__ = "rule_nodes"
    __table_args__ = (UniqueConstraint("requirement_id", "id", name="uq_requirement_node"),)

    id = Column(String(64), primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)
    parent_id = Column(String(64), ForeignKey("rule_nodes.id"), nullable=True, index=True)
    node_type = Column(Enum(NodeType), nullable=False)
    content = Column(Text, nullable=False)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.medium, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    status = Column(Enum(NodeStatus), default=NodeStatus.active, nullable=False)

    requirement = relationship("Requirement", back_populates="rule_nodes")
    parent = relationship("RuleNode", remote_side=[id], backref="children")
    bound_cases = relationship("TestCase", secondary=case_rule_node_assoc, back_populates="bound_rule_nodes")


class RulePath(Base):
    __tablename__ = "rule_paths"

    id = Column(String(64), primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)
    node_sequence = Column(Text, nullable=False)  # comma-joined node ids

    requirement = relationship("Requirement", back_populates="rule_paths")
    bound_cases = relationship("TestCase", secondary=case_rule_path_assoc, back_populates="bound_paths")


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    precondition = Column(Text, nullable=True, default="")
    steps = Column(Text, nullable=False)
    expected_result = Column(Text, nullable=False)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.medium, nullable=False)
    status = Column(Enum(TestCaseStatus), default=TestCaseStatus.active, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="testcases")
    bound_rule_nodes = relationship("RuleNode", secondary=case_rule_node_assoc, back_populates="bound_cases")
    bound_paths = relationship("RulePath", secondary=case_rule_path_assoc, back_populates="bound_cases")
    reco_results = relationship(
        "RecoResult",
        back_populates="test_case",
        cascade="all, delete-orphan",
    )


class ArchitectureAnalysis(Base):
    __tablename__ = "architecture_analyses"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    image_path = Column(Text, nullable=True)
    description_text = Column(Text, nullable=True)
    analysis_result = Column(Text, nullable=True)
    status = Column(Enum(AnalysisStatus), default=AnalysisStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="architecture_analyses")
    requirement = relationship("Requirement", back_populates="architecture_analyses")


class RecoRun(Base):
    __tablename__ = "reco_run"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)
    mode = Column(Enum(RecoMode), default=RecoMode.full, nullable=False)
    k = Column(Integer, nullable=False)
    input_changed_node_ids = Column(Text, nullable=True)
    total_target_risk = Column(Float, default=0.0, nullable=False)
    covered_risk = Column(Float, default=0.0, nullable=False)
    coverage_ratio = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    requirement = relationship("Requirement", back_populates="reco_runs")
    results = relationship("RecoResult", back_populates="run", cascade="all, delete-orphan")


class RecoResult(Base):
    __tablename__ = "reco_result"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("reco_run.id"), nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    case_id = Column(Integer, ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    gain_risk = Column(Float, default=0.0, nullable=False)
    gain_node_ids = Column(Text, nullable=False)
    top_contributors = Column(Text, nullable=False)
    why_selected = Column(String(255), nullable=False)

    run = relationship("RecoRun", back_populates="results")
    test_case = relationship("TestCase", back_populates="reco_results")


class RiskItem(Base):
    __tablename__ = "risk_items"

    id = Column(String(64), primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)
    related_node_id = Column(String(64), ForeignKey("rule_nodes.id"), nullable=True, index=True)
    category = Column(Enum(RiskCategory), nullable=False)
    risk_level = Column(Enum(RiskLevel), nullable=False)
    description = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=False)
    decision = Column(Enum(RiskDecision), default=RiskDecision.pending, nullable=False)
    decision_reason = Column(Text, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    risk_source = Column(Enum(RiskSource), default=RiskSource.rule_tree, nullable=False)
    clarification_text = Column(Text, nullable=True)
    doc_update_needed = Column(Boolean, default=False, nullable=False)
    analysis_stage = Column(Enum(AnalysisStage), nullable=True)
    validity = Column(Enum(RiskValidity), default=RiskValidity.active, nullable=True)
    origin_snapshot_id = Column(Integer, ForeignKey("effective_requirement_snapshots.id"), nullable=True)
    last_seen_snapshot_id = Column(Integer, ForeignKey("effective_requirement_snapshots.id"), nullable=True)
    last_analysis_at = Column(DateTime, nullable=True)
    converted_node_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    requirement = relationship("Requirement", back_populates="risk_items")
    related_node = relationship("RuleNode", foreign_keys=[related_node_id])
    origin_snapshot = relationship("EffectiveRequirementSnapshot", foreign_keys=[origin_snapshot_id])
    last_seen_snapshot = relationship("EffectiveRequirementSnapshot", foreign_keys=[last_seen_snapshot_id])


class RuleTreeSession(Base):
    __tablename__ = "rule_tree_sessions"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    status = Column(Enum(RuleTreeSessionStatus), default=RuleTreeSessionStatus.active, nullable=False)
    confirmed_tree_snapshot = Column(Text, nullable=True)
    requirement_text_snapshot = Column(Text, nullable=True)
    progress_stage = Column(String(50), nullable=True)
    progress_message = Column(Text, nullable=True)
    progress_percent = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    generated_tree_snapshot = Column(Text, nullable=True)
    reviewed_tree_snapshot = Column(Text, nullable=True)
    current_task_started_at = Column(DateTime, nullable=True)
    current_task_finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    requirement = relationship("Requirement", back_populates="rule_tree_sessions")
    messages = relationship("RuleTreeMessage", back_populates="session", cascade="all, delete-orphan")


class RuleTreeMessage(Base):
    __tablename__ = "rule_tree_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("rule_tree_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(String(50), nullable=False)
    tree_snapshot = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("RuleTreeSession", back_populates="messages")


class TestPlanSession(Base):
    __tablename__ = "test_plan_sessions"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)
    status = Column(
        Enum(TestPlanSessionStatus),
        default=TestPlanSessionStatus.plan_generating,
        nullable=False,
    )
    plan_markdown = Column(Text, nullable=True)
    test_points_json = Column(Text, nullable=True)
    generated_cases_json = Column(Text, nullable=True)
    confirmed_case_ids_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    requirement = relationship("Requirement", back_populates="test_plan_sessions")


class DiffRecord(Base):
    __tablename__ = "diff_records"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    base_requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    compare_requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    base_version = Column(Integer, nullable=False)
    compare_version = Column(Integer, nullable=False)
    result_json = Column(Text, nullable=False)
    diff_type = Column(String(20), default="semantic", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project")
    base_requirement = relationship("Requirement", foreign_keys=[base_requirement_id])
    compare_requirement = relationship("Requirement", foreign_keys=[compare_requirement_id])


class RequirementInput(Base):
    __tablename__ = "requirement_inputs"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)
    input_type = Column(Enum(InputType), nullable=False)
    content = Column(Text, nullable=False)
    source_label = Column(String(255), nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    requirement = relationship("Requirement", back_populates="requirement_inputs")


class EffectiveRequirementSnapshot(Base):
    __tablename__ = "effective_requirement_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)
    stage = Column(Enum(AnalysisStage), nullable=False)
    status = Column(Enum(SnapshotStatus), default=SnapshotStatus.draft, nullable=False)
    based_on_input_ids = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    base_snapshot_id = Column(Integer, ForeignKey("effective_requirement_snapshots.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    requirement = relationship("Requirement", back_populates="effective_requirement_snapshots")
    base_snapshot = relationship("EffectiveRequirementSnapshot", remote_side=[id])
    fields = relationship("EffectiveRequirementField", back_populates="snapshot", cascade="all, delete-orphan")


class EffectiveRequirementField(Base):
    __tablename__ = "effective_requirement_fields"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("effective_requirement_snapshots.id"), nullable=False, index=True)
    field_key = Column(String(64), nullable=False)
    value = Column(Text, nullable=True)
    derivation = Column(Enum(Derivation), nullable=True)
    confidence = Column(Float, nullable=True)
    source_refs = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)

    snapshot = relationship("EffectiveRequirementSnapshot", back_populates="fields")


class EvidenceBlock(Base):
    __tablename__ = "evidence_blocks"

    id = Column(Integer, primary_key=True, index=True)
    product_doc_id = Column(Integer, ForeignKey("product_docs.id"), nullable=False, index=True)
    chunk_id = Column(Integer, ForeignKey("product_doc_chunks.id"), nullable=True, index=True)
    evidence_type = Column(Enum(EvidenceType), nullable=False)
    module_name = Column(String(255), nullable=True)
    statement = Column(Text, nullable=False)
    status = Column(Enum(EvidenceStatus), default=EvidenceStatus.draft, nullable=False)
    source_span = Column(Text, nullable=True)
    chunk_content_hash = Column(String(64), nullable=True)
    created_from = Column(Enum(EvidenceCreatedFrom), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product_doc = relationship("ProductDoc")
    chunk = relationship("ProductDocChunk")


class ProductDoc(Base):
    __tablename__ = "product_docs"

    id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String(512), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    chunks = relationship("ProductDocChunk", back_populates="product_doc", cascade="all, delete-orphan")
    updates = relationship("ProductDocUpdate", back_populates="product_doc", cascade="all, delete-orphan")


class ProductDocChunk(Base):
    __tablename__ = "product_doc_chunks"

    id = Column(Integer, primary_key=True, index=True)
    product_doc_id = Column(Integer, ForeignKey("product_docs.id"), nullable=False, index=True)
    stage_key = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    keywords = Column(Text, nullable=True)
    parent_title = Column(String(255), nullable=True)
    heading_level = Column(Integer, nullable=True)

    product_doc = relationship("ProductDoc", back_populates="chunks")


class ProductDocUpdate(Base):
    __tablename__ = "product_doc_updates"

    id = Column(Integer, primary_key=True, index=True)
    product_doc_id = Column(Integer, ForeignKey("product_docs.id"), nullable=False, index=True)
    chunk_id = Column(Integer, ForeignKey("product_doc_chunks.id"), nullable=True)
    risk_item_id = Column(String(64), ForeignKey("risk_items.id"), nullable=True)
    original_content = Column(Text, nullable=True)
    suggested_content = Column(Text, nullable=True)
    status = Column(Enum(DocUpdateStatus), default=DocUpdateStatus.pending, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product_doc = relationship("ProductDoc", back_populates="updates")
    chunk = relationship("ProductDocChunk")
    risk_item = relationship("RiskItem")
