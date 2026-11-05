"""Add bookings and original evidence with numbered PDF pages."""

import sqlalchemy as sa

from alembic import op

revision = "0002_bookings_evidence"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "evidence_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False
        ),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("medium", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255)),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("source_type IN ('quotation', 'message')"),
        sa.CheckConstraint("medium IN ('pasted_text', 'pdf')"),
        sa.CheckConstraint("char_length(original_text) BETWEEN 1 AND 100000"),
        sa.CheckConstraint(
            "(medium = 'pdf' AND filename IS NOT NULL) OR "
            "(medium = 'pasted_text' AND filename IS NULL)"
        ),
    )
    op.create_index(
        "ix_evidence_sources_booking_id", "evidence_sources", ["booking_id"]
    )
    op.create_table(
        "evidence_pages",
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("evidence_sources.id"),
            primary_key=True,
        ),
        sa.Column("page_number", sa.Integer(), primary_key=True),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.CheckConstraint("page_number BETWEEN 1 AND 100"),
    )


def downgrade() -> None:
    op.drop_table("evidence_pages")
    op.drop_index("ix_evidence_sources_booking_id", table_name="evidence_sources")
    op.drop_table("evidence_sources")
    op.drop_table("bookings")
