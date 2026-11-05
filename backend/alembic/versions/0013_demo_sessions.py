"""Isolated expiring demo sessions; preserve legacy bookings without an owner."""

import sqlalchemy as sa

from alembic import op

revision = "0013_demo_sessions"
down_revision = "0012_policy_consistency"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demo_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_demo_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_demo_expiry"),
    )
    op.add_column("bookings", sa.Column("owner_session_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_booking_demo_session",
        "bookings",
        "demo_sessions",
        ["owner_session_id"],
        ["id"],
    )
    op.create_index("ix_bookings_owner_session_id", "bookings", ["owner_session_id"])
    op.execute("""
        CREATE FUNCTION beforepay_preserve_booking_owner() RETURNS trigger AS $$
        BEGIN
            IF NEW.owner_session_id IS DISTINCT FROM OLD.owner_session_id THEN
                RAISE EXCEPTION 'Booking ownership is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER bookings_owner_immutable BEFORE UPDATE ON bookings
        FOR EACH ROW EXECUTE FUNCTION beforepay_preserve_booking_owner();
    """)


def downgrade():
    op.execute("DROP TRIGGER bookings_owner_immutable ON bookings")
    op.execute("DROP FUNCTION beforepay_preserve_booking_owner()")
    op.drop_index("ix_bookings_owner_session_id", "bookings")
    op.drop_constraint("fk_booking_demo_session", "bookings", type_="foreignkey")
    op.drop_column("bookings", "owner_session_id")
    op.drop_table("demo_sessions")
