"""form16 per employer (allow multiple Form 16s per assessment year)

Adds `employerTan` to `form16_imports` and moves the uniqueness key from
(userId, assessmentYear) to (userId, assessmentYear, employerTan), so a taxpayer
with several employers in a year can store one Form 16 per employer.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-08 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("form16_imports", sa.Column("employerTan", sa.String(), nullable=True))
    # Backfill the TAN from the stored normalized data.
    op.execute(
        """UPDATE form16_imports
           SET "employerTan" = data->>'employerTan'
           WHERE "employerTan" IS NULL"""
    )
    op.drop_constraint("uq_form16_user_ay", "form16_imports", type_="unique")
    op.create_unique_constraint(
        "uq_form16_user_ay_tan",
        "form16_imports",
        ["userId", "assessmentYear", "employerTan"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_form16_user_ay_tan", "form16_imports", type_="unique")
    op.create_unique_constraint(
        "uq_form16_user_ay", "form16_imports", ["userId", "assessmentYear"]
    )
    op.drop_column("form16_imports", "employerTan")
