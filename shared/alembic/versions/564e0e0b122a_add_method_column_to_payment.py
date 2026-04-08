"""Add method column to payment

Revision ID: 564e0e0b122a
Revises: a5d960800586
Create Date: 2025-06-09 21:02:16.720555

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '564e0e0b122a'
down_revision: Union[str, None] = 'a5d960800586'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payment', sa.Column('method', sa.String(), nullable=True))



def downgrade() -> None:
    op.drop_column('payment', 'method')
