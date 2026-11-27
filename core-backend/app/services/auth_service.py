"""Login and current-user lookup (simple login with JWT, assumption A-04)."""

from sqlalchemy.orm import Session

from app.core.errors import Unauthorized
from app.core.security import create_token, verify_password
from app.repositories.models import User
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, session: Session):
        self.users = UserRepository(session)

    def login(self, email: str, password: str) -> tuple[str, User]:
        user = self.users.by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise Unauthorized("Wrong e-mail or password", code="INVALID_CREDENTIALS")
        return create_token(user.user_id, user.role.value), user

    def get_user(self, user_id: int) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise Unauthorized("User no longer exists")
        return user
