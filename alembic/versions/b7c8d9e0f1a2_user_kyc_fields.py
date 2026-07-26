"""user KYC fields — add panNumber, aadhaarNumber, fatherName, dob, address

Personal profile: OCR-scanned PAN/Aadhaar details are stored on the user
profile. All five columns are optional (nullable) so existing rows stay valid.

Revision ID: b7c8d9e0f1a2
Revises: a7b8c9d0e1f2
Create Date: 2026-07-26 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("panNumber", sa.String(), nullable=True))
    op.add_column("users", sa.Column("aadhaarNumber", sa.String(), nullable=True))
    op.add_column("users", sa.Column("fatherName", sa.String(), nullable=True))
    op.add_column("users", sa.Column("dob", sa.String(), nullable=True))
    op.add_column("users", sa.Column("address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "address")
    op.drop_column("users", "dob")
    op.drop_column("users", "fatherName")
    op.drop_column("users", "aadhaarNumber")
    op.drop_column("users", "panNumber")
