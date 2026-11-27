"""Execution message contract I4 (docs/contracts/messages/*.schema.json) as Pydantic models.

Shared by the Job Publisher (outbound) and the Execution Event Listener (inbound, Member 2).
Validation of every message is tactic T10 (verify message integrity).
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    messageId: uuid.UUID = Field(default_factory=uuid.uuid4)
    schemaVersion: Literal[1] = 1
    executionId: uuid.UUID
    projectId: int
    tests: list[RequestedTest] = Field(min_length=1, max_length=50)
    limits: Limits
    sentAt: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExecutionHeartbeat(_Msg):
    messageId: uuid.UUID
    schemaVersion: Literal[1]
    type: Literal["ExecutionHeartbeat"]
    executionId: uuid.UUID
    workerId: str = Field(max_length=64)
    sentAt: datetime


class ExecutionFinished(_Msg):
    messageId: uuid.UUID
    schemaVersion: Literal[1]
    type: Literal["ExecutionFinished"]
    executionId: uuid.UUID
    workerId: str = Field(max_length=64)
    outcome: Literal["COMPLETED", "TIMEOUT", "RESOURCE_LIMIT", "ERROR"]
    exitCode: int | None = None
    junitXml: str | None = Field(default=None, max_length=262144)
    stdout: str = Field(default="", max_length=65536)
    stderr: str = Field(default="", max_length=65536)
    truncated: bool = False
    errorDetail: str | None = Field(default=None, max_length=2000)
    durationMs: int | None = Field(default=None, ge=0)
    sentAt: datetime


def test_file_name(test_case_id: int, version: int) -> str:
    """Agreed file name the Runner Worker writes for each test (docs/phase1/03 §2)."""
    return f"test_tc_{test_case_id}_v{version}.py"


test_file_name.__test__ = False  # not a pytest test
