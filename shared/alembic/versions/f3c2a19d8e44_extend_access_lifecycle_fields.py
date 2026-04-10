"""extend access lifecycle fields

Revision ID: f3c2a19d8e44
Revises: e2a5f9c1b4d7
Create Date: 2026-04-09 23:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3c2a19d8e44"
down_revision: Union[str, None] = "e2a5f9c1b4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "access_requests",
        sa.Column("request_kind", sa.Text(), nullable=False, server_default="new_access"),
    )
    op.add_column(
        "access_requests",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("access_requests", "request_kind", server_default=None)

    op.add_column(
        "access_registry_entries",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        "access_registry_entries",
        sa.Column("allow_auto_renew", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "access_registry_entries",
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "access_registry_entries",
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("access_registry_entries", "priority", server_default=None)
    op.alter_column("access_registry_entries", "allow_auto_renew", server_default=None)

    op.add_column(
        "access_grants",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("access_grants", "revoked_at")

    op.drop_column("access_registry_entries", "valid_until")
    op.drop_column("access_registry_entries", "valid_from")
    op.drop_column("access_registry_entries", "allow_auto_renew")
    op.drop_column("access_registry_entries", "priority")

    op.drop_column("access_requests", "expires_at")
    op.drop_column("access_requests", "request_kind")
