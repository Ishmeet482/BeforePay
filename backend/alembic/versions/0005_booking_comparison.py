"""Immutable merchant proposals and comparisons, separate from customer baseline."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_booking_comparison"
down_revision = "0004_customer_review"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "merchant_booking_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("audit", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "booking_id", "version", name="uq_merchant_booking_version"
        ),
        sa.CheckConstraint("version >= 1"),
    )
    op.create_index(
        "ix_merchant_booking_versions_booking_id",
        "merchant_booking_versions",
        ["booking_id"],
    )
    op.create_table(
        "booking_comparisons",
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
        sa.Column("agreement_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "confirmation_id",
            sa.Uuid(),
            sa.ForeignKey("agreement_confirmations.id"),
            nullable=False,
        ),
        sa.Column(
            "proposal_id",
            sa.Uuid(),
            sa.ForeignKey("merchant_booking_versions.id"),
            nullable=False,
        ),
        sa.Column("proposal_fingerprint", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_booking_comparisons_booking_id", "booking_comparisons", ["booking_id"]
    )
    for table in ("merchant_booking_versions", "booking_comparisons"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION contextkey_reject_review_mutation()"
        )


def downgrade():
    op.drop_table("booking_comparisons")
    op.drop_table("merchant_booking_versions")
