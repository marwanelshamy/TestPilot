"""Domain enumerations — identical names/values to db/schema.sql and the OpenAPI contract."""

from enum import StrEnum


class Role(StrEnum):
    DEVELOPER = "DEVELOPER"
    QA_ASSISTANT = "QA_ASSISTANT"
    TEAM_LEAD = "TEAM_LEAD"
    ADMIN = "ADMIN"


class TestType(StrEnum):
    __test__ = False
    NORMAL = "NORMAL"
    BOUNDARY = "BOUNDARY"
    NEGATIVE = "NEGATIVE"


class TestSource(StrEnum):
    __test__ = False
    AI_GENERATED = "AI_GENERATED"
    MANUAL = "MANUAL"


class TestCaseStatus(StrEnum):
    __test__ = False
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FlagStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class ExecutionStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self not in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING)


class TerminationReason(StrEnum):
    COMPLETED = "COMPLETED"
    TIMEOUT = "TIMEOUT"
    RUNNER_LOST = "RUNNER_LOST"
    INVALID_REPORT = "INVALID_REPORT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    CANCELLED_BY_USER = "CANCELLED_BY_USER"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class TestResultStatus(StrEnum):
    __test__ = False
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    NOT_RUN = "NOT_RUN"


class EvidenceType(StrEnum):
    STDOUT = "STDOUT"
    STDERR = "STDERR"
    JUNIT_XML = "JUNIT_XML"
    RUNNER_LOG = "RUNNER_LOG"
