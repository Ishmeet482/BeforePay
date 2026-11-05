"""Immutable cited extraction drafts; existing evidence remains untouched."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_immutable_drafts"
down_revision = "0002_bookings_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_source_ids", postgresql.JSONB(), nullable=False),
        sa.Column("source_fingerprints", postgresql.JSONB(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("booking_id", "version", name="uq_draft_booking_version"),
        sa.CheckConstraint("version >= 1"),
        sa.CheckConstraint("status = 'draft'"),
    )
    op.create_index("ix_draft_versions_booking_id", "draft_versions", ["booking_id"])
    op.execute("""
        CREATE FUNCTION contextkey_reject_draft_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'Draft versions are immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER draft_versions_immutable
        BEFORE UPDATE OR DELETE ON draft_versions
        FOR EACH ROW EXECUTE FUNCTION contextkey_reject_draft_mutation()
    """)


def downgrade() -> None:
    op.drop_table("draft_versions")
    op.execute("DROP FUNCTION contextkey_reject_draft_mutation()")
