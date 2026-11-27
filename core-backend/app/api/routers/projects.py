"""C4 L3: Project API — FR-01, FR-02."""

from fastapi import APIRouter, Depends, Query, status

from app.api.deps.auth import CAN_ADD_REQUIREMENT, CAN_CREATE_PROJECT, CAN_READ
from app.api.deps.providers import project_service
from app.api.schemas import IdResponse, Page, ProjectCreate, ProjectOut, RequirementCreate, RequirementOut
from app.core.actor import Actor
from app.services.project_service import ProjectService

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(CAN_READ),
    svc: ProjectService = Depends(project_service),
):
    items, total = svc.list_projects(actor, page, size)
    return Page[ProjectOut](items=items, page=page, size=size, total=total)


@router.post("/projects", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate, actor: Actor = Depends(CAN_CREATE_PROJECT), svc: ProjectService = Depends(project_service)
):
    return IdResponse(id=svc.create_project(actor, body.name, body.description).project_id)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, actor: Actor = Depends(CAN_READ), svc: ProjectService = Depends(project_service)):
    return svc.get_project(actor, project_id)


@router.post("/projects/{project_id}/requirements", response_model=IdResponse, status_code=status.HTTP_201_CREATED)
def add_requirement(
    project_id: int,
    body: RequirementCreate,
    actor: Actor = Depends(CAN_ADD_REQUIREMENT),
    svc: ProjectService = Depends(project_service),
):
    return IdResponse(id=svc.add_requirement(actor, project_id, body.title, body.description).requirement_id)


@router.get("/projects/{project_id}/requirements", response_model=Page[RequirementOut])
def list_requirements(
    project_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(CAN_READ),
    svc: ProjectService = Depends(project_service),
):
    items, total = svc.list_requirements(actor, project_id, page, size)
    return Page[RequirementOut](items=items, page=page, size=size, total=total)
