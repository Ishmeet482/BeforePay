"""Append-only deposit/cancellation consistency checks."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0012_policy_consistency"
down_revision = "0011_correction_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "policy_consistency_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column(
            "proposal_id",
            sa.Uuid(),
            sa.ForeignKey("merchant_booking_versions.id"),
            nullable=False,
        ),
        sa.Column("proposal_fingerprint", sa.String(64), nullable=False),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("output", JSONB(), nullable=False),
        sa.Column("clauses", JSONB(), nullable=False),
        sa.Column("model_metadata", JSONB(), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    for column in ("booking_id", "proposal_id"):
        op.create_index(
            f"ix_policy_consistency_checks_{column}",
            "policy_consistency_checks",
            [column],
        )
    op.execute(
        "CREATE TRIGGER policy_consistency_checks_immutable "
        "BEFORE UPDATE OR DELETE ON policy_consistency_checks "
        "FOR EACH ROW EXECUTE FUNCTION contextkey_reject_review_mutation()"
    )


def downgrade():
    op.drop_table("policy_consistency_checks")
