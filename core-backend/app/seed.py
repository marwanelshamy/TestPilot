"""Idempotent demo seed: `python -m app.seed`. Accounts are listed in the README (M3 §6)."""

import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import init_engine, session_factory
from app.core.enums import Role
from app.core.security import hash_password
from app.repositories.models import Project, Requirement, User
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository

log = logging.getLogger(__name__)

DEMO_USERS = [
    ("Dina Developer", "dev@testpilot.local", Role.DEVELOPER),
    ("Qamar QA Assistant", "qa@testpilot.local", Role.QA_ASSISTANT),
    ("Laila Team Lead", "lead@testpilot.local", Role.TEAM_LEAD),
    ("Adam Admin", "admin@testpilot.local", Role.ADMIN),
]


def seed(session: Session, password: str) -> dict[str, int]:
    users = UserRepository(session)
    ids: dict[str, int] = {}
    for name, email, role in DEMO_USERS:
        u = users.by_email(email) or users.add(
            User(name=name, email=email, password_hash=hash_password(password), role=role)
        )
        ids[email] = u.user_id
    projects = ProjectRepository(session)
    existing, _ = projects.list_for_user(ids["dev@testpilot.local"], 0, 100)
    if not any(p.name == "Calculator Demo" for p in existing):
        p = projects.add(
            Project(
                name="Calculator Demo",
                description="Sample project for the M3 demo",
                created_by=ids["dev@testpilot.local"],
            ),
            member_ids=[ids["dev@testpilot.local"], ids["qa@testpilot.local"], ids["lead@testpilot.local"]],
        )
        projects.add_requirement(
            Requirement(
                project_id=p.project_id,
                title="add(a, b) returns the sum of two integers",
                description="add(a, b) returns a + b for any two integers, including negatives and zero. "
                "Non-integer input raises TypeError.",
                created_by=ids["dev@testpilot.local"],
            )
        )
    session.commit()
    return ids


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    if s.seed_demo:
        init_engine(s.database_url)
        with session_factory()() as session:
            seed(session, s.demo_password)
        log.info("demo data seeded")
