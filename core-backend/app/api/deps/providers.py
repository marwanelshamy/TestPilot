"""Dependencies that build services with the shared adapters stored on app.state."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import get_session
from app.services.orchestrator import ExecutionOrchestrator
from app.services.project_service import ProjectService
from app.services.results_service import ResultsService
from app.services.test_case_service import TestCaseService


def settings(request: Request) -> Settings:
    return request.app.state.settings


def project_service(session: Session = Depends(get_session)) -> ProjectService:
    return ProjectService(session)


def test_case_service(request: Request, session: Session = Depends(get_session)) -> TestCaseService:
    return TestCaseService(session, request.app.state.ai_client)


test_case_service.__test__ = False


def results_service(request: Request, session: Session = Depends(get_session)) -> ResultsService:
    return ResultsService(session, request.app.state.ai_client)


def orchestrator(request: Request, session: Session = Depends(get_session)) -> ExecutionOrchestrator:
    return ExecutionOrchestrator(session, request.app.state.publisher, request.app.state.settings)
