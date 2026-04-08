"""harden plan and control plane columns

Revision ID: 6a7b8c9d0e1f
Revises: 1f2e3d4c5b6a
Create Date: 2026-04-02 19:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6a7b8c9d0e1f"
down_revision: Union[str, None] = "1f2e3d4c5b6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("legacy_payload", sa.Text(), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column("scope", sa.Text(), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column("entitlement_kind", sa.Text(), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column("quota_bytes", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "vpn_control_planes",
        sa.Column("scope", sa.Text(), nullable=True),
    )
    op.add_column(
        "vpn_control_planes",
        sa.Column("server_name", sa.Text(), nullable=True),
    )

    op.execute(
        """
        UPDATE plans
        SET legacy_payload = COALESCE(metadata->>'legacy_payload', code),
            scope = COALESCE(metadata->>'scope', 'standard'),
            entitlement_kind = COALESCE(metadata->>'entitlement_kind', 'time'),
            quota_bytes = CASE
                WHEN NULLIF(metadata->>'quota_bytes', '') IS NOT NULL
                    THEN (metadata->>'quota_bytes')::bigint
                ELSE NULL
            END
        """
    )
    op.execute(
        """
        UPDATE vpn_control_planes
        SET scope = COALESCE(metadata->>'scope', 'standard'),
            server_name = COALESCE(metadata->>'server_name', code)
        """
    )

    op.alter_column("plans", "legacy_payload", nullable=False)
    op.alter_column("plans", "scope", nullable=False)
    op.alter_column("plans", "entitlement_kind", nullable=False)
    op.alter_column("vpn_control_planes", "scope", nullable=False)
    op.alter_column("vpn_control_planes", "server_name", nullable=False)


def downgrade() -> None:
    op.drop_column("vpn_control_planes", "server_name")
    op.drop_column("vpn_control_planes", "scope")
    op.drop_column("plans", "quota_bytes")
    op.drop_column("plans", "entitlement_kind")
    op.drop_column("plans", "scope")
    op.drop_column("plans", "legacy_payload")
