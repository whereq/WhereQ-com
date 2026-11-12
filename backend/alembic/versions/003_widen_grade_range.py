"""Widen school.grade_range to 255 (YCDSB embeds program descriptions)

Revision ID: 003_grade_range
Revises: 002_schools
Create Date: 2026-05-31
"""
from alembic import op
import sqlalchemy as sa

revision = "003_grade_range"
down_revision = "002_schools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("school", "grade_range",
                    type_=sa.String(255), existing_type=sa.String(64), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("school", "grade_range",
                    type_=sa.String(64), existing_type=sa.String(255), existing_nullable=True)
