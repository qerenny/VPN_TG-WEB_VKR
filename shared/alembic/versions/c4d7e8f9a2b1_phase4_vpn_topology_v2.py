"""Phase 4 vpn topology v2 tables

Revision ID: c4d7e8f9a2b1
Revises: 9b3a4e7f6c11
Create Date: 2026-03-15 00:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d7e8f9a2b1"
down_revision: Union[str, None] = "9b3a4e7f6c11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vpn_control_planes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("api_base_url", sa.Text(), nullable=False),
        sa.Column("subscription_base_url", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "accepts_new_deployments",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "vpn_locations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "vpn_access_points",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("control_plane_id", sa.BigInteger(), nullable=False),
        sa.Column("location_id", sa.BigInteger(), nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("capacity_limit", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["control_plane_id"],
            ["vpn_control_planes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["vpn_locations.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "vpn_client_deployments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("vpn_client_id", sa.BigInteger(), nullable=False),
        sa.Column("access_point_id", sa.BigInteger(), nullable=False),
        sa.Column("external_client_id", sa.Text(), nullable=True),
        sa.Column("external_remark", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'failed')",
            name="ck_vpn_client_deployments_status",
        ),
        sa.ForeignKeyConstraint(
            ["vpn_client_id"],
            ["vpn_clients.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["access_point_id"],
            ["vpn_access_points.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_vpn_client_deployments_active_pair",
        "vpn_client_deployments",
        ["vpn_client_id", "access_point_id"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_vpn_client_deployments_active_pair",
        table_name="vpn_client_deployments",
    )
    op.drop_table("vpn_client_deployments")
    op.drop_table("vpn_access_points")
    op.drop_table("vpn_locations")
    op.drop_table("vpn_control_planes")
