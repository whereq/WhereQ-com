"""Make 5 km the default radius of the nearby search.

The nearby list opened on a 2 km radius, which is tight enough that a
category the centre happens not to contain reads as empty.  The radius rail
already offered 5 km; only the starting point moves.

The stored value of a row the user has actually chosen is left alone — this
changes the *default*, not the user's own choice.

Revision ID: 015_nearby_default_radius
Revises: 014_unplace_fallback_content
Create Date: 2026-11-07
"""
from alembic import op

revision = "015_nearby_default_radius"
down_revision = "014_unplace_fallback_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_settings ALTER COLUMN radius_km SET DEFAULT 5.0"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_settings ALTER COLUMN radius_km SET DEFAULT 2.0"
    )
