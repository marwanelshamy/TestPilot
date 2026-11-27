"""ADR-006 / QAS-7: only a valid, complete, consistent report can produce PASSED or FAILED."""

import uuid

import pytest

from app.core.enums import ExecutionStatus as S
from app.core.enums import TerminationReason as R
from app.core.enums import TestResultStatus as T
from app.core.messages import ExecutionFinished
from app.services.orchestrator.report_validator import InvalidReport, evaluate, parse_junit
from tests.conftest import finished, junit

EXPECTED = {101: 2, 102: 1}


def ev(**kw):
    return evaluate(ExecutionFinished.model_validate(finished(uuid.uuid4(), **kw)), EXPECTED)


def test_all_pass_is_passed():
    v = ev(exitCode=0, junitXml=junit([(101, 2, "pass"), (102, 1, "pass")]))
    assert (v.status, v.reason) == (S.PASSED, R.COMPLETED)
    assert v.results[101][0] == T.PASSED and v.results[101][1] == 120


def test_one_failure_is_failed_with_message():
    v = ev(exitCode=1, junitXml=junit([(101, 2, "pass"), (102, 1, "fail")]))
    assert v.status == S.FAILED
    assert v.results[102] == (T.FAILED, 120, "assert 3 == 4")


def test_error_and_skip_mapping():
    v = ev(exitCode=1, junitXml=junit([(101, 2, "error"), (102, 1, "skip")]))
    assert v.status == S.FAILED
    assert v.results[101][0] == T.ERROR and v.results[102][0] == T.SKIPPED


@pytest.mark.parametrize(
    "kw, reason",
    [
        ({"junitXml": None}, R.INVALID_REPORT),  # completed but no report
        ({"junitXml": "<not xml"}, R.INVALID_REPORT),  # unparseable
        ({"junitXml": junit([(101, 2, "pass")])}, R.INVALID_REPORT),  # requested test 102 missing
        ({"junitXml": junit([(101, 2, "pass"), (102, 1, "pass")], suite_tests=5)}, R.INVALID_REPORT),  # count lie
        ({"junitXml": junit([(101, 1, "pass"), (102, 1, "pass")])}, R.INVALID_REPORT),  # wrong version
        ({"exitCode": 0, "junitXml": junit([(101, 2, "fail"), (102, 1, "pass")])}, R.INVALID_REPORT),  # exit 0 + fail
        ({"exitCode": 1, "junitXml": junit([(101, 2, "pass"), (102, 1, "pass")])}, R.INVALID_REPORT),  # exit 1 + pass
        ({"exitCode": 2, "junitXml": junit([(101, 2, "pass"), (102, 1, "pass")])}, R.INVALID_REPORT),  # interrupted
        ({"outcome": "TIMEOUT", "junitXml": junit([(101, 2, "pass"), (102, 1, "pass")])}, R.TIMEOUT),
        ({"outcome": "RESOURCE_LIMIT"}, R.RESOURCE_LIMIT),
        ({"outcome": "ERROR", "errorDetail": "docker failed"}, R.INTERNAL_ERROR),
    ],
)
def test_never_passed_without_valid_evidence(kw, reason):
    v = ev(**kw)
    assert v.status == S.INTERRUPTED
    assert v.reason == reason


def test_xml_entity_attack_is_rejected():
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><testsuite tests="0">&a;</testsuite>'
    with pytest.raises(InvalidReport):
        parse_junit(bomb, EXPECTED)


def test_foreign_test_in_report_is_rejected():
    xml = (
        junit([(101, 2, "pass"), (102, 1, "pass")])
        .replace("</testsuite>", '<testcase classname="evil_module" name="test_x" time="0"/></testsuite>')
        .replace('tests="2"', 'tests="3"')
    )
    with pytest.raises(InvalidReport):
        parse_junit(xml, EXPECTED)
