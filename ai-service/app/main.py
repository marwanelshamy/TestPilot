"""AI Assistance Service (contract I2, docs/contracts/ai-service-api.openapi.yaml).

Run: `uvicorn --factory app.main:create_app --port 8001`. Internal network only; no database (ASR-3).
"""

import logging
import uuid
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import AiSettings
from app.providers import LLMProvider, build_provider
from app.service import AiAssistance, AiError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TestTypeName = Literal["NORMAL", "BOUNDARY", "NEGATIVE"]


class SuggestIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requirementText: str = Field(min_length=1, max_length=10000)
    codeUnderTest: str | None = Field(default=None, max_length=20000)
    language: Literal["python"]
    framework: Literal["pytest"]
    testTypes: list[TestTypeName] = Field(default_factory=lambda: ["NORMAL", "BOUNDARY", "NEGATIVE"], min_length=1)
    maxSuggestions: int = Field(default=5, ge=1, le=10)


class ExplainIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    testCode: str = Field(max_length=20000)
    failureMessage: str = Field(max_length=4000)
    logExcerpt: str = Field(default="", max_length=8000)


def _error(request: Request, status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    cid = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex[:12]
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}, "correlationId": cid}},
    )


def create_app(settings: AiSettings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    settings = settings or AiSettings()
    ai = AiAssistance(settings, provider or build_provider(settings))

    app = FastAPI(title="TestPilot AI — AI Assistance Service", version="1.0.0")
    app.state.ai = ai

    @app.exception_handler(AiError)
    async def ai_error(request: Request, exc: AiError):
        return _error(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        fields = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "error": e["msg"]} for e in exc.errors()]
        return _error(request, 400, "VALIDATION_ERROR", "Invalid request", {"fields": fields})

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "provider": ai.provider.name,
            "model": ai.provider.model,
            "llmCircuit": ai.breaker.state,
            "cache": {"entries": len(ai.cache.data), "hits": ai.cache.hits, "misses": ai.cache.misses},
        }

    @app.post("/v1/test-suggestions")
    def test_suggestions(body: SuggestIn):
        r = ai.suggest(body.requirementText, body.codeUnderTest, body.testTypes, body.maxSuggestions)
        return {
            "suggestions": [s.model_dump() for s in r.suggestions],
            "providerModel": r.provider_model,
            "redactions": r.redactions,
            "cached": r.cached,
        }

    @app.post("/v1/failure-explanations")
    def failure_explanations(body: ExplainIn):
        text = ai.explain(body.testCode, body.failureMessage, body.logExcerpt)
        return {"explanationText": text, "providerModel": ai.provider_model, "aiGenerated": True}

    return app
