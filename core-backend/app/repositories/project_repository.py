"""C4 L3: Project Repository — projects, membership and requirements (P7)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repositories.models import Project, ProjectMember, Requirement


class ProjectRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, project: Project, member_ids: list[int]) -> Project:
        self.s.add(project)
        self.s.flush()
        for uid in dict.fromkeys(member_ids):
            self.s.add(ProjectMember(project_id=project.project_id, user_id=uid))
        self.s.flush()
        return project

    def add_member(self, project_id: int, user_id: int) -> None:
        if not self.is_member(project_id, user_id):
            self.s.add(ProjectMember(project_id=project_id, user_id=user_id))
            self.s.flush()

    def get(self, project_id: int) -> Project | None:
        return self.s.get(Project, project_id)

    def is_member(self, project_id: int, user_id: int) -> bool:
        return self.s.get(ProjectMember, (project_id, user_id)) is not None

    def list_for_user(self, user_id: int, offset: int, limit: int) -> tuple[list[Project], int]:
        base = select(Project).join(ProjectMember).where(ProjectMember.user_id == user_id)
        total = self.s.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.s.scalars(base.order_by(Project.project_id.desc()).offset(offset).limit(limit)).all()
        return list(rows), total

    # --- requirements ---
    def add_requirement(self, req: Requirement) -> Requirement:
        self.s.add(req)
        self.s.flush()
        return req

    def get_requirement(self, requirement_id: int) -> Requirement | None:
        return self.s.get(Requirement, requirement_id)

    def list_requirements(self, project_id: int, offset: int, limit: int) -> tuple[list[Requirement], int]:
        base = select(Requirement).where(Requirement.project_id == project_id)
        total = self.s.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.s.scalars(
            base.order_by(Requirement.created_at, Requirement.requirement_id).offset(offset).limit(limit)
        ).all()
        return list(rows), total
