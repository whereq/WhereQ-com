"""Add Keycloak identity to users; passwords now optional (managed by Keycloak)

Revision ID: 004_keycloak
Revises: 003_grade_range
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = "004_keycloak"
down_revision = "003_grade_range"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("keycloak_id", sa.String(64), nullable=True))
    op.create_index("ix_users_keycloak_id", "users", ["keycloak_id"], unique=True)
    # Passwords are managed by Keycloak — local hash becomes optional.
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=False)
    op.drop_index("ix_users_keycloak_id", table_name="users")
    op.drop_column("users", "keycloak_id")
