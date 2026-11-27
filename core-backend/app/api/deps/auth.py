"""C4 L3: Auth & Access Filter — checks the JWT on every call and the caller's role (tactic T9).

Project membership is data-dependent and is enforced by the business layer (app.services._access).
Role matrix: docs/phase1/03-contracts-and-data.md §3.
"""

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.database import get_session
from app.core.enums import Role
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.services.auth_service import AuthService


def current_actor(request: Request, session: Session = Depends(get_session)) -> Actor:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("Missing bearer token")
    claims = decode_token(token)
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError) as e:
        raise Unauthorized("Invalid token") from e
    user = AuthService(session).get_user(user_id)  # role is re-read from the DB, not trusted from the token
    return Actor(user_id=user.user_id, role=user.role)


def require_roles(*roles: Role) -> Callable[..., Actor]:
    allowed = set(roles)

    def dep(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.role not in allowed:
            raise Forbidden(
                f"Role {actor.role.value} may not perform this action",
                details={"allowedRoles": sorted(r.value for r in allowed)},
            )
        return actor

    return dep


# Named role groups (one place to change the matrix)
CAN_CREATE_PROJECT = require_roles(Role.DEVELOPER, Role.TEAM_LEAD)
CAN_ADD_REQUIREMENT = require_roles(Role.DEVELOPER)
CAN_EDIT_TESTS = require_roles(Role.DEVELOPER, Role.QA_ASSISTANT)
CAN_FLAG = require_roles(Role.DEVELOPER, Role.QA_ASSISTANT, Role.TEAM_LEAD)
CAN_APPROVE = require_roles(Role.DEVELOPER, Role.TEAM_LEAD)
CAN_RUN = require_roles(Role.DEVELOPER, Role.QA_ASSISTANT, Role.TEAM_LEAD)
CAN_READ = require_roles(Role.DEVELOPER, Role.QA_ASSISTANT, Role.TEAM_LEAD)
CAN_EXPLAIN = require_roles(Role.DEVELOPER, Role.QA_ASSISTANT)
CAN_REPORT = require_roles(Role.TEAM_LEAD)
