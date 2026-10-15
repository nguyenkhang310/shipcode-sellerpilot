"""Persist conversation scope and proposal references without changing old runs."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_04"
down_revision = "20261015_03"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_run", sa.Column("conversation_id", sa.String(36), nullable=True))
    op.add_column("agent_run", sa.Column("shop_slug", sa.String(120), nullable=True))
    op.add_column("agent_run", sa.Column("proposal_id", sa.Integer(), nullable=True))
    op.create_index("ix_agent_run_conversation_id", "agent_run", ["conversation_id"])
    op.create_index("ix_agent_run_shop_slug", "agent_run", ["shop_slug"])


def downgrade():
    op.drop_index("ix_agent_run_shop_slug", "agent_run")
    op.drop_index("ix_agent_run_conversation_id", "agent_run")
    op.drop_column("agent_run", "proposal_id")
    op.drop_column("agent_run", "shop_slug")
    op.drop_column("agent_run", "conversation_id")
