"""Immutable provisional merchant replies; no changes to prior records."""

import sqlalchemy as sa

from alembic import op

revision = "0010_clarification_replies"
down_revision = "0009_clarification_suggestions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clarification_replies",
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
        sa.Column("suggestion_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "comparison_id",
            sa.Uuid(),
            sa.ForeignKey("booking_comparisons.id"),
            nullable=False,
        ),
        sa.Column("comparison_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "proposal_id",
            sa.Uuid(),
            sa.ForeignKey("merchant_booking_versions.id"),
            nullable=False,
        ),
        sa.Column("proposal_fingerprint", sa.String(64), nullable=False),
        sa.Column("merchant_label", sa.String(100), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("identity_provisional", sa.Boolean(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("identity_provisional = true", name="ck_reply_provisional"),
        sa.CheckConstraint(
            "char_length(trim(merchant_label)) > 0", name="ck_reply_label"
        ),
        sa.CheckConstraint("char_length(trim(response)) > 0", name="ck_reply_response"),
    )
    for column in ("booking_id", "suggestion_id"):
        op.create_index(
            f"ix_clarification_replies_{column}", "clarification_replies", [column]
        )
    op.execute(
        "CREATE TRIGGER clarification_replies_immutable BEFORE UPDATE OR DELETE "
        "ON clarification_replies FOR EACH ROW "
        "EXECUTE FUNCTION contextkey_reject_review_mutation()"
    )


def downgrade():
    op.drop_table("clarification_replies")
