"""ORM models for the 13 entities of the M2 Data view + processed_message (docs/phase1/03 §5).

Must stay identical in table/column names to db/schema.sql — checked by tests/unit/test_schema_drift.py.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import (
    ApprovalDecision,
    EvidenceType,
    ExecutionStatus,
    FlagStatus,
    Role,
    TerminationReason,
    TestCaseStatus,
    TestResultStatus,
    TestSource,
    TestType,
)

# BIGSERIAL on PostgreSQL, INTEGER PRIMARY KEY (autoincrement) on SQLite for tests
BigId = BigInteger().with_variant(Integer, "sqlite")
JsonDoc = JSON().with_variant(JSONB, "postgresql")


def _enum(e, name: str) -> SAEnum:
    return SAEnum(e, name=name, values_callable=lambda x: [m.value for m in x], validate_strings=True)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ts(nullable: bool = False):
    return mapped_column(DateTime(timezone=True), nullable=nullable, default=None if nullable else utcnow)


class User(Base):
    __tablename__ = "app_user"
    user_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"))
    created_at: Mapped[datetime] = _ts()


class Project(Base):
    __tablename__ = "project"
    project_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    programming_language: Mapped[str] = mapped_column(String(20), default="Python")
    test_framework: Mapped[str] = mapped_column(String(20), default="pytest")
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    created_at: Mapped[datetime] = _ts()
    __table_args__ = (
        CheckConstraint("programming_language = 'Python'", name="ck_project_language"),
        CheckConstraint("test_framework = 'pytest'", name="ck_project_framework"),
    )


class ProjectMember(Base):
    __tablename__ = "project_member"
    project_id: Mapped[int] = mapped_column(ForeignKey("project.project_id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id", ondelete="CASCADE"), primary_key=True)
    joined_at: Mapped[datetime] = _ts()


class Requirement(Base):
    __tablename__ = "requirement"
    requirement_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.project_id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    created_at: Mapped[datetime] = _ts()
    __table_args__ = (Index("ix_requirement_project", "project_id", "created_at"),)


class RequirementTestCase(Base):
    __tablename__ = "requirement_test_case"
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirement.requirement_id", ondelete="CASCADE"), primary_key=True
    )
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_case.test_case_id", ondelete="CASCADE"), primary_key=True
    )
    __table_args__ = (Index("ix_rtc_test_case", "test_case_id"),)


class TestCase(Base):
    __test__ = False
    __tablename__ = "test_case"
    test_case_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.project_id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    test_type: Mapped[TestType] = mapped_column(_enum(TestType, "test_type"))
    source: Mapped[TestSource] = mapped_column(_enum(TestSource, "test_source"))
    test_code: Mapped[str] = mapped_column(Text)
    status: Mapped[TestCaseStatus] = mapped_column(
        _enum(TestCaseStatus, "test_case_status"), default=TestCaseStatus.DRAFT
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()

    requirements: Mapped[list[Requirement]] = relationship(secondary="requirement_test_case", lazy="selectin")
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_test_case_version"),
        Index("ix_test_case_project_status", "project_id", "status"),
    )


class TestApproval(Base):
    __test__ = False
    __tablename__ = "test_approval"
    approval_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_case.test_case_id", ondelete="CASCADE"))
    test_case_version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[ApprovalDecision] = mapped_column(_enum(ApprovalDecision, "approval_decision"))
    comment: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    decided_at: Mapped[datetime] = _ts()
    __table_args__ = (Index("ix_approval_test_version", "test_case_id", "test_case_version"),)


class ReviewFlag(Base):
    __tablename__ = "review_flag"
    flag_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_case.test_case_id", ondelete="CASCADE"))
    comment: Mapped[str] = mapped_column(Text)
    status: Mapped[FlagStatus] = mapped_column(_enum(FlagStatus, "flag_status"), default=FlagStatus.OPEN)
    raised_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    created_at: Mapped[datetime] = _ts()


class Execution(Base):
    __tablename__ = "execution"
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.project_id", ondelete="CASCADE"))
    requested_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    status: Mapped[ExecutionStatus] = mapped_column(
        _enum(ExecutionStatus, "execution_status"), default=ExecutionStatus.QUEUED
    )
    termination_reason: Mapped[TerminationReason | None] = mapped_column(_enum(TerminationReason, "termination_reason"))
    time_limit_seconds: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = _ts()
    started_at: Mapped[datetime | None] = _ts(nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = _ts(nullable=True)
    finished_at: Mapped[datetime | None] = _ts(nullable=True)

    tests: Mapped[list["ExecutionTestCase"]] = relationship(
        back_populates="execution", lazy="selectin", order_by="ExecutionTestCase.execution_test_id"
    )
    __table_args__ = (
        CheckConstraint(
            "(status IN ('QUEUED','RUNNING') AND termination_reason IS NULL AND finished_at IS NULL) OR "
            "(status NOT IN ('QUEUED','RUNNING') AND termination_reason IS NOT NULL AND finished_at IS NOT NULL)",
            name="ck_terminal_has_reason",
        ),
        CheckConstraint(
            "status NOT IN ('PASSED','FAILED') OR termination_reason = 'COMPLETED'",
            name="ck_pass_fail_needs_completed",
        ),
        Index("ix_execution_project_created", "project_id", "created_at"),
        Index("ix_execution_running", "status", "last_heartbeat_at"),
    )


class ExecutionTestCase(Base):
    __tablename__ = "execution_test_case"
    execution_test_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("execution.execution_id", ondelete="CASCADE"))
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_case.test_case_id"))
    test_case_version: Mapped[int] = mapped_column(Integer)
    result_status: Mapped[TestResultStatus] = mapped_column(
        _enum(TestResultStatus, "test_result_status"), default=TestResultStatus.NOT_RUN
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    failure_message: Mapped[str | None] = mapped_column(Text)

    execution: Mapped[Execution] = relationship(back_populates="tests")
    __table_args__ = (UniqueConstraint("execution_id", "test_case_id"),)


class ExecutionEvidence(Base):
    __tablename__ = "execution_evidence"
    evidence_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("execution.execution_id", ondelete="CASCADE"))
    execution_test_id: Mapped[int | None] = mapped_column(
        ForeignKey("execution_test_case.execution_test_id", ondelete="CASCADE")
    )
    evidence_type: Mapped[EvidenceType] = mapped_column(_enum(EvidenceType, "evidence_type"))
    content: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _ts()
    __table_args__ = (Index("ix_evidence_execution", "execution_id"),)


class ProcessedMessage(Base):
    __tablename__ = "processed_message"
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    processed_at: Mapped[datetime] = _ts()


class AiExplanation(Base):
    __tablename__ = "ai_explanation"
    explanation_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    execution_test_id: Mapped[int] = mapped_column(
        ForeignKey("execution_test_case.execution_test_id", ondelete="CASCADE")
    )
    explanation_text: Mapped[str] = mapped_column(Text)
    provider_model: Mapped[str] = mapped_column(String(120))
    requested_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    created_at: Mapped[datetime] = _ts()


class QualityReport(Base):
    __tablename__ = "quality_report"
    report_id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.project_id", ondelete="CASCADE"))
    summary: Mapped[dict] = mapped_column(JsonDoc)
    generated_by: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"))
    created_at: Mapped[datetime] = _ts()
    __table_args__ = (Index("ix_report_project", "project_id", "created_at"),)
