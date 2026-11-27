"""C4 L3: Execution & Results API — FR-06..FR-12."""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps.auth import CAN_EXPLAIN, CAN_READ, CAN_REPORT, CAN_RUN
from app.api.deps.providers import orchestrator, results_service
from app.api.schemas import (
    CoverageOut,
    EvidenceOut,
    ExecutionAccepted,
    ExecutionCreate,
    ExecutionOut,
    ExplanationOut,
    IdResponse,
    Page,
    QualityReportOut,
    RisksOut,
)
from app.core.actor import Actor
from app.services.orchestrator import ExecutionOrchestrator
from app.services.results_service import AI_LABEL, ResultsService

router = APIRouter(tags=["executions"])


@router.post("/executions", response_model=ExecutionAccepted, status_code=status.HTTP_202_ACCEPTED)
def start_execution(
    body: ExecutionCreate, actor: Actor = Depends(CAN_RUN), orch: ExecutionOrchestrator = Depends(orchestrator)
):
    ex = orch.start_run(actor, body.project_id, body.test_case_ids)
    return ExecutionAccepted(execution_id=ex.execution_id, status=ex.status)


@router.get("/executions/{execution_id}", response_model=ExecutionOut)
def get_execution(
    execution_id: uuid.UUID, actor: Actor = Depends(CAN_READ), svc: ResultsService = Depends(results_service)
):
    return svc.get_execution(actor, execution_id)


@router.get("/projects/{project_id}/executions", response_model=Page[ExecutionOut])
def list_executions(
    project_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(CAN_READ),
    svc: ResultsService = Depends(results_service),
):
    items, total = svc.list_executions(actor, project_id, page, size)
    return Page[ExecutionOut](items=items, page=page, size=size, total=total)


@router.get("/executions/{execution_id}/logs", response_model=Page[EvidenceOut])
def execution_logs(
    execution_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(CAN_READ),
    svc: ResultsService = Depends(results_service),
):
    items, total = svc.logs(actor, execution_id, page, size)
    return Page[EvidenceOut](items=items, page=page, size=size, total=total)


@router.post(
    "/executions/{execution_id}/tests/{execution_test_id}/explanation",
    response_model=ExplanationOut,
    status_code=status.HTTP_201_CREATED,
)
def explain_failure(
    execution_id: uuid.UUID,
    execution_test_id: int,
    actor: Actor = Depends(CAN_EXPLAIN),
    svc: ResultsService = Depends(results_service),
):
    e = svc.explain(actor, execution_id, execution_test_id)
    return ExplanationOut(
        explanation_id=e.explanation_id,
        explanation_text=e.explanation_text,
        label=AI_LABEL,
        provider_model=e.provider_model,
        created_at=e.created_at,
    )


@router.get("/projects/{project_id}/coverage", response_model=CoverageOut)
def coverage(project_id: int, actor: Actor = Depends(CAN_READ), svc: ResultsService = Depends(results_service)):
    return CoverageOut(requirements=svc.coverage(actor, project_id))


@router.get("/projects/{project_id}/risks", response_model=RisksOut)
def risks(project_id: int, actor: Actor = Depends(CAN_READ), svc: ResultsService = Depends(results_service)):
    return RisksOut(risks=svc.risks(actor, project_id))


@router.post("/projects/{project_id}/reports", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def create_report(project_id: int, actor: Actor = Depends(CAN_REPORT), svc: ResultsService = Depends(results_service)):
    return IdResponse(id=svc.generate_report(actor, project_id).report_id)


@router.get("/reports/{report_id}", response_model=QualityReportOut)
def get_report(report_id: int, actor: Actor = Depends(CAN_READ), svc: ResultsService = Depends(results_service)):
    return svc.get_report(actor, report_id)
