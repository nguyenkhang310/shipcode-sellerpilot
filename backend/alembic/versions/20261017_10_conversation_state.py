"""Persistent pins and deletion tombstones, scoped to a seller shop."""
from alembic import op
import sqlalchemy as sa

revision = '20261017_10'
down_revision = '20261016_09'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('conversation_state',
        sa.Column('shop_slug', sa.String(120), primary_key=True),
        sa.Column('conversation_id', sa.String(36), primary_key=True),
        sa.Column('pinned_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_table('conversation_state')
