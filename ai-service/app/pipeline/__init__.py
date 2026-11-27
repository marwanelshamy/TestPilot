"""Redaction pipeline — pipe-and-filter (pattern P5, constraint C-07, tactic T8).

Every piece of user text goes through the same ordered filters BEFORE any external LLM call:
    SecretRedactor  ->  WhitespaceMinimizer  ->  LengthLimiter
Each filter takes (text, report) and returns new text, so filters can be added, removed or reordered
without touching the callers.
"""

import re
from dataclasses import dataclass, field


@dataclass
class RedactionReport:
    secrets_removed: int = 0
    truncated: bool = False
    kinds: list[str] = field(default_factory=list)


# (kind, pattern, replacement). Order matters: multi-line blocks first.
_SECRET_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "[REDACTED_PRIVATE_KEY]",
    ),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}"), "[REDACTED_API_KEY]"),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "[REDACTED_API_KEY]"),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "[REDACTED_TOKEN]"),
    ("aws_access_key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "[REDACTED_JWT]"),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"), "Bearer [REDACTED_TOKEN]"),
    (
        "url_credentials",
        re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)([^\s:/@]+):([^\s@/]+)@"),
        r"\1[REDACTED_USER]:[REDACTED_PASSWORD]@",
    ),
    (
        "assignment",
        re.compile(
            r"""(?ix)
            \b([A-Z0-9_]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|token|private[_-]?key)[A-Z0-9_]*)
            (\s*[:=]\s*)
            (['"]?)(?!\[REDACTED)([^\s'"]{4,})\3   # skip values an earlier filter already redacted
            """
        ),
        r"\1\2\3[REDACTED]\3",
    ),
]


class SecretRedactor:
    def __call__(self, text: str, report: RedactionReport) -> str:
        for kind, pattern, repl in _SECRET_PATTERNS:
            text, n = pattern.subn(repl, text)
            if n:
                report.secrets_removed += n
                report.kinds.append(kind)
        return text


class WhitespaceMinimizer:
    """Drop trailing spaces and collapse runs of blank lines (fewer tokens, same meaning)."""

    def __call__(self, text: str, report: RedactionReport) -> str:
        lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
        out: list[str] = []
        for ln in lines:
            if ln == "" and out and out[-1] == "":
                continue
            out.append(ln)
        return "\n".join(out).strip("\n")


class LengthLimiter:
    def __init__(self, max_chars: int):
        self.max_chars = max_chars

    def __call__(self, text: str, report: RedactionReport) -> str:
        if len(text) <= self.max_chars:
            return text
        report.truncated = True
        return text[: self.max_chars] + "\n# ...[context truncated by TestPilot]"


class RedactionPipeline:
    def __init__(self, max_chars: int):
        self.filters = [SecretRedactor(), WhitespaceMinimizer(), LengthLimiter(max_chars)]

    def run(self, text: str | None, report: RedactionReport) -> str | None:
        if text is None:
            return None
        for f in self.filters:
            text = f(text, report)
        return text
