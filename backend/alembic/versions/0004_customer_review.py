"""Immutable customer agreement versions and separate confirmation audit records."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_customer_review"
down_revision = "0003_immutable_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agreement_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column(
            "draft_id", sa.Uuid(), sa.ForeignKey("draft_versions.id"), nullable=False
        ),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("agreement_versions.id")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_fingerprints", postgresql.JSONB(), nullable=False),
        sa.Column("reviewed_source_ids", postgresql.JSONB(), nullable=False),
        sa.Column("audit", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "booking_id", "version", name="uq_agreement_booking_version"
        ),
        sa.CheckConstraint("version >= 1"),
    )
    op.create_index(
        "ix_agreement_versions_booking_id", "agreement_versions", ["booking_id"]
    )
    op.create_table(
        "agreement_confirmations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column(
            "agreement_id",
            sa.Uuid(),
            sa.ForeignKey("agreement_versions.id"),
            nullable=False,
        ),
        sa.Column("reviewed_fingerprint", sa.String(64), nullable=False),
        sa.Column("customer_label", sa.String(100), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("agreement_id", name="uq_confirmation_agreement"),
        sa.CheckConstraint("acknowledged = true"),
    )
    op.create_index(
        "ix_agreement_confirmations_booking_id",
        "agreement_confirmations",
        ["booking_id"],
    )
    op.execute(
        """CREATE FUNCTION contextkey_reject_review_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Agreement review records are immutable';
        END; $$"""
    )
    for table in ("agreement_versions", "agreement_confirmations"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION contextkey_reject_review_mutation()"
        )


def downgrade():
    op.drop_table("agreement_confirmations")
    op.drop_table("agreement_versions")
    op.execute("DROP FUNCTION contextkey_reject_review_mutation()")
