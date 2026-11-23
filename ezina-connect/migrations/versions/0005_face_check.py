"""selfie face check: face_* columns on identity_documents (SELFIE rows only)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20

0001 builds the baseline with create_all from the *current* models, so a database created from scratch already has
these columns when it reaches this revision. Every step checks first and only adds what is missing. No new tables.
"""
import sqlalchemy as sa
from alembic import op

from app.database import JSONType

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_STATUS_CK = "ck_identity_documents_face_check_status"
_ONLY_CK = "ck_identity_documents_face_only_selfie"
_FK = "fk_identity_documents_face_compared_id"
_IX = "ix_identity_documents_face_check_status"
_STATUSES = "('PENDING_ID','MATCHED','MISMATCH','NO_FACE_ID','NO_FACE_SELFIE','LIVENESS_FAILED','ERROR','SKIPPED')"
_ONLY = (
    "kind = 'SELFIE' OR (face_check_status IS NULL AND face_compared_id_document_id IS NULL AND face_verified IS NULL "
    "AND face_distance IS NULL AND face_threshold IS NULL AND face_confidence_band IS NULL AND "
    "face_liveness_passed IS NULL AND face_found_id IS NULL AND face_found_selfie IS NULL AND face_model IS NULL AND "
    "face_detector IS NULL AND face_processing_ms IS NULL AND face_warnings IS NULL AND face_error_message IS NULL AND "
    "face_checked_at IS NULL AND face_check_attempts = 0)"
)
_DROP_ORDER = (
    "face_checked_at", "face_check_attempts", "face_error_message", "face_warnings", "face_processing_ms",
    "face_detector", "face_model", "face_found_selfie", "face_found_id", "face_liveness_passed",
    "face_confidence_band", "face_threshold", "face_distance", "face_verified", "face_compared_id_document_id",
    "face_check_status",
)


def _columns() -> dict[str, sa.Column]:
    return {
        "face_check_status": sa.Column("face_check_status", sa.String(16)),
        "face_compared_id_document_id": sa.Column("face_compared_id_document_id", sa.Uuid()),
        "face_verified": sa.Column("face_verified", sa.Boolean()),
        "face_distance": sa.Column("face_distance", sa.Numeric(8, 5)),
        "face_threshold": sa.Column("face_threshold", sa.Numeric(8, 5)),
        "face_confidence_band": sa.Column("face_confidence_band", sa.Text()),
        "face_liveness_passed": sa.Column("face_liveness_passed", sa.Boolean()),
        "face_found_id": sa.Column("face_found_id", sa.Boolean()),
        "face_found_selfie": sa.Column("face_found_selfie", sa.Boolean()),
        "face_model": sa.Column("face_model", sa.Text()),
        "face_detector": sa.Column("face_detector", sa.Text()),
        "face_processing_ms": sa.Column("face_processing_ms", sa.Numeric(12, 1)),
        "face_warnings": sa.Column("face_warnings", JSONType),
        "face_error_message": sa.Column("face_error_message", sa.Text()),
        "face_check_attempts": sa.Column("face_check_attempts", sa.Integer(), nullable=False, server_default="0"),
        "face_checked_at": sa.Column("face_checked_at", sa.DateTime(timezone=True)),
    }


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("identity_documents"):
        return
    existing = {c["name"] for c in insp.get_columns("identity_documents")}
    cols = _columns()
    missing = [n for n in cols if n not in existing]
    if not missing:
        return
    with op.batch_alter_table("identity_documents") as b:
        for n in missing:
            b.add_column(cols[n])
        b.create_index(_IX, ["face_check_status"])
        b.create_foreign_key(_FK, "identity_documents", ["face_compared_id_document_id"], ["id"], ondelete="SET NULL")
        b.create_check_constraint(_STATUS_CK, f"face_check_status IS NULL OR face_check_status IN {_STATUSES}")
        b.create_check_constraint(_ONLY_CK, _ONLY)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("identity_documents"):
        return
    existing = {c["name"] for c in insp.get_columns("identity_documents")}
    if "face_check_status" not in existing:
        return
    with op.batch_alter_table("identity_documents") as b:
        b.drop_constraint(_ONLY_CK, type_="check")
        b.drop_constraint(_STATUS_CK, type_="check")
        # the self-referencing foreign key goes with its column
        b.drop_index(_IX)
        for n in _DROP_ORDER:
            if n in existing:
                b.drop_column(n)
