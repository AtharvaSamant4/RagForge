"""Preserve sources and indexes while recording model transitions."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("index_profile", sa.JSON(), nullable=True))
    op.add_column("projects", sa.Column("index_generation", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("projects", "index_generation")
    op.drop_column("projects", "index_profile")
