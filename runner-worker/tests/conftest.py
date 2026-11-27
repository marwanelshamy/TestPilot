import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from worker.messages import ExecutionRequested

REPO_ROOT = Path(__file__).resolve().parents[2]

PASSING = "def test_add():\n    assert 1 + 1 == 2\n"
FAILING = "def test_sub():\n    assert 3 - 1 == 1, 'math is hard'\n"


def message_schema(name: str) -> dict:
    return json.loads((REPO_ROOT / "docs" / "contracts" / "messages" / f"{name}.schema.json").read_text())


def validate(instance: dict, name: str) -> None:
    """Validate against the shared contract, including formats such as uuid and date-time."""
    jsonschema.Draft202012Validator(message_schema(name), format_checker=jsonschema.FormatChecker()).validate(instance)


def job_dict(**overrides) -> dict:
    d = {
        "messageId": str(uuid.uuid4()),
        "schemaVersion": 1,
        "executionId": str(uuid.uuid4()),
        "projectId": 1,
        "tests": [
            {"testCaseId": 101, "testCaseVersion": 2, "testCode": PASSING},
            {"testCaseId": 102, "testCaseVersion": 1, "testCode": FAILING},
        ],
        "limits": {"timeSeconds": 30, "cpu": 1, "memoryMb": 256},
        "sentAt": datetime.now(UTC).isoformat(),
    }
    d.update(overrides)
    return d


@pytest.fixture
def job() -> ExecutionRequested:
    return ExecutionRequested.model_validate(job_dict())
