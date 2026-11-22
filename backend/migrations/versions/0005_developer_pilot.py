"""Opt-in developer pilot, private feedback and offline deployment evidence."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None
def col(name, type_, nullable=False, fk=None):
    return sa.Column(name, type_, *([sa.ForeignKey(fk, ondelete='CASCADE')] if fk else []), nullable=nullable)


def upgrade():
    op.create_table('pilot_participants', sa.Column('id', sa.String(36), primary_key=True),
        col('user_id', sa.String(36), fk='users.id'), col('cohort', sa.String(20)),
        col('authorized_by', sa.String(36), fk='users.id'), col('authorization_reference', sa.String(100)),
        col('enrolled_at', sa.Float()), col('consented_at', sa.Float(), True), col('consent_version', sa.String(30), True),
        col('expires_at', sa.Float()), col('event_count', sa.Integer()), col('lock_epoch', sa.Integer()),
        col('trial_reviewed_at', sa.Float(), True), col('trial_reviewed_by', sa.String(36), True), sa.UniqueConstraint('user_id'))
    op.create_index('ix_pilot_participants_expires_at', 'pilot_participants', ['expires_at'])
    op.create_table('pilot_events', sa.Column('id', sa.String(36), primary_key=True),
        col('participant_id', sa.String(36), fk='pilot_participants.id'), col('kind', sa.String(40)),
        col('entity_hash', sa.String(64)), col('observed_at', sa.Float()), col('elapsed_ms', sa.Float(), True),
        sa.UniqueConstraint('participant_id', 'kind', 'entity_hash'))
    op.create_table('pilot_tasks', sa.Column('id', sa.String(36), primary_key=True),
        col('participant_id', sa.String(36), fk='pilot_participants.id'), col('task_number', sa.Integer()),
        col('status', sa.String(20)), col('duration_seconds', sa.Integer()), col('errors', sa.Integer()),
        col('assistance', sa.Integer()), col('difficulty', sa.Integer()), col('feedback', sa.String(2000)), col('updated_at', sa.Float()),
        sa.UniqueConstraint('participant_id', 'task_number'))
    op.create_table('pilot_issues', sa.Column('id', sa.String(36), primary_key=True),
        col('participant_id', sa.String(36), fk='pilot_participants.id'), col('category', sa.String(30)),
        col('severity', sa.String(10)), col('status', sa.String(20)), col('description', sa.String(2000)),
        col('sanitized_reproduction', sa.String(2000)), col('engineering_reference', sa.String(150)),
        col('reviewed_by', sa.String(36), True), col('reviewed_at', sa.Float(), True), col('export_approved', sa.Boolean()), col('created_at', sa.Float()))
    op.create_table('pilot_deployments', sa.Column('id', sa.String(36), primary_key=True),
        col('participant_id', sa.String(36), fk='pilot_participants.id'), col('export_id', sa.String(36)), col('template_sha256', sa.String(64)),
        col('public_key', sa.String(64)), col('challenge', sa.String(64)), col('issued_at', sa.Float()), col('expires_at', sa.Float()),
        col('received_at', sa.Float(), True), col('query_received_at', sa.Float(), True), col('proof_sha256', sa.String(64), True), sa.UniqueConstraint('export_id'))
    op.create_table('pilot_operator_state', sa.Column('id', sa.String(20), primary_key=True),
        col('checklist', sa.JSON()), col('incident_owner', sa.String(100)), col('updated_by', sa.String(36)), col('updated_at', sa.Float()))
    for table in ('pilot_events', 'pilot_tasks', 'pilot_issues', 'pilot_deployments'):
        op.create_index('ix_' + table + '_participant_id', table, ['participant_id'])


def downgrade():
    for table in ('pilot_operator_state', 'pilot_deployments', 'pilot_issues', 'pilot_tasks', 'pilot_events', 'pilot_participants'):
        op.drop_table(table)
