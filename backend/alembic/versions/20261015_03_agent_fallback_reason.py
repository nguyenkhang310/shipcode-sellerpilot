"""Record why an agent run used the deterministic fallback.

Revision ID: 20261015_03
Revises: 20261015_02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261015_03"
down_revision: Union[str, Sequence[str], None] = "20261015_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_run",
        sa.Column("fallback_reason", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_run", "fallback_reason")
