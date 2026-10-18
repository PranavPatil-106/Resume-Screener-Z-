"""add_is_archived_and_archived_at_to_job_descriptions

Revision ID: c4b3a2e1d0f9
Revises: e1a2b3c4d5e6
Create Date: 2026-10-14 13:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4b3a2e1d0f9'
down_revision: Union[str, Sequence[str], None] = 'e1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add is_archived and archived_at columns to job_descriptions."""
    with op.batch_alter_table('job_descriptions') as batch_op:
        batch_op.add_column(
            sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('0'))
        )
        batch_op.add_column(
            sa.Column('archived_at', sa.DateTime(), nullable=True)
        )
        batch_op.create_index('ix_job_descriptions_is_archived', ['is_archived'])


def downgrade() -> None:
    """Downgrade schema to remove is_archived and archived_at columns from job_descriptions."""
    with op.batch_alter_table('job_descriptions') as batch_op:
        batch_op.drop_index('ix_job_descriptions_is_archived')
        batch_op.drop_column('archived_at')
        batch_op.drop_column('is_archived')
