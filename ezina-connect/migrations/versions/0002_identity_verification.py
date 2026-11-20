"""identity verification: identity_documents table + farmers.id_document_status / selfie_status

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19

0001 builds the baseline with create_all from the *current* models, so a database created from scratch already has
these objects when it reaches this revision. Every step therefore checks first and only adds what is missing;
a database created before the identity feature gets the new column and table here.
"""
import sqlalchemy as sa
from alembic import op

from app.database import JSONType

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_STATUSES = "('NOT_PROVIDED','RECEIVED','NEEDS_HELP','DEFERRED')"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())

    existing = {c["name"] for c in insp.get_columns("farmers")}
    for name in ("id_document_status", "selfie_status"):
        if name in existing:
            continue
        with op.batch_alter_table("farmers") as b:
            b.add_column(sa.Column(name, sa.String(20), nullable=False, server_default="NOT_PROVIDED"))
            b.create_index(f"ix_farmers_{name}", [name])
            b.create_check_constraint(f"ck_farmers_{name}", f"{name} IN {_STATUSES}")

    if not insp.has_table("identity_documents"):
        op.create_table(
            "identity_documents",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("farmer_id", sa.Uuid(), sa.ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("country", sa.String(2)),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("id_document_type", sa.String(30)),
            sa.Column("wa_media_id", sa.String(100)),
            sa.Column("storage_key", sa.String(500), nullable=False),
            sa.Column("mime_type", sa.String(100), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("challenge", sa.String(100)),
            sa.Column("challenge_issued_at", sa.DateTime(timezone=True)),
            sa.Column("quality_result", JSONType),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(12), nullable=False, server_default="ACCEPTED"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("kind IN ('ID_FRONT','ID_BACK','SELFIE')", name="ck_identity_documents_kind"),
            sa.CheckConstraint("status IN ('ACCEPTED','REJECTED','SUPERSEDED')", name="ck_identity_documents_status"),
        )
        op.create_index("ix_identity_documents_farmer_id", "identity_documents", ["farmer_id"])
        op.create_index("ix_identity_documents_kind", "identity_documents", ["kind"])
        op.create_index("ix_identity_documents_wa_media_id", "identity_documents", ["wa_media_id"])
        op.create_index("ix_identity_documents_status", "identity_documents", ["status"])
        op.create_index("ix_identity_documents_sha256", "identity_documents", ["sha256"], unique=True)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("identity_documents"):
        op.drop_table("identity_documents")
    existing = {c["name"] for c in insp.get_columns("farmers")}
    for name in ("id_document_status", "selfie_status"):
        if name in existing:
            with op.batch_alter_table("farmers") as b:
                b.drop_constraint(f"ck_farmers_{name}", type_="check")
                b.drop_index(f"ix_farmers_{name}")
                b.drop_column(name)
