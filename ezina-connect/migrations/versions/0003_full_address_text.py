"""farms: one full_address_text replaces village, district and address

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20

0001 builds the baseline with create_all from the *current* models, so a database created from scratch already has
the new shape when it reaches this revision: every step checks first. A database created before this change gets
full_address_text (filled from the old columns, if it has any rows), then loses village, district and address.
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_OLD = ("village", "district", "address")


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("farms"):
        return
    cols = {c["name"] for c in insp.get_columns("farms")}
    if "full_address_text" not in cols:
        with op.batch_alter_table("farms") as b:
            b.add_column(sa.Column("full_address_text", sa.Text(), nullable=True))
        # no records are expected; if there are some, keep what they had as one text
        if any(c in cols for c in _OLD):
            v, d, a = (c if c in cols else "''" for c in _OLD)  # village, district, address
            op.execute(sa.text(
                f"UPDATE farms SET full_address_text = "
                f"COALESCE(NULLIF({a}, ''), TRIM(COALESCE({v}, '') || ' ' || COALESCE({d}, '')))"
            ))
        op.execute(sa.text("UPDATE farms SET full_address_text = '' WHERE full_address_text IS NULL"))
        with op.batch_alter_table("farms") as b:
            b.alter_column("full_address_text", existing_type=sa.Text(), nullable=False)
    drop = [c for c in _OLD if c in cols]
    if drop:
        with op.batch_alter_table("farms") as b:
            for c in drop:
                b.drop_column(c)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("farms"):
        return
    cols = {c["name"] for c in insp.get_columns("farms")}
    with op.batch_alter_table("farms") as b:
        if "village" not in cols:
            b.add_column(sa.Column("village", sa.String(200), nullable=True))
        if "district" not in cols:
            b.add_column(sa.Column("district", sa.String(200), nullable=True))
        if "address" not in cols:
            b.add_column(sa.Column("address", sa.String(500), nullable=True))
    if "full_address_text" in cols:
        op.execute(sa.text("UPDATE farms SET address = substr(full_address_text, 1, 500)"))
        with op.batch_alter_table("farms") as b:
            b.drop_column("full_address_text")
