"""User Repository — supports the Auth & Access Filter (login, current user)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import User


class UserRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, user_id: int) -> User | None:
        return self.s.get(User, user_id)

    def by_email(self, email: str) -> User | None:
        return self.s.scalar(select(User).where(User.email == email.lower()))

    def add(self, user: User) -> User:
        user.email = user.email.lower()
        self.s.add(user)
        self.s.flush()
        return user
