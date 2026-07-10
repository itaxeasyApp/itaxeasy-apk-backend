"""drop business trade_name — merge into the single (trade) name field

The "Set up Business" form no longer has a separate Trade Name input: the one
remaining name field is the trade name (the `name` column is kept and now holds
it). The old, always-empty `tradeName` column is therefore dropped.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("businesses", "tradeName")


def downgrade() -> None:
    op.add_column("businesses", sa.Column("tradeName", sa.String(), nullable=True))
