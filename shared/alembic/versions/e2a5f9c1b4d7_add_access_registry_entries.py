"""add access registry entries

Revision ID: e2a5f9c1b4d7
Revises: d91a4c2e7b10
Create Date: 2026-04-09 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2a5f9c1b4d7"
down_revision: Union[str, None] = "d91a4c2e7b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_registry_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identity_type", sa.Text(), nullable=False),
        sa.Column("identity_value", sa.Text(), nullable=False),
        sa.Column("template_code", sa.Text(), nullable=False),
        sa.Column("auto_approve", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_actor", sa.Text(), nullable=True),
        sa.Column("updated_by_actor", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_type", "identity_value", name="uq_access_registry_identity"),
    )
    op.create_index(
        op.f("ix_access_registry_entries_identity_type"),
        "access_registry_entries",
        ["identity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_access_registry_entries_template_code"),
        "access_registry_entries",
        ["template_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_access_registry_entries_template_code"), table_name="access_registry_entries")
    op.drop_index(op.f("ix_access_registry_entries_identity_type"), table_name="access_registry_entries")
    op.drop_table("access_registry_entries")
