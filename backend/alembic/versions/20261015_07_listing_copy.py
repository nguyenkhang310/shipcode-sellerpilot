"""Remember product copy requests across draft clarification turns."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_07"
down_revision = "20261015_06"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("product_draft", sa.Column("copy_instructions", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("product_draft", "copy_instructions")
