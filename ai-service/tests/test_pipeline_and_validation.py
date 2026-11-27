"""C-07 redaction pipeline (P5) and T2 output validation."""

import pytest

from app.pipeline import RedactionPipeline, RedactionReport
from app.validation import InvalidModelOutput, validate_explanation, validate_suggestions

SECRETS = {
    "aws": "AKIAABCDEFGHIJKLMNOP",
    "anthropic": "sk-ant-api03-abcdefghijklmnopqrstuvwx",
    "github": "ghp_abcdefghijklmnopqrstuvwxyz0123",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlLXZhbHVl",
    "db_password": "hunter2-very-secret",
    "conn_password": "p4ssw0rd",
}

LEAKY = f"""
AWS_KEY = "{SECRETS["aws"]}"
client = Client(api_key="{SECRETS["anthropic"]}")
GITHUB_TOKEN={SECRETS["github"]}
headers = {{"Authorization": "Bearer {SECRETS["jwt"]}"}}
DB_PASSWORD = '{SECRETS["db_password"]}'
url = "postgresql://admin:{SECRETS["conn_password"]}@db:5432/app"
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAsecretsecret
-----END RSA PRIVATE KEY-----
def add(a, b):
    return a + b
"""


def test_every_secret_is_removed_and_code_survives():
    report = RedactionReport()
    out = RedactionPipeline(10000).run(LEAKY, report)
    for name, value in SECRETS.items():
        assert value not in out, f"{name} leaked"
    assert "PRIVATE KEY-----\nMIIE" not in out and "[REDACTED_PRIVATE_KEY]" in out
    assert "def add(a, b):\n    return a + b" in out  # the actual code is untouched
    assert report.secrets_removed >= 7


def test_plain_code_is_not_changed():
    code = "def password_strength(pw):\n    return len(pw) >= 8\n"
    report = RedactionReport()
    assert RedactionPipeline(10000).run(code, report) == code.strip("\n")
    assert report.secrets_removed == 0


def test_context_is_minimised_and_limited():
    report = RedactionReport()
    out = RedactionPipeline(50).run("a   \n\n\n\nb\n" + "x" * 200, report)
    assert out.startswith("a\n\nb\n") and report.truncated and "truncated by TestPilot" in out


GOOD = "def test_x():\n    assert 1\n"


def test_invalid_suggestions_are_dropped_not_forwarded():
    raw = {
        "suggestions": [
            {"title": "ok", "testType": "NORMAL", "testCode": GOOD},
            {"title": "syntax error", "testType": "NORMAL", "testCode": "def test_y(:\n"},
            {"title": "no test fn", "testType": "NORMAL", "testCode": "x = 1\n"},
            {"title": "bad type", "testType": "SMOKE", "testCode": GOOD + "\n"},
            {"title": "duplicate", "testType": "NORMAL", "testCode": GOOD},
            {"title": "not asked", "testType": "NEGATIVE", "testCode": "def test_z():\n    pass\n"},
            "not even an object",
        ]
    }
    out = validate_suggestions(raw, ["NORMAL", "BOUNDARY"], limit=5)
    assert [s.title for s in out] == ["ok"]


def test_limit_and_empty_results():
    many = {
        "suggestions": [
            {"title": str(i), "testType": "NORMAL", "testCode": f"def test_{i}():\n    pass\n"} for i in range(9)
        ]
    }
    assert len(validate_suggestions(many, ["NORMAL"], limit=3)) == 3
    with pytest.raises(InvalidModelOutput):
        validate_suggestions({"suggestions": []}, ["NORMAL"], 3)
    with pytest.raises(InvalidModelOutput):
        validate_suggestions(["wrong shape"], ["NORMAL"], 3)
    with pytest.raises(InvalidModelOutput):
        validate_explanation({"explanationText": "   "})
