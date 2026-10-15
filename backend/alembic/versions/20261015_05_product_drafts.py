"""Persist image-backed product publishing drafts."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_05"
down_revision = "20261015_04"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_draft",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("shop_slug", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("image_filename", sa.String(length=255), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("image_mime", sa.String(length=50), nullable=False),
        sa.Column("image_bytes", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("category_name", sa.String(length=100), nullable=True),
        sa.Column("price_vnd", sa.Integer(), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("published_product_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_draft")),
    )
    op.create_index(op.f("ix_product_draft_conversation_id"), "product_draft", ["conversation_id"])
    op.create_index(op.f("ix_product_draft_shop_slug"), "product_draft", ["shop_slug"])
    op.create_index(op.f("ix_product_draft_status"), "product_draft", ["status"])
    op.add_column("agent_run", sa.Column("product_draft_id", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("agent_run", "product_draft_id")
    op.drop_index(op.f("ix_product_draft_status"), table_name="product_draft")
    op.drop_index(op.f("ix_product_draft_shop_slug"), table_name="product_draft")
    op.drop_index(op.f("ix_product_draft_conversation_id"), table_name="product_draft")
    op.drop_table("product_draft")
