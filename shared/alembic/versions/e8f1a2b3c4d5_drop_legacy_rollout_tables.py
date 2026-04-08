"""drop legacy rollout tables

Revision ID: e8f1a2b3c4d5
Revises: d12e5f7a9c31
Create Date: 2026-03-31 17:15:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e8f1a2b3c4d5"
down_revision: Union[str, None] = "d12e5f7a9c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_TABLES = (
    "payment",
    "promocodeusage",
    "referral",
    "promocode",
    "user",
)


def upgrade() -> None:
    for table_name in LEGACY_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')


def downgrade() -> None:
    raise NotImplementedError(
        "Legacy table drop is destructive. Restore from backup instead of alembic downgrade."
    )
