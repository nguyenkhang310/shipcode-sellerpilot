"""Add agent action proposals and audit log.

Revision ID: 20261015_01
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261015_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "action_proposal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("target_kind", sa.String(length=20), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("old_price_vnd", sa.Integer(), nullable=False),
        sa.Column("new_price_vnd", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_proposal")),
    )
    op.create_index(op.f("ix_action_proposal_sku"), "action_proposal", ["sku"])
    op.create_index(op.f("ix_action_proposal_status"), "action_proposal", ["status"])
    op.create_table(
        "action_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("before_value", sa.Integer(), nullable=False),
        sa.Column("after_value", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_audit")),
        sa.UniqueConstraint("proposal_id", name="uq_action_audit_proposal_id"),
    )
    op.create_index(op.f("ix_action_audit_proposal_id"), "action_audit", ["proposal_id"])
    op.create_index(op.f("ix_action_audit_sku"), "action_audit", ["sku"])


def downgrade() -> None:
    op.drop_index(op.f("ix_action_audit_sku"), table_name="action_audit")
    op.drop_index(op.f("ix_action_audit_proposal_id"), table_name="action_audit")
    op.drop_table("action_audit")
    op.drop_index(op.f("ix_action_proposal_status"), table_name="action_proposal")
    op.drop_index(op.f("ix_action_proposal_sku"), table_name="action_proposal")
    op.drop_table("action_proposal")
