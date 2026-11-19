"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-11

The baseline creates every table from the SQLAlchemy models (dialect-aware: JSONB, UUID and indexes on
PostgreSQL). Subsequent changes should be generated with `alembic revision --autogenerate` against PostgreSQL.
"""
import app.models  # noqa: F401
from alembic import op
from app.database import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
