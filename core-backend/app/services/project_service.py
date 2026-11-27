"""C4 L3: Project Service — projects with the one supported stack (C-01) and their requirements (FR-01, FR-02)."""

from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.repositories.models import Project, Requirement
from app.repositories.project_repository import ProjectRepository
from app.services._access import page_args, require_member


class ProjectService:
    def __init__(self, session: Session):
        self.s = session
        self.projects = ProjectRepository(session)

    def create_project(self, actor: Actor, name: str, description: str | None) -> Project:
        project = Project(
            name=name.strip(),
            description=description,
            programming_language="Python",
            test_framework="pytest",
            created_by=actor.user_id,
        )
        self.projects.add(project, member_ids=[actor.user_id])
        self.s.commit()
        return project

    def list_projects(self, actor: Actor, page: int, size: int) -> tuple[list[Project], int]:
        offset, limit = page_args(page, size)
        return self.projects.list_for_user(actor.user_id, offset, limit)

    def get_project(self, actor: Actor, project_id: int) -> Project:
        return require_member(self.projects, actor, project_id)

    def add_requirement(self, actor: Actor, project_id: int, title: str, description: str) -> Requirement:
        require_member(self.projects, actor, project_id)
        req = self.projects.add_requirement(
            Requirement(project_id=project_id, title=title.strip(), description=description, created_by=actor.user_id)
        )
        self.s.commit()
        return req

    def list_requirements(self, actor: Actor, project_id: int, page: int, size: int) -> tuple[list[Requirement], int]:
        require_member(self.projects, actor, project_id)
        offset, limit = page_args(page, size)
        return self.projects.list_requirements(project_id, offset, limit)
