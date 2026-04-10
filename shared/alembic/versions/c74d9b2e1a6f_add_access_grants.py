"""add access grants

Revision ID: c74d9b2e1a6f
Revises: b806a150f35d
Create Date: 2026-04-09 19:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c74d9b2e1a6f"
down_revision: Union[str, None] = "b806a150f35d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("granted_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("plan_id", sa.BigInteger(), nullable=True),
        sa.Column("template_code", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("entitlement_kind", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quota_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_ref", name="uq_access_grants_source"),
    )
    op.create_index(op.f("ix_access_grants_user_id"), "access_grants", ["user_id"], unique=False)
    op.create_index(op.f("ix_access_grants_status"), "access_grants", ["status"], unique=False)
    op.create_index(op.f("ix_access_grants_source_type"), "access_grants", ["source_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_access_grants_source_type"), table_name="access_grants")
    op.drop_index(op.f("ix_access_grants_status"), table_name="access_grants")
    op.drop_index(op.f("ix_access_grants_user_id"), table_name="access_grants")
    op.drop_table("access_grants")
