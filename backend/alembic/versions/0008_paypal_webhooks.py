"""Verified sandbox webhook deduplication, committed with reconciliation."""

import sqlalchemy as sa

from alembic import op

revision = "0008_paypal_webhooks"
down_revision = "0007_paypal_sandbox"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paypal_webhook_events",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("payment_attempts.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE TRIGGER paypal_webhook_events_immutable BEFORE UPDATE OR DELETE "
        "ON paypal_webhook_events FOR EACH ROW "
        "EXECUTE FUNCTION contextkey_reject_review_mutation()"
    )


def downgrade():
    op.drop_table("paypal_webhook_events")
