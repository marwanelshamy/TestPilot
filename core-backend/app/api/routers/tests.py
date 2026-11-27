"""C4 L3: Test Case & Approval API — FR-03..FR-05 (+ manual entry, ADR-009)."""

from fastapi import APIRouter, Depends, Query, status

from app.api.deps.auth import CAN_APPROVE, CAN_EDIT_TESTS, CAN_FLAG, CAN_READ
from app.api.deps.providers import test_case_service
from app.api.schemas import (
    ApprovalDecisionIn,
    FlagCreate,
    GenerateTestsRequest,
    GenerateTestsResponse,
    IdResponse,
    Page,
    TestCaseCreate,
    TestCaseOut,
    TestCaseUpdate,
    VersionOut,
)
from app.core.actor import Actor
from app.core.enums import ApprovalDecision, TestCaseStatus, TestSource
from app.services.test_case_service import TestCaseService

router = APIRouter(tags=["tests"])


def to_out(svc: TestCaseService, tc) -> TestCaseOut:
    return TestCaseOut(
        test_case_id=tc.test_case_id,
        project_id=tc.project_id,
        title=tc.title,
        description=tc.description,
        test_type=tc.test_type,
        source=tc.source,
        test_code=tc.test_code,
        status=tc.status,
        version=tc.version,
        requirement_ids=[r.requirement_id for r in tc.requirements],
        approved_version=svc.approved_version(tc),
        ai_generated=tc.source == TestSource.AI_GENERATED,
        updated_at=tc.updated_at,
    )


@router.post(
    "/projects/{project_id}/tests/generate", response_model=GenerateTestsResponse, status_code=status.HTTP_201_CREATED
)
def generate_tests(
    project_id: int,
    body: GenerateTestsRequest,
    actor: Actor = Depends(CAN_EDIT_TESTS),
    svc: TestCaseService = Depends(test_case_service),
):
    ids = svc.generate(actor, project_id, body.requirement_id, body.test_types, body.code_under_test)
    return GenerateTestsResponse(test_ids=ids)


@router.post("/projects/{project_id}/tests", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def create_test(
    project_id: int,
    body: TestCaseCreate,
    actor: Actor = Depends(CAN_EDIT_TESTS),
    svc: TestCaseService = Depends(test_case_service),
):
    tc = svc.create_manual(
        actor, project_id, body.title, body.description, body.test_type, body.test_code, body.requirement_ids
    )
    return IdResponse(id=tc.test_case_id)


@router.get("/projects/{project_id}/tests", response_model=Page[TestCaseOut])
def list_tests(
    project_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status_filter: TestCaseStatus | None = Query(None, alias="status"),
    actor: Actor = Depends(CAN_READ),
    svc: TestCaseService = Depends(test_case_service),
):
    items, total = svc.list_tests(actor, project_id, status_filter, page, size)
    return Page[TestCaseOut](items=[to_out(svc, t) for t in items], page=page, size=size, total=total)


@router.get("/tests/{test_id}", response_model=TestCaseOut)
def get_test(test_id: int, actor: Actor = Depends(CAN_READ), svc: TestCaseService = Depends(test_case_service)):
    return to_out(svc, svc.get(actor, test_id))


@router.put("/tests/{test_id}", response_model=VersionOut)
def update_test(
    test_id: int,
    body: TestCaseUpdate,
    actor: Actor = Depends(CAN_EDIT_TESTS),
    svc: TestCaseService = Depends(test_case_service),
):
    changes = body.model_dump(exclude_unset=True)
    return VersionOut(version=svc.update(actor, test_id, changes).version)


@router.post("/tests/{test_id}/approve", response_model=TestCaseOut)
def approve_test(
    test_id: int,
    body: ApprovalDecisionIn,
    actor: Actor = Depends(CAN_APPROVE),
    svc: TestCaseService = Depends(test_case_service),
):
    return to_out(svc, svc.decide(actor, test_id, body.version, ApprovalDecision.APPROVED, body.comment))


@router.post("/tests/{test_id}/reject", response_model=TestCaseOut)
def reject_test(
    test_id: int,
    body: ApprovalDecisionIn,
    actor: Actor = Depends(CAN_APPROVE),
    svc: TestCaseService = Depends(test_case_service),
):
    return to_out(svc, svc.decide(actor, test_id, body.version, ApprovalDecision.REJECTED, body.comment))


@router.post("/tests/{test_id}/flags", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def flag_test(
    test_id: int, body: FlagCreate, actor: Actor = Depends(CAN_FLAG), svc: TestCaseService = Depends(test_case_service)
):
    return IdResponse(id=svc.flag(actor, test_id, body.comment).flag_id)
