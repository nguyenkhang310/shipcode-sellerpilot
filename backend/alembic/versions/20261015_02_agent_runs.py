"""Add persisted chat agent runs.

Revision ID: 20261015_02
Revises: 20261015_01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261015_02"
down_revision: Union[str, Sequence[str], None] = "20261015_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=50), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("tool_name", sa.String(length=100), nullable=True),
        sa.Column("tool_arguments_json", sa.Text(), nullable=False),
        sa.Column("facts_json", sa.Text(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_run")),
    )
    op.create_index(op.f("ix_agent_run_created_at"), "agent_run", ["created_at"])
    op.create_index(op.f("ix_agent_run_intent"), "agent_run", ["intent"])
    op.create_index(op.f("ix_agent_run_status"), "agent_run", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_run_status"), table_name="agent_run")
    op.drop_index(op.f("ix_agent_run_intent"), table_name="agent_run")
    op.drop_index(op.f("ix_agent_run_created_at"), table_name="agent_run")
    op.drop_table("agent_run")
