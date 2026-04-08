"""add whitelist foundation

Revision ID: 1f2e3d4c5b6a
Revises: e8f1a2b3c4d5
Create Date: 2026-04-02 16:40:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1f2e3d4c5b6a"
down_revision: Union[str, None] = "e8f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vpn_clients",
        sa.Column("scope", sa.Text(), nullable=False, server_default=sa.text("'standard'")),
    )
    op.add_column(
        "vpn_access_points",
        sa.Column("scope", sa.Text(), nullable=False, server_default=sa.text("'standard'")),
    )

    op.drop_index("uq_vpn_clients_active_user", table_name="vpn_clients")
    op.create_index(
        "uq_vpn_clients_active_user_scope",
        "vpn_clients",
        ["user_id", "scope"],
        unique=True,
        postgresql_where=sa.text("deactivated_at IS NULL"),
    )

    op.create_table(
        "traffic_grants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("vpn_client_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("granted_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vpn_client_id"], ["vpn_clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_traffic_grants_vpn_client_id",
        "traffic_grants",
        ["vpn_client_id"],
        unique=False,
    )

    op.create_table(
        "traffic_state",
        sa.Column("vpn_client_id", sa.BigInteger(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("allocated_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("used_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("remaining_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("last_provider_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vpn_client_id"], ["vpn_clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("vpn_client_id"),
    )

    op.alter_column("vpn_clients", "scope", server_default=None)
    op.alter_column("vpn_access_points", "scope", server_default=None)


def downgrade() -> None:
    op.drop_table("traffic_state")
    op.drop_index("ix_traffic_grants_vpn_client_id", table_name="traffic_grants")
    op.drop_table("traffic_grants")

    op.drop_index("uq_vpn_clients_active_user_scope", table_name="vpn_clients")
    op.create_index(
        "uq_vpn_clients_active_user",
        "vpn_clients",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("deactivated_at IS NULL"),
    )

    op.drop_column("vpn_access_points", "scope")
    op.drop_column("vpn_clients", "scope")
