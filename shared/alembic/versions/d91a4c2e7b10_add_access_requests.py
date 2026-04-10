"""add access requests

Revision ID: d91a4c2e7b10
Revises: c74d9b2e1a6f
Create Date: 2026-04-09 20:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d91a4c2e7b10"
down_revision: Union[str, None] = "c74d9b2e1a6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_template_code", sa.Text(), nullable=True),
        sa.Column("access_grant_id", sa.BigInteger(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_actor", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["access_grant_id"], ["access_grants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_access_requests_user_id"), "access_requests", ["user_id"], unique=False)
    op.create_index(op.f("ix_access_requests_status"), "access_requests", ["status"], unique=False)
    op.create_index(
        op.f("ix_access_requests_requested_template_code"),
        "access_requests",
        ["requested_template_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_access_requests_requested_template_code"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_status"), table_name="access_requests")
    op.drop_index(op.f("ix_access_requests_user_id"), table_name="access_requests")
    op.drop_table("access_requests")
