"""The authenticated caller, passed from the API layer to services."""

from dataclasses import dataclass

from app.core.enums import Role


@dataclass(frozen=True)
class Actor:
    user_id: int
    role: Role
