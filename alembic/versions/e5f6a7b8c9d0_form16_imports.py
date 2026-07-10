"""form16_imports (Form 16 extraction storage)

Adds the `form16_imports` table: one row per (user, assessment year) holding the
normalized Form 16 fields extracted by the OCR service, plus the full raw OCR
response for later re-mapping. The original PDF is not stored.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-07 13:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "form16_imports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("userId", sa.Integer(), nullable=False),
        sa.Column("assessmentYear", sa.String(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rawOcr", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["userId"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("userId", "assessmentYear", name="uq_form16_user_ay"),
    )
    op.create_index(
        op.f("ix_form16_imports_userId"),
        "form16_imports",
        ["userId"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_form16_imports_userId"), table_name="form16_imports")
    op.drop_table("form16_imports")
