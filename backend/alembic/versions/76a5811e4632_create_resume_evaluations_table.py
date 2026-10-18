"""create_resume_evaluations_table

Revision ID: 76a5811e4632
Revises: ca0900bc2b60
Create Date: 2026-10-12 11:54:33.100089

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '76a5811e4632'
down_revision: Union[str, Sequence[str], None] = 'ca0900bc2b60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'resume_evaluations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('screening_session_id', sa.String(length=36), nullable=False),
        sa.Column('resume_id', sa.String(length=36), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('job_description_id', sa.String(length=36), nullable=False),
        sa.Column('job_title', sa.String(length=255), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=True),
        sa.Column('evaluated_at', sa.DateTime(), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=True),
        sa.Column('max_overall_score', sa.Float(), nullable=False, server_default='100.0'),
        sa.Column('rubric', sa.JSON(), nullable=False),
        sa.Column('missing_criteria', sa.JSON(), nullable=False),
        sa.Column('unverified_criteria', sa.JSON(), nullable=False),
        sa.Column('evaluation_summary', sa.Text(), nullable=False),
        sa.Column('disclaimer', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['screening_session_id'], ['screening_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('screening_session_id', 'resume_id', name='uq_resume_evaluations_session_resume'),
    )
    op.create_index(op.f('ix_resume_evaluations_id'), 'resume_evaluations', ['id'], unique=False)
    op.create_index(op.f('ix_resume_evaluations_screening_session_id'), 'resume_evaluations', ['screening_session_id'], unique=False)
    op.create_index(op.f('ix_resume_evaluations_resume_id'), 'resume_evaluations', ['resume_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_resume_evaluations_resume_id'), table_name='resume_evaluations')
    op.drop_index(op.f('ix_resume_evaluations_screening_session_id'), table_name='resume_evaluations')
    op.drop_index(op.f('ix_resume_evaluations_id'), table_name='resume_evaluations')
    op.drop_table('resume_evaluations')
