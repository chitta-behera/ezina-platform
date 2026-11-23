"""Name and face checks via ezina_id_verify (AWS Rekognition): new columns on identity_documents

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-23

* name_extract_method / name_extract_confidence: how the name on the ID was read ("mrz", "label", "layout", "llm") and
  how sure the package is (0-1). ID_FRONT rows.
* face_similarity (0-100) and face_selfie_quality_ok: from the face match. SELFIE rows only, so the existing check
  constraint ck_identity_documents_face_only_selfie is extended to cover them.
face_distance and face_detector (the old HTTP API's fields) stay, nullable, so existing rows are preserved; nothing
writes them any more.

0001 builds the baseline with create_all from the *current* models, so a database created from scratch already has
these columns and the extended constraint when it reaches this revision. Every step checks first and only adds what is
missing.
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_ONLY_CK = "ck_identity_documents_face_only_selfie"
_BASE = (
    "kind = 'SELFIE' OR (face_check_status IS NULL AND face_compared_id_document_id IS NULL AND face_verified IS NULL "
    "AND face_distance IS NULL AND face_threshold IS NULL AND face_confidence_band IS NULL AND "
    "face_liveness_passed IS NULL AND face_found_id IS NULL AND face_found_selfie IS NULL AND face_model IS NULL AND "
    "face_detector IS NULL AND face_processing_ms IS NULL AND face_warnings IS NULL AND face_error_message IS NULL AND "
    "face_checked_at IS NULL AND face_check_attempts = 0"
)
_OLD_ONLY = _BASE + ")"
_NEW_ONLY = _BASE + " AND face_similarity IS NULL AND face_selfie_quality_ok IS NULL)"


def _columns() -> dict[str, sa.Column]:
    return {
        "name_extract_method": sa.Column("name_extract_method", sa.Text()),
        "name_extract_confidence": sa.Column("name_extract_confidence", sa.Numeric(5, 4)),
        "face_similarity": sa.Column("face_similarity", sa.Numeric(7, 3)),
        "face_selfie_quality_ok": sa.Column("face_selfie_quality_ok", sa.Boolean()),
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
    constraints = {c["name"] for c in insp.get_check_constraints("identity_documents")}
    with op.batch_alter_table("identity_documents") as b:
        if _ONLY_CK in constraints:
            b.drop_constraint(_ONLY_CK, type_="check")
        for n in missing:
            b.add_column(cols[n])
        b.create_check_constraint(_ONLY_CK, _NEW_ONLY)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("identity_documents"):
        return
    existing = {c["name"] for c in insp.get_columns("identity_documents")}
    present = [n for n in _columns() if n in existing]
    if not present:
        return
    constraints = {c["name"] for c in insp.get_check_constraints("identity_documents")}
    with op.batch_alter_table("identity_documents") as b:
        if _ONLY_CK in constraints:
            b.drop_constraint(_ONLY_CK, type_="check")
        for n in present:
            b.drop_column(n)
        b.create_check_constraint(_ONLY_CK, _OLD_ONLY)
