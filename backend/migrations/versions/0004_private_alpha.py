"""Private-alpha access, quotas/budgets and safe operational state."""
from alembic import op
import sqlalchemy as sa
revision="0004"
down_revision="0003"
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('users',sa.Column('is_admin',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('users',sa.Column('disabled',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('users',sa.Column('resource_epoch',sa.Integer(),nullable=False,server_default='0'))
    op.add_column('api_keys',sa.Column('expires_at',sa.Float(),nullable=True))
    op.create_table('invites',sa.Column('id',sa.String(36),primary_key=True),sa.Column('token_hash',sa.String(64),unique=True,nullable=False),sa.Column('created_by',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('expires_at',sa.Float(),nullable=False),sa.Column('redeemed_by',sa.String(36)),sa.Column('revoked',sa.Boolean(),nullable=False))
    op.create_table('provider_usage',sa.Column('day',sa.String(10),primary_key=True),sa.Column('requests',sa.Integer(),nullable=False),sa.Column('input_chars',sa.Integer(),nullable=False))
    op.create_table('operational_metrics',sa.Column('key',sa.String(220),primary_key=True),sa.Column('count',sa.Integer(),nullable=False),sa.Column('total_ms',sa.Float(),nullable=False),sa.Column('max_ms',sa.Float(),nullable=False))
    op.create_table('worker_heartbeats',sa.Column('instance',sa.String(100),primary_key=True),sa.Column('updated_at',sa.Float(),nullable=False),sa.Column('details',sa.JSON(),nullable=False))


def downgrade():
    for table in ['worker_heartbeats','operational_metrics','provider_usage','invites']:op.drop_table(table)
    op.drop_column('api_keys','expires_at')
    for column in ['resource_epoch','disabled','is_admin']:op.drop_column('users',column)
