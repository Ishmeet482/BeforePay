"""Dedicated demo marker and authored template catalogue only."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0015_demo_templates"
down_revision = "0014_public_admission"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demo_templates",
        sa.Column("key", sa.String(40), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
    )
    op.create_table(
        "demo_deployment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("database_name", sa.String(100), nullable=False),
        sa.Column("template_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("id = 1"),
    )
    for table in ("demo_templates", "demo_deployment"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION contextkey_reject_review_mutation()"
        )


def downgrade():
    op.drop_table("demo_deployment")
    op.drop_table("demo_templates")
