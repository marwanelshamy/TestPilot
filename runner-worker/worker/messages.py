"""Execution messages, contract I4 (docs/contracts/messages/*.schema.json). Tactic T10: every inbound
job is validated before anything runs; every outbound event is built from these models.

The Runner Worker is a separate deployable, so it keeps its own copy of the models; the contract tests
in tests/test_contract.py check both directions against the shared JSON Schemas."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Outcome = Literal["COMPLETED", "TIMEOUT", "RESOURCE_LIMIT", "ERROR"]

MAX_STREAM_CHARS = 65536  # stdout / stderr
MAX_JUNIT_CHARS = 262144


class _Msg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestedTest(_Msg):
    testCaseId: int
    testCaseVersion: int = Field(ge=1)
    testCode: str = Field(max_length=20000)


class Limits(_Msg):
    timeSeconds: int = Field(ge=1, le=300)
    cpu: float = Field(gt=0, le=2)
    memoryMb: int = Field(ge=64, le=1024)


class ExecutionRequested(_Msg):
    messageId: uuid.UUID
    schemaVersion: Literal[1]
    executionId: uuid.UUID
    projectId: int
    tests: list[RequestedTest] = Field(min_length=1, max_length=50)
    limits: Limits
    sentAt: datetime


class ExecutionHeartbeat(_Msg):
    messageId: uuid.UUID = Field(default_factory=uuid.uuid4)
    schemaVersion: Literal[1] = 1
    type: Literal["ExecutionHeartbeat"] = "ExecutionHeartbeat"
    executionId: uuid.UUID
    workerId: str = Field(max_length=64)
    sentAt: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExecutionFinished(_Msg):
    messageId: uuid.UUID = Field(default_factory=uuid.uuid4)
    schemaVersion: Literal[1] = 1
    type: Literal["ExecutionFinished"] = "ExecutionFinished"
    executionId: uuid.UUID
    workerId: str = Field(max_length=64)
    outcome: Outcome
    exitCode: int | None = None
    junitXml: str | None = Field(default=None, max_length=MAX_JUNIT_CHARS)
    stdout: str = Field(default="", max_length=MAX_STREAM_CHARS)
    stderr: str = Field(default="", max_length=MAX_STREAM_CHARS)
    truncated: bool = False
    errorDetail: str | None = Field(default=None, max_length=2000)
    durationMs: int | None = Field(default=None, ge=0)
    sentAt: datetime = Field(default_factory=lambda: datetime.now(UTC))


def test_file_name(test_case_id: int, version: int) -> str:
    """Agreed with the Core Backend (docs/phase1/03 §2): the report validator maps results back to
    test cases through this name."""
    return f"test_tc_{test_case_id}_v{version}.py"


test_file_name.__test__ = False
