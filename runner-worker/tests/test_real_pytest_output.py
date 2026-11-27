"""Runs REAL pytest with the exact command and file layout the sandbox uses (no Docker needed), to prove
the JUnit XML it produces is what the Core Backend's report validator expects: every <testcase> carries
`test_tc_<id>_v<version>`, failures carry the assertion message, and the exit code is 1 when a test fails.

This runs trusted test code from this file only, in a temp folder. It is NOT a sandbox."""

import subprocess
import sys
import xml.etree.ElementTree as ET

from worker.sandbox import PYTEST_CMD, build_test_files


def run_like_sandbox(job, tmp_path):
    for rel, code in build_test_files(job).items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code, encoding="utf-8")
    cmd = [sys.executable, *PYTEST_CMD[1:]]
    cmd = [c.replace("/work/report.xml", str(tmp_path / "report.xml")) for c in cmd]
    proc = subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True, timeout=120)
    return proc, (tmp_path / "report.xml").read_text(encoding="utf-8")


def test_real_pytest_report_shape(job, tmp_path):
    proc, xml = run_like_sandbox(job, tmp_path)
    assert proc.returncode == 1  # one passing, one failing test
    root = ET.fromstring(xml)
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    cases = suite.findall("testcase")
    assert int(suite.get("tests")) == len(cases) == 2
    names = sorted(c.get("classname") for c in cases)
    assert names == ["tests.test_tc_101_v2", "tests.test_tc_102_v1"]
    failed = next(c for c in cases if c.get("classname").endswith("102_v1"))
    assert "math is hard" in failed.find("failure").get("message")
