"""Confirmed product content, price and inventory edits with durable audit."""
from alembic import op
import sqlalchemy as sa

revision = '20261019_11'
down_revision = '20261017_10'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('product_edit_proposal',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('operation_id',sa.String(36),nullable=False,unique=True),
        sa.Column('shop_slug',sa.String(120),nullable=False,index=True),
        sa.Column('sku',sa.String(100),nullable=False),
        sa.Column('product_id',sa.Integer(),nullable=False),
        sa.Column('variant_id',sa.Integer(),nullable=True),
        sa.Column('target_kind',sa.String(20),nullable=False),
        sa.Column('status',sa.String(20),nullable=False,index=True),
        sa.Column('before_json',sa.Text(),nullable=False),
        sa.Column('after_json',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('decided_at',sa.DateTime(),nullable=True))
    op.create_table('product_edit_audit',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('proposal_id',sa.Integer(),nullable=False,unique=True),
        sa.Column('shop_slug',sa.String(120),nullable=False),
        sa.Column('sku',sa.String(100),nullable=False),
        sa.Column('before_json',sa.Text(),nullable=False),
        sa.Column('after_json',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    op.add_column('agent_run',sa.Column('product_edit_proposal_id',sa.Integer(),nullable=True))


def downgrade():
    op.drop_column('agent_run','product_edit_proposal_id')
    op.drop_table('product_edit_audit')
    op.drop_table('product_edit_proposal')
