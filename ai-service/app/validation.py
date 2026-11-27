"""Sanity checking of model output (tactic T2). Invalid suggestions are DROPPED, never forwarded.

The Core Backend checks again before storing (defence in depth), but this service must only ever return
suggestions that are valid Python, define at least one pytest test, and use an allowed test type.
"""

import ast
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

TestType = Literal["NORMAL", "BOUNDARY", "NEGATIVE"]


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    testType: TestType
    testCode: str = Field(min_length=1, max_length=20000)


class InvalidModelOutput(Exception):
    pass


def defines_pytest_test(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    return any(
        isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test") for n in ast.walk(tree)
    )


def validate_suggestions(raw: object, allowed_types: list[str], limit: int) -> list[Suggestion]:
    """raw must be {"suggestions": [...]}. Returns the valid ones; raises if the shape is wrong or
    nothing valid remains."""
    if not isinstance(raw, dict) or not isinstance(raw.get("suggestions"), list):
        raise InvalidModelOutput("model output is not {suggestions: [...]}")
    out: list[Suggestion] = []
    seen: set[str] = set()
    for item in raw["suggestions"]:
        try:
            s = Suggestion.model_validate(item)
        except ValidationError:
            continue
        if s.testType not in allowed_types or not defines_pytest_test(s.testCode):
            continue
        key = " ".join(s.testCode.split())
        if key in seen:  # identical code twice
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    if not out:
        raise InvalidModelOutput("model returned no valid test suggestion")
    return out


def validate_explanation(raw: object) -> str:
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("explanationText"), str)
        or not raw["explanationText"].strip()
    ):
        raise InvalidModelOutput("model output is not {explanationText: str}")
    return raw["explanationText"].strip()[:4000]
