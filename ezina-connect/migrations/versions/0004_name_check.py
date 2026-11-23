"""ID name check: name_check_* columns on identity_documents

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20

0001 builds the baseline with create_all from the *current* models, so a database created from scratch already has
these columns when it reaches this revision. Every step checks first and only adds what is missing.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_CK = "ck_identity_documents_name_check_status"
_STATUSES = "('PENDING','MATCHED','PARTIAL','MISMATCH','NOT_FOUND','ERROR','SKIPPED')"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("identity_documents"):
        return
    existing = {c["name"] for c in insp.get_columns("identity_documents")}
    columns = {
        "name_check_status": sa.Column("name_check_status", sa.String(10)),
        "name_match_score": sa.Column("name_match_score", sa.Numeric(5, 2)),
        "extracted_name": sa.Column("extracted_name", sa.Text()),
        "name_checked_at": sa.Column("name_checked_at", sa.DateTime(timezone=True)),
        "name_check_attempts": sa.Column("name_check_attempts", sa.Integer(), nullable=False, server_default="0"),
    }
    missing = [n for n in columns if n not in existing]
    if not missing:
        return
    with op.batch_alter_table("identity_documents") as b:
        for n in missing:
            b.add_column(columns[n])
        if "name_check_status" in missing:
            b.create_index("ix_identity_documents_name_check_status", ["name_check_status"])
            b.create_check_constraint(_CK, f"name_check_status IS NULL OR name_check_status IN {_STATUSES}")


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("identity_documents"):
        return
    existing = {c["name"] for c in insp.get_columns("identity_documents")}
    with op.batch_alter_table("identity_documents") as b:
        if "name_check_status" in existing:
            b.drop_constraint(_CK, type_="check")
            b.drop_index("ix_identity_documents_name_check_status")
        for n in ("name_check_attempts", "name_checked_at", "extracted_name", "name_match_score", "name_check_status"):
            if n in existing:
                b.drop_column(n)
