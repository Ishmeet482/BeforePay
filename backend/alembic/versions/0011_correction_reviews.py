"""Append-only human correction review history; not checkout approval."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0011_correction_reviews"
down_revision = "0010_clarification_replies"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clarification_correction_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column(
            "suggestion_id",
            sa.Uuid(),
            sa.ForeignKey("clarification_suggestions.id"),
            nullable=False,
        ),
        sa.Column(
            "reply_id",
            sa.Uuid(),
            sa.ForeignKey("clarification_replies.id"),
            nullable=False,
        ),
        sa.Column(
            "comparison_id",
            sa.Uuid(),
            sa.ForeignKey("booking_comparisons.id"),
            nullable=False,
        ),
        sa.Column(
            "agreement_id",
            sa.Uuid(),
            sa.ForeignKey("agreement_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "confirmation_id",
            sa.Uuid(),
            sa.ForeignKey("agreement_confirmations.id"),
            nullable=False,
        ),
        sa.Column(
            "original_proposal_id",
            sa.Uuid(),
            sa.ForeignKey("merchant_booking_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "proposal_id",
            sa.Uuid(),
            sa.ForeignKey("merchant_booking_versions.id"),
            nullable=False,
        ),
        sa.Column("context_fingerprint", sa.String(64), nullable=False),
        sa.Column("context", JSONB(), nullable=False),
        sa.Column("reviewer_label", sa.String(100), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("identity_provisional", sa.Boolean(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "suggestion_id", "comparison_id", name="uq_correction_review_context"
        ),
        sa.CheckConstraint(
            "identity_provisional = true", name="ck_correction_provisional"
        ),
    )
    for column in ("booking_id", "suggestion_id"):
        op.create_index(
            f"ix_clarification_correction_reviews_{column}",
            "clarification_correction_reviews",
            [column],
        )
    op.execute(
        "CREATE TRIGGER clarification_correction_reviews_immutable "
        "BEFORE UPDATE OR DELETE ON clarification_correction_reviews "
        "FOR EACH ROW EXECUTE FUNCTION contextkey_reject_review_mutation()"
    )


def downgrade():
    op.drop_table("clarification_correction_reviews")
