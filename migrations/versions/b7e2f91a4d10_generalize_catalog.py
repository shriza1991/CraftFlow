"""Allow catalog items without a physical material.

Revision ID: b7e2f91a4d10
Revises: 6a8433ba6cdb
"""

from alembic import op
import sqlalchemy as sa

revision = "b7e2f91a4d10"
down_revision = "6a8433ba6cdb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("products", "material", existing_type=sa.String(100), nullable=True)


def downgrade() -> None:
    # This fails if null materials exist; backfill explicitly before downgrading.
    op.alter_column("products", "material", existing_type=sa.String(100), nullable=False)
