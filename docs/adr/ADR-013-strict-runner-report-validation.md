# ADR-013: Strict validation of runner output before PASSED or FAILED

| Field | Content |
|---|---|
| ADR number & title | ADR-013: Strict validation of runner output before PASSED or FAILED |
| Status | Accepted |
| Date & deciders | 27 November 2026 - Member 1 (Execution Orchestrator), reviewed with Member 2 |
| Context | M2 ADR-006 says pass/fail comes only from valid runner output but does not define 'valid'. A partial report, a report for other tests, or a forged report must never become PASSED (QAS-7). |
| Alternatives considered | 1. Trust any parsable JUnit XML: simplest, but a crashed or forged run can look like a pass.<br>2. Valid XML and every requested test present (matched by the file name `test_tc_<id>_v<version>.py`) and consistent test counts and a pytest exit code consistent with the failures (chosen).<br>3. Let the runner decide pass/fail: moves the decision next to untrusted code, contradicting ADR-006. |
| Decision | `report_validator.evaluate()`: COMPLETED plus a valid, complete, consistent report gives PASSED/FAILED; anything else gives INTERRUPTED with INVALID_REPORT, TIMEOUT, RESOURCE_LIMIT or INTERNAL_ERROR. XML is parsed with defusedxml (no entity expansion). |
| Rationale | Turns ADR-006 into checkable rules; the exit-code cross-check blocks the simple fake pass (`os._exit(0)`), measured in QAS-3 and QAS-7. |
| Consequences | + 16 unit tests and a cross-check against real pytest output (Phase 2). - A test file that cannot be imported (pytest exit code 2) is reported as INTERRUPTED/INVALID_REPORT rather than 'ERROR in test N': less helpful, never unsafe (open improvement). |
