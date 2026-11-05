"""Append-only cancellation rules and separate human approvals."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_cancellation_rules"
down_revision = "0005_booking_comparison"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cancellation_rule_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column("target_kind", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("target_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("audit", postgresql.JSONB(), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "booking_id",
            "target_kind",
            "target_id",
            "version",
            name="uq_cancellation_rule_version",
        ),
    )
    op.create_index(
        "ix_cancellation_rule_versions_booking_id",
        "cancellation_rule_versions",
        ["booking_id"],
    )
    op.create_table(
        "cancellation_rule_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column(
            "rule_id",
            sa.Uuid(),
            sa.ForeignKey("cancellation_rule_versions.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("reviewed_fingerprint", sa.String(64), nullable=False),
        sa.Column("audit", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_cancellation_rule_approvals_booking_id",
        "cancellation_rule_approvals",
        ["booking_id"],
    )
    for table in ("cancellation_rule_versions", "cancellation_rule_approvals"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION contextkey_reject_review_mutation()"
        )


def downgrade():
    op.drop_table("cancellation_rule_approvals")
    op.drop_table("cancellation_rule_versions")
