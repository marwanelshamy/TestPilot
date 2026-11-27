"""Provider-neutral prompts and output schemas. Kept outside any adapter so a new provider reuses them
(ASR-5: "provider-specific prompts and configuration kept outside the core")."""

SUGGEST_SYSTEM = """You write pytest test cases for a software testing platform. A human reviews every \
suggestion before it runs, so be precise and honest.

Each suggestion must be ONE self-contained Python file that:
- uses only the Python standard library and pytest;
- if code under test is provided, includes that code verbatim at the top of the file (the test runs in an \
empty sandbox with no network and no other files), otherwise tests the behaviour described using a minimal \
reference implementation written in the file and clearly named as such;
- defines one or more functions whose names start with `test_`;
- has no network, file-system or subprocess access.

Cover the requested test types: NORMAL (typical valid input), BOUNDARY (edges such as zero, empty, \
limits) and NEGATIVE (invalid input that must be rejected, e.g. with pytest.raises). Give each suggestion \
a short title and a one-sentence description of what it checks."""


def suggest_user_prompt(requirement: str, code: str | None, test_types: list[str], n: int) -> str:
    parts = [f"Requirement:\n{requirement}"]
    parts.append(f"Code under test:\n```python\n{code}\n```" if code else "No code under test was provided.")
    parts.append(f"Suggest up to {n} tests covering these types: {', '.join(test_types)}.")
    return "\n\n".join(parts)


SUGGESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "testType": {"type": "string", "enum": ["NORMAL", "BOUNDARY", "NEGATIVE"]},
                    "testCode": {"type": "string"},
                },
                "required": ["title", "description", "testType", "testCode"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}

EXPLAIN_SYSTEM = """You help developers investigate a failed pytest test. You see the test code, the \
failure message and a log excerpt. Explain the most likely cause in 2-5 sentences and suggest what to check \
next. This is a hypothesis shown to a human next to the real logs: say when you are unsure, and never \
claim the code is correct or that the test passed."""


def explain_user_prompt(test_code: str, failure: str, logs: str) -> str:
    return (
        f"Test code:\n```python\n{test_code}\n```\n\nFailure message:\n{failure or '(none)'}\n\n"
        f"Log excerpt:\n{logs or '(none)'}"
    )


EXPLANATION_SCHEMA = {
    "type": "object",
    "properties": {"explanationText": {"type": "string"}},
    "required": ["explanationText"],
    "additionalProperties": False,
}
