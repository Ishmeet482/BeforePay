"""Append-only advisory suggestions bound to exact saved comparison inputs."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_clarification_suggestions"
down_revision = "0008_paypal_webhooks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clarification_suggestions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column(
            "comparison_id",
            sa.Uuid(),
            sa.ForeignKey("booking_comparisons.id"),
            nullable=False,
        ),
        sa.Column("comparison_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "agreement_id",
            sa.Uuid(),
            sa.ForeignKey("agreement_versions.id"),
            nullable=False,
        ),
        sa.Column("agreement_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "proposal_id",
            sa.Uuid(),
            sa.ForeignKey("merchant_booking_versions.id"),
            nullable=False,
        ),
        sa.Column("proposal_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "confirmation_id",
            sa.Uuid(),
            sa.ForeignKey("agreement_confirmations.id"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=False),
        sa.Column("supporting_terms", postgresql.JSONB(), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    for column in ("booking_id", "comparison_id"):
        op.create_index(
            f"ix_clarification_suggestions_{column}",
            "clarification_suggestions",
            [column],
        )
    op.execute(
        "CREATE TRIGGER clarification_suggestions_immutable BEFORE UPDATE OR DELETE "
        "ON clarification_suggestions FOR EACH ROW "
        "EXECUTE FUNCTION contextkey_reject_review_mutation()"
    )


def downgrade():
    op.drop_table("clarification_suggestions")
