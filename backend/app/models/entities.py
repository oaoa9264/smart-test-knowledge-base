import enum
from datetime import datetime

from sqlalchemy import (
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


class RecoMode(str, enum.Enum):
    full = "FULL"
    change = "CHANGE"


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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="requirements")
    rule_nodes = relationship("RuleNode", back_populates="requirement", cascade="all, delete-orphan")
    rule_paths = relationship("RulePath", back_populates="requirement", cascade="all, delete-orphan")
    architecture_analyses = relationship("ArchitectureAnalysis", back_populates="requirement")
    reco_runs = relationship("RecoRun", back_populates="requirement", cascade="all, delete-orphan")


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
    steps = Column(Text, nullable=False)
    expected_result = Column(Text, nullable=False)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.medium, nullable=False)
    status = Column(Enum(TestCaseStatus), default=TestCaseStatus.active, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="testcases")
    bound_rule_nodes = relationship("RuleNode", secondary=case_rule_node_assoc, back_populates="bound_cases")
    bound_paths = relationship("RulePath", secondary=case_rule_path_assoc, back_populates="bound_cases")
    reco_results = relationship("RecoResult", back_populates="test_case")


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
    case_id = Column(Integer, ForeignKey("test_cases.id"), nullable=False, index=True)
    gain_risk = Column(Float, default=0.0, nullable=False)
    gain_node_ids = Column(Text, nullable=False)
    top_contributors = Column(Text, nullable=False)
    why_selected = Column(String(255), nullable=False)

    run = relationship("RecoRun", back_populates="results")
    test_case = relationship("TestCase", back_populates="reco_results")
