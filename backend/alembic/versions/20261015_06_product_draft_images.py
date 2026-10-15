"""Allow a product draft to carry a gallery of up to six images."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_06"
down_revision = "20261015_05"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("product_draft", sa.Column("extra_images_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("product_draft", "extra_images_json")
