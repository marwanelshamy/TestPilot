"""Initial schema: the 13 entities of the M2 Data view + processed_message (= db/schema.sql).

Revision ID: 0001
Revises:
Create Date: 2026-11-27
"""

from alembic import op

from app.core.database import Base
from app.repositories import models  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The ORM models are the executable form of db/schema.sql; tests/unit/test_schema_drift.py
    # fails if the two ever disagree on tables or columns.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
