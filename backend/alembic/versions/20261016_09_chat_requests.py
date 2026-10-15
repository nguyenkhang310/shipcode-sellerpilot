"""Durable chat idempotency and cancellation outcomes."""
from alembic import op
import sqlalchemy as sa

revision = '20261016_09'
down_revision = '20261016_08'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('chat_request',
        sa.Column('shop_slug', sa.String(120), primary_key=True),
        sa.Column('request_id', sa.String(36), primary_key=True),
        sa.Column('conversation_id', sa.String(36), nullable=True),
        sa.Column('fingerprint', sa.String(64), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('response_json', sa.Text(), nullable=True),
        sa.Column('error_status', sa.Integer(), nullable=True),
        sa.Column('error_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False))
    op.create_index('ix_chat_request_status', 'chat_request', ['status'])


def downgrade():
    op.drop_index('ix_chat_request_status', 'chat_request')
    op.drop_table('chat_request')
