"""merge catalog generalization and knowledge base heads

Revision ID: 012e8b346d5b
Revises: b7e2f91a4d10, cbb711ecfc74
Create Date: 2026-10-27 20:08:09.940535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '012e8b346d5b'
down_revision: Union[str, None] = ('b7e2f91a4d10', 'cbb711ecfc74')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
