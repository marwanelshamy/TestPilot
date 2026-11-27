"""Validates runner output and maps it to a verdict (tactic T2 sanity checking; ADR-006; QAS-7).

Mapping table: docs/phase1/03-contracts-and-data.md §2.  Only a COMPLETED run with a valid JUnit-XML
report that covers every requested test, and an exit code consistent with that report, can become
PASSED or FAILED. Everything else is INTERRUPTED with a reason — never PASSED.
"""

import re
from dataclasses import dataclass, field

from defusedxml import ElementTree as SafeET  # runner output is untrusted: no XML entity expansion

from app.core.enums import ExecutionStatus, TerminationReason, TestResultStatus
from app.core.messages import ExecutionFinished

_TC_RE = re.compile(r"test_tc_(\d+)_v(\d+)")

TestOutcome = tuple[TestResultStatus, int | None, str | None]  # (status, duration_ms, failure_message)


@dataclass
class Verdict:
    status: ExecutionStatus
    reason: TerminationReason
    results: dict[int, TestOutcome] = field(default_factory=dict)
    note: str | None = None


class InvalidReport(Exception):
    pass


def parse_junit(xml_text: str, expected: dict[int, int]) -> dict[int, TestOutcome]:
    """Parse pytest's JUnit XML into one outcome per requested test case.

    expected: {test_case_id: version}. A test case file may contain several test functions:
    the case is FAILED if any failed, ERROR if any errored, SKIPPED if all skipped, else PASSED.
    Raises InvalidReport for anything malformed, inconsistent or incomplete.
    """
    try:
        root = SafeET.fromstring(xml_text)
    except Exception as e:  # ParseError, entity/DTD attacks rejected by defusedxml
        raise InvalidReport(f"unparseable JUnit XML: {type(e).__name__}") from e

    suites = [root] if root.tag == "testsuite" else root.findall("testsuite") if root.tag == "testsuites" else []
    if not suites:
        raise InvalidReport("no <testsuite> element")

    per_case: dict[int, list[tuple[TestResultStatus, float, str | None]]] = {}
    for suite in suites:
        cases = suite.findall("testcase")
        declared = suite.get("tests")
        if declared is None or not declared.isdigit() or int(declared) != len(cases):
            raise InvalidReport("testsuite 'tests' count does not match <testcase> elements")
        for c in cases:
            ident = " ".join(filter(None, [c.get("classname"), c.get("name"), c.get("file")]))
            m = _TC_RE.search(ident)
            if not m:
                raise InvalidReport(f"test '{ident}' does not belong to any requested test case")
            tc_id, ver = int(m.group(1)), int(m.group(2))
            if expected.get(tc_id) != ver:
                raise InvalidReport(f"unexpected test case {tc_id} v{ver} in report")
            try:
                secs = float(c.get("time", "0") or 0)
            except ValueError as e:
                raise InvalidReport("invalid time attribute") from e
            failure, error, skipped = c.find("failure"), c.find("error"), c.find("skipped")
            if error is not None:
                st, msg = TestResultStatus.ERROR, error.get("message") or (error.text or "")
            elif failure is not None:
                st, msg = TestResultStatus.FAILED, failure.get("message") or (failure.text or "")
            elif skipped is not None:
                st, msg = TestResultStatus.SKIPPED, skipped.get("message")
            else:
                st, msg = TestResultStatus.PASSED, None
            per_case.setdefault(tc_id, []).append((st, secs, (msg or "")[:4000] or None))

    missing = [tc for tc in expected if tc not in per_case]
    if missing:
        raise InvalidReport(f"report is missing requested test case(s) {missing}")

    out: dict[int, TestOutcome] = {}
    for tc_id, items in per_case.items():
        statuses = [s for s, _, _ in items]
        if TestResultStatus.ERROR in statuses:
            st = TestResultStatus.ERROR
        elif TestResultStatus.FAILED in statuses:
            st = TestResultStatus.FAILED
        elif all(s == TestResultStatus.SKIPPED for s in statuses):
            st = TestResultStatus.SKIPPED
        else:
            st = TestResultStatus.PASSED
        msg = next((m for s, _, m in items if s == st and m), None)
        out[tc_id] = (st, int(round(sum(t for _, t, _ in items) * 1000)), msg)
    return out


def evaluate(msg: ExecutionFinished, expected: dict[int, int]) -> Verdict:
    """Decide the terminal status from an ExecutionFinished message."""
    partial: dict[int, TestOutcome] = {}
    if msg.junitXml:
        try:
            partial = parse_junit(msg.junitXml, expected)
        except InvalidReport:
            partial = {}

    if msg.outcome == "TIMEOUT":
        return Verdict(ExecutionStatus.INTERRUPTED, TerminationReason.TIMEOUT, partial, "time limit exceeded")
    if msg.outcome == "RESOURCE_LIMIT":
        return Verdict(ExecutionStatus.INTERRUPTED, TerminationReason.RESOURCE_LIMIT, {}, "resource limit exceeded")
    if msg.outcome == "ERROR":
        return Verdict(ExecutionStatus.INTERRUPTED, TerminationReason.INTERNAL_ERROR, {}, msg.errorDetail)

    # outcome == COMPLETED: the report must be valid and consistent with the exit code
    if not msg.junitXml:
        return Verdict(ExecutionStatus.INTERRUPTED, TerminationReason.INVALID_REPORT, {}, "no JUnit report")
    try:
        results = parse_junit(msg.junitXml, expected)
    except InvalidReport as e:
        return Verdict(ExecutionStatus.INTERRUPTED, TerminationReason.INVALID_REPORT, {}, str(e))

    any_bad = any(s in (TestResultStatus.FAILED, TestResultStatus.ERROR) for s, _, _ in results.values())
    # pytest exit codes: 0 = all passed, 1 = some tests failed. Anything else (2 interrupted,
    # 3 internal error, 4 usage error, 5 no tests) or a mismatch with the report is not trustworthy.
    if msg.exitCode not in (0, 1) or (msg.exitCode == 0) == any_bad:
        return Verdict(
            ExecutionStatus.INTERRUPTED,
            TerminationReason.INVALID_REPORT,
            {},
            f"exit code {msg.exitCode} inconsistent with report",
        )
    status = ExecutionStatus.FAILED if any_bad else ExecutionStatus.PASSED
    return Verdict(status, TerminationReason.COMPLETED, results)
