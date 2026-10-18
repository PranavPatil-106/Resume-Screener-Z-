"""add_index_model_to_staged_resumes

Revision ID: e1a2b3c4d5e6
Revises: 76a5811e4632
Create Date: 2026-10-12 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '76a5811e4632'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add index_model column to staged_resumes."""
    op.add_column(
        'staged_resumes',
        sa.Column('index_model', sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('staged_resumes', 'index_model')
