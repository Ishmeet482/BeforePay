"""Durable sandbox checkout approvals, attempts, events and receipts."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_paypal_sandbox"
down_revision = "0006_cancellation_rules"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "checkout_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("audit", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_checkout_approvals_booking_id", "checkout_approvals", ["booking_id"]
    )
    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column(
            "approval_id",
            sa.Uuid(),
            sa.ForeignKey("checkout_approvals.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("amount", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("create_key", sa.String(36), unique=True, nullable=False),
        sa.Column("capture_key", sa.String(36), unique=True, nullable=False),
        sa.Column("order_id", sa.String(64), unique=True),
        sa.Column("capture_id", sa.String(64), unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("capture_requested_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_payment_attempts_booking_id", "payment_attempts", ["booking_id"]
    )
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("payment_attempts.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("code", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_payment_events_attempt_id", "payment_events", ["attempt_id"])
    op.create_table(
        "sandbox_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id",
            sa.Uuid(),
            sa.ForeignKey("bookings.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("payment_attempts.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "approval_id",
            sa.Uuid(),
            sa.ForeignKey("checkout_approvals.id"),
            nullable=False,
        ),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("amount", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("order_id", sa.String(64), unique=True, nullable=False),
        sa.Column("capture_id", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    for table in ("checkout_approvals", "payment_events", "sandbox_receipts"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION contextkey_reject_review_mutation()"
        )
    op.execute("""CREATE FUNCTION contextkey_protect_payment_attempt() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Payment attempts cannot be deleted';
      END IF;
      IF (OLD.id, OLD.booking_id, OLD.approval_id, OLD.amount, OLD.currency,
          OLD.create_key, OLD.capture_key, OLD.created_at) IS DISTINCT FROM
         (NEW.id, NEW.booking_id, NEW.approval_id, NEW.amount, NEW.currency,
          NEW.create_key, NEW.capture_key, NEW.created_at) THEN
        RAISE EXCEPTION 'Payment attempt bindings are immutable';
      END IF;
      IF OLD.order_id IS NOT NULL AND OLD.order_id IS DISTINCT FROM NEW.order_id THEN
        RAISE EXCEPTION 'PayPal order binding is immutable';
      END IF;
      IF OLD.capture_id IS NOT NULL
         AND OLD.capture_id IS DISTINCT FROM NEW.capture_id THEN
        RAISE EXCEPTION 'PayPal capture binding is immutable';
      END IF;
      IF OLD.capture_requested_at IS NOT NULL
         AND OLD.capture_requested_at IS DISTINCT FROM NEW.capture_requested_at THEN
        RAISE EXCEPTION 'Capture intent timestamp is immutable';
      END IF;
      RETURN NEW;
    END; $$""")
    op.execute(
        "CREATE TRIGGER payment_attempt_bindings "
        "BEFORE UPDATE OR DELETE ON payment_attempts "
        "FOR EACH ROW EXECUTE FUNCTION contextkey_protect_payment_attempt()"
    )


def downgrade():
    op.drop_table("sandbox_receipts")
    op.drop_table("payment_events")
    op.drop_table("payment_attempts")
    op.drop_table("checkout_approvals")
    op.execute("DROP FUNCTION contextkey_protect_payment_attempt()")
