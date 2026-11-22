"""Durable bounded application exports, independent of document jobs."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("exports",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("project_id",sa.String(36),sa.ForeignKey("projects.id",ondelete="CASCADE"),nullable=False),
        sa.Column("status",sa.String(20),nullable=False),
        sa.Column("config",sa.JSON(),nullable=False),
        sa.Column("attempts",sa.Integer(),nullable=False),
        sa.Column("lease_token",sa.String(36)),sa.Column("lease_until",sa.Float()),
        sa.Column("error",sa.String(300)),sa.Column("size_bytes",sa.Integer(),nullable=False),
        sa.Column("sha256",sa.String(64)),sa.Column("created_at",sa.Float(),nullable=False),
        sa.Column("expires_at",sa.Float(),nullable=False))
    op.create_index("ix_exports_project_id","exports",["project_id"])
    op.create_index("ix_exports_status","exports",["status"])


def downgrade():
    op.drop_table("exports")
