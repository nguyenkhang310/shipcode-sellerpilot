"""Revocable seller sessions and durable login throttling."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_12'
down_revision = '20261019_11'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('seller_session',
        sa.Column('token_hash',sa.String(64),primary_key=True),
        sa.Column('user_id',sa.Integer(),nullable=False),
        sa.Column('shop_slug',sa.String(120),nullable=False),
        sa.Column('credential_tag',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('expires_at',sa.DateTime(),nullable=False),
        sa.Column('revoked_at',sa.DateTime(),nullable=True))
    op.create_index('ix_seller_session_shop_slug','seller_session',['shop_slug'])
    op.create_index('ix_seller_session_expires_at','seller_session',['expires_at'])
    op.create_table('seller_login_attempt',
        sa.Column('key',sa.String(64),primary_key=True),
        sa.Column('started_at',sa.DateTime(),nullable=False),
        sa.Column('count',sa.Integer(),nullable=False))


def downgrade():
    op.drop_table('seller_login_attempt')
    op.drop_table('seller_session')
