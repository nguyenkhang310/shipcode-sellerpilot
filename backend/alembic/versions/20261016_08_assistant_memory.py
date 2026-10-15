"""Scoped seller preferences and seller-supplied product economics."""
from alembic import op
import sqlalchemy as sa

revision = '20261016_08'
down_revision = '20261015_07'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('assistant_memory',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('shop_slug', sa.String(120), nullable=False),
        sa.Column('scope', sa.String(160), nullable=False),
        sa.Column('key', sa.String(60), nullable=False),
        sa.Column('value_json', sa.Text(), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('shop_slug', 'scope', 'key', name='uq_assistant_memory_scope'),
    )
    op.create_index('ix_assistant_memory_shop_slug', 'assistant_memory', ['shop_slug'])


def downgrade():
    op.drop_index('ix_assistant_memory_shop_slug', 'assistant_memory')
    op.drop_table('assistant_memory')
