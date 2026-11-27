"""POST /api/auth/login, GET /api/me."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps.auth import current_actor
from app.api.schemas import LoginRequest, LoginResponse, UserOut
from app.core.actor import Actor
from app.core.database import get_session
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    token, user = AuthService(session).login(body.email, body.password)
    return LoginResponse(token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    return AuthService(session).get_user(actor.user_id)
