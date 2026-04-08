"""Change type of payment_id column to payment

Revision ID: fd997e5f0fa2
Revises: 564e0e0b122a
Create Date: 2025-06-09 21:14:01.020093

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'fd997e5f0fa2'
down_revision: Union[str, None] = '564e0e0b122a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.alter_column("payment", "payment_id", type_=sa.String(), existing_type=sa.UUID())

def downgrade():
    op.alter_column("payment", "payment_id", type_=sa.UUID(), existing_type=sa.String())
