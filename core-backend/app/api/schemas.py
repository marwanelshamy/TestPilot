"""Request/response models of the public REST API (contract I1, docs/contracts/public-api.openapi.yaml).
JSON uses camelCase; Python uses snake_case."""

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.core.enums import (
    EvidenceType,
    ExecutionStatus,
    Role,
    TerminationReason,
    TestCaseStatus,
    TestResultStatus,
    TestSource,
    TestType,
)


class Api(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ApiIn(Api):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


T = TypeVar("T")


class Page(Api, Generic[T]):  # noqa: UP046 (pydantic generic model)
    items: list[T]
    page: int
    size: int
    total: int


class IdResponse(Api):
    id: int


# ---------- auth ----------
class LoginRequest(ApiIn):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=200)


class UserOut(Api):
    user_id: int
    name: str
    email: str
    role: Role


class LoginResponse(Api):
    token: str
    user: UserOut


# ---------- projects & requirements ----------
class ProjectCreate(ApiIn):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(Api):
    project_id: int
    name: str
    description: str | None
    programming_language: str
    test_framework: str
    created_by: int
    created_at: datetime


class RequirementCreate(ApiIn):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)


class RequirementOut(Api):
    requirement_id: int
    project_id: int
    title: str
    description: str
    created_at: datetime


# ---------- tests ----------
class GenerateTestsRequest(ApiIn):
    requirement_id: int
    test_types: list[TestType] = Field(
        default_factory=lambda: [TestType.NORMAL, TestType.BOUNDARY, TestType.NEGATIVE], min_length=1
    )
    code_under_test: str | None = Field(default=None, max_length=20000)


class GenerateTestsResponse(Api):
    test_ids: list[int]


class TestCaseCreate(ApiIn):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    test_type: TestType
    test_code: str = Field(min_length=1, max_length=20000)
    requirement_ids: list[int] = Field(default_factory=list)


class TestCaseUpdate(ApiIn):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    test_type: TestType | None = None
    test_code: str | None = Field(default=None, min_length=1, max_length=20000)


class TestCaseOut(Api):
    test_case_id: int
    project_id: int
    title: str
    description: str | None
    test_type: TestType
    source: TestSource
    test_code: str
    status: TestCaseStatus
    version: int
    requirement_ids: list[int]
    approved_version: int | None
    ai_generated: bool
    updated_at: datetime


class VersionOut(Api):
    version: int


class ApprovalDecisionIn(ApiIn):
    version: int = Field(ge=1)
    comment: str | None = Field(default=None, max_length=2000)


class FlagCreate(ApiIn):
    comment: str = Field(min_length=1, max_length=2000)


# ---------- executions ----------
class ExecutionCreate(ApiIn):
    project_id: int
    test_case_ids: list[int] = Field(min_length=1, max_length=50)


class ExecutionAccepted(Api):
    execution_id: uuid.UUID
    status: ExecutionStatus


class ExecutionTestOut(Api):
    execution_test_id: int
    test_case_id: int
    test_case_version: int
    result_status: TestResultStatus
    duration_ms: int | None
    failure_message: str | None


class ExecutionOut(Api):
    execution_id: uuid.UUID
    project_id: int
    status: ExecutionStatus
    termination_reason: TerminationReason | None
    tests: list[ExecutionTestOut]
    requested_by: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class EvidenceOut(Api):
    evidence_id: int
    evidence_type: EvidenceType
    content: str
    size_bytes: int
    truncated: bool


class ExplanationOut(Api):
    explanation_id: int
    explanation_text: str
    ai_generated: bool = True
    label: str
    provider_model: str
    created_at: datetime


# ---------- reports ----------
class CoverageItem(Api):
    requirement_id: int
    title: str
    approved_test_count: int
    last_result: str | None


class CoverageOut(Api):
    requirements: list[CoverageItem]


class RiskItem(Api):
    rule: str
    severity: str
    ref_id: str
    message: str


class RisksOut(Api):
    risks: list[RiskItem]


class QualityReportOut(Api):
    report_id: int
    project_id: int
    created_at: datetime
    summary: dict[str, Any]
