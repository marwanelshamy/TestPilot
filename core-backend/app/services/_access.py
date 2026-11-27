"""Project-membership rule shared by the services (the Auth & Access Filter checks token and role;
membership depends on data, so the business layer enforces it)."""

from app.core.actor import Actor
from app.core.errors import Forbidden, NotFound
from app.repositories.models import Project
from app.repositories.project_repository import ProjectRepository


def require_member(projects: ProjectRepository, actor: Actor, project_id: int) -> Project:
    project = projects.get(project_id)
    if project is None:
        raise NotFound(f"Project {project_id} not found")
    if not projects.is_member(project_id, actor.user_id):
        raise Forbidden("You are not a member of this project")
    return project


def page_args(page: int, size: int) -> tuple[int, int]:
    page = max(page, 1)
    size = min(max(size, 1), 100)
    return (page - 1) * size, size
