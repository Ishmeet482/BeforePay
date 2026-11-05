"""Durable public resource reservations and AI circuit state."""

import sqlalchemy as sa

from alembic import op

revision = "0014_public_admission"
down_revision = "0013_demo_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demo_admission_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("circuit_reason", sa.String(40)),
        sa.CheckConstraint("id = 1"),
    )
    op.execute("INSERT INTO demo_admission_control(id) VALUES (1)")
    op.create_table(
        "demo_admissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid()),
        sa.Column("booking_id", sa.Uuid()),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("units", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("units >= 0"),
        sa.CheckConstraint("input_hash ~ '^[0-9a-f]{64}$'"),
        sa.CheckConstraint(
            "kind IN ('session','booking','source','write','upload','ai')"
        ),
    )
    for column in ("session_id", "kind", "created_at"):
        op.create_index(f"ix_demo_admissions_{column}", "demo_admissions", [column])
    op.execute("""
        CREATE FUNCTION beforepay_preserve_admission() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Admission charges cannot be deleted';
          END IF;
          IF (to_jsonb(NEW) - 'finished_at') IS DISTINCT FROM
             (to_jsonb(OLD) - 'finished_at') OR OLD.finished_at IS NOT NULL
             OR NEW.finished_at IS NULL THEN
            RAISE EXCEPTION 'Admission charges are immutable';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER demo_admissions_immutable
        BEFORE UPDATE OR DELETE ON demo_admissions
        FOR EACH ROW EXECUTE FUNCTION beforepay_preserve_admission();
    """)


def downgrade():
    op.drop_table("demo_admissions")
    op.execute("DROP FUNCTION beforepay_preserve_admission()")
    op.drop_table("demo_admission_control")
