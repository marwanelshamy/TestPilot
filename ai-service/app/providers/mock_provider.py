"""Deterministic offline provider — the default for demos and tests (no API key, no cost, no data leaves
the machine). It produces real, runnable pytest code from the code under test when one is given."""

import ast
import re

from app.providers import ExplainRequest, SuggestRequest


def _first_function(code: str | None) -> tuple[str, int] | None:
    if not code:
        return None
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            return node.name, len(node.args.args)
    return None


def _call(name: str, value: str, count: int) -> str:
    return f"{name}({', '.join([value] * count)})"


class MockProvider:
    name = "mock"
    model = "mock-1"

    def suggest_tests(self, req: SuggestRequest) -> dict:
        fn = _first_function(req.code_under_test)
        suggestions = []
        for t in req.test_types:
            if fn:
                name, n = fn
                tests = {
                    "NORMAL": f"def test_{name}_runs_with_typical_input():\n    {_call(name, '1', n)}\n",
                    "BOUNDARY": f"def test_{name}_accepts_zero_values():\n    {_call(name, '0', n)}\n",
                    "NEGATIVE": (
                        f"def test_{name}_rejects_wrong_argument_count():\n"
                        f"    with pytest.raises(TypeError):\n"
                        f"        {_call(name, '1', n + 1)}\n"
                    ),
                }
                code = "import pytest\n\n" + req.code_under_test.rstrip() + "\n\n\n" + tests[t]
                title = f"{t.lower()} case for {name}()"
            else:
                slug = re.sub(r"[^a-z0-9]+", "_", req.requirement_text.lower())[:30].strip("_") or "requirement"
                code = (
                    "import pytest\n\n\n"
                    f"def test_{slug}_{t.lower()}():\n"
                    '    pytest.skip("mock suggestion: paste the code under test to get a runnable test")\n'
                )
                title = f"{t.lower()} case (needs code under test)"
            suggestions.append(
                {
                    "title": title,
                    "description": f"Mock {t} suggestion generated offline.",
                    "testType": t,
                    "testCode": code,
                }
            )
            if len(suggestions) >= req.max_suggestions:
                break
        return {"suggestions": suggestions}

    def explain_failure(self, req: ExplainRequest) -> dict:
        first = ((req.failure_message or "the failure").strip().splitlines() or ["the failure"])[0][:200]
        return {
            "explanationText": (
                f"Possible cause (offline mock): the assertion reported '{first}'. Compare the expected value in "
                "the test with what the code returns for the same input, and check the log excerpt for the "
                "values involved."
            )
        }
