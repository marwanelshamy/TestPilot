"""Contract I4 in both directions: what the worker accepts and what it emits match the shared JSON Schemas."""

import json

import jsonschema
import pytest
from pydantic import ValidationError

from tests.conftest import job_dict, validate
from worker.messages import ExecutionFinished, ExecutionHeartbeat, ExecutionRequested


def test_valid_job_matches_schema_and_model():
    d = job_dict()
    validate(d, "execution-requested")
    assert ExecutionRequested.model_validate(d).tests[0].testCaseId == 101


@pytest.mark.parametrize(
    "bad",
    [
        {"tests": []},  # no tests
        {"limits": {"timeSeconds": 0, "cpu": 1, "memoryMb": 256}},  # time limit out of range
        {"limits": {"timeSeconds": 30, "cpu": 8, "memoryMb": 256}},  # too much CPU
        {"limits": {"timeSeconds": 30, "cpu": 1, "memoryMb": 99999}},  # too much memory
        {"schemaVersion": 2},  # unknown contract version
        {"executionId": "not-a-uuid"},
        {"command": "rm -rf /"},  # unknown field
    ],
)
def test_invalid_jobs_are_rejected_by_both(bad):
    d = job_dict(**bad)
    with pytest.raises(jsonschema.ValidationError):
        validate(d, "execution-requested")
    with pytest.raises(ValidationError):
        ExecutionRequested.model_validate(d)


def test_emitted_heartbeat_matches_schema(job):
    hb = ExecutionHeartbeat(executionId=job.executionId, workerId="w1")
    validate(json.loads(hb.model_dump_json()), "execution-heartbeat")


@pytest.mark.parametrize("outcome", ["COMPLETED", "TIMEOUT", "RESOURCE_LIMIT", "ERROR"])
def test_emitted_finished_matches_schema(job, outcome):
    fin = ExecutionFinished(
        executionId=job.executionId, workerId="w1", outcome=outcome, exitCode=1, junitXml="<x/>", durationMs=5
    )
    validate(json.loads(fin.model_dump_json()), "execution-finished")
