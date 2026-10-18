"""create_user_invitations_table

Revision ID: ca0900bc2b60
Revises: 97ab211c9031
Create Date: 2026-10-12 00:09:14.584180

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca0900bc2b60'
down_revision: Union[str, Sequence[str], None] = '97ab211c9031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_invitations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_invitations_id'), 'user_invitations', ['id'], unique=False)
    op.create_index(op.f('ix_user_invitations_user_id'), 'user_invitations', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_invitations_token_hash'), 'user_invitations', ['token_hash'], unique=True)
    op.create_index(op.f('ix_user_invitations_expires_at'), 'user_invitations', ['expires_at'], unique=False)
    op.create_index(op.f('ix_user_invitations_created_by_id'), 'user_invitations', ['created_by_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_invitations_created_by_id'), table_name='user_invitations')
    op.drop_index(op.f('ix_user_invitations_expires_at'), table_name='user_invitations')
    op.drop_index(op.f('ix_user_invitations_token_hash'), table_name='user_invitations')
    op.drop_index(op.f('ix_user_invitations_user_id'), table_name='user_invitations')
    op.drop_index(op.f('ix_user_invitations_id'), table_name='user_invitations')
    op.drop_table('user_invitations')
