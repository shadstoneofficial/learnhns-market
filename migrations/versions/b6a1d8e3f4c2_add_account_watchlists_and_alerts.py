"""add account watchlists and alerts

Revision ID: b6a1d8e3f4c2
Revises: a7d4c2e8b931
Create Date: 2026-05-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b6a1d8e3f4c2'
down_revision = 'a7d4c2e8b931'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gfavip_user_id', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('username', sa.String(length=100), nullable=True),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('gfavip_tier', sa.String(length=40), nullable=False),
        sa.Column('local_tier', sa.String(length=40), nullable=False),
        sa.Column('email_verified_at', sa.DateTime(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gfavip_user_id'),
    )
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_accounts_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_accounts_gfavip_tier'), ['gfavip_tier'], unique=False)
        batch_op.create_index(batch_op.f('ix_accounts_gfavip_user_id'), ['gfavip_user_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_accounts_last_login_at'), ['last_login_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_accounts_local_tier'), ['local_tier'], unique=False)
        batch_op.create_index(batch_op.f('ix_accounts_username'), ['username'], unique=False)

    op.create_table(
        'account_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('session_token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_token_hash'),
    )
    with op.batch_alter_table('account_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_account_sessions_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_sessions_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_sessions_revoked_at'), ['revoked_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_sessions_session_token_hash'), ['session_token_hash'], unique=True)

    op.create_table(
        'account_watchlist_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('network', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('alerts_enabled', sa.Boolean(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('tags_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'network', 'name', name='uq_account_watchlist_account_network_name'),
    )
    with op.batch_alter_table('account_watchlist_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_account_watchlist_items_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_watchlist_items_alerts_enabled'), ['alerts_enabled'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_watchlist_items_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_watchlist_items_network'), ['network'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_watchlist_items_source'), ['source'], unique=False)

    op.create_table(
        'account_alert_preferences',
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('email_enabled', sa.Boolean(), nullable=False),
        sa.Column('digest_enabled', sa.Boolean(), nullable=False),
        sa.Column('reminder_days_json', sa.JSON(), nullable=False),
        sa.Column('timezone', sa.String(length=80), nullable=False),
        sa.Column('manage_token_hash', sa.String(length=64), nullable=True),
        sa.Column('unsubscribed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('account_id'),
        sa.UniqueConstraint('manage_token_hash'),
    )
    with op.batch_alter_table('account_alert_preferences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_account_alert_preferences_email_enabled'), ['email_enabled'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_alert_preferences_manage_token_hash'), ['manage_token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_account_alert_preferences_unsubscribed_at'), ['unsubscribed_at'], unique=False)

    op.create_table(
        'account_alert_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('watchlist_item_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('network', sa.String(length=20), nullable=False),
        sa.Column('alert_type', sa.String(length=40), nullable=False),
        sa.Column('cadence_days', sa.Integer(), nullable=False),
        sa.Column('expiration_height', sa.Integer(), nullable=True),
        sa.Column('blocks_until_expire', sa.Integer(), nullable=True),
        sa.Column('days_until_expire', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('mailgun_message_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.ForeignKeyConstraint(['watchlist_item_id'], ['account_watchlist_items.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'watchlist_item_id', 'alert_type', 'cadence_days', 'expiration_height', name='uq_account_alert_event_cadence'),
    )
    with op.batch_alter_table('account_alert_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_account_alert_events_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_alert_events_alert_type'), ['alert_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_alert_events_cadence_days'), ['cadence_days'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_alert_events_expiration_height'), ['expiration_height'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_alert_events_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_alert_events_network'), ['network'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_alert_events_sent_at'), ['sent_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_alert_events_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_account_alert_events_watchlist_item_id'), ['watchlist_item_id'], unique=False)


def downgrade():
    with op.batch_alter_table('account_alert_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_account_alert_events_watchlist_item_id'))
        batch_op.drop_index(batch_op.f('ix_account_alert_events_status'))
        batch_op.drop_index(batch_op.f('ix_account_alert_events_sent_at'))
        batch_op.drop_index(batch_op.f('ix_account_alert_events_network'))
        batch_op.drop_index(batch_op.f('ix_account_alert_events_name'))
        batch_op.drop_index(batch_op.f('ix_account_alert_events_expiration_height'))
        batch_op.drop_index(batch_op.f('ix_account_alert_events_cadence_days'))
        batch_op.drop_index(batch_op.f('ix_account_alert_events_alert_type'))
        batch_op.drop_index(batch_op.f('ix_account_alert_events_account_id'))
    op.drop_table('account_alert_events')

    with op.batch_alter_table('account_alert_preferences', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_account_alert_preferences_unsubscribed_at'))
        batch_op.drop_index(batch_op.f('ix_account_alert_preferences_manage_token_hash'))
        batch_op.drop_index(batch_op.f('ix_account_alert_preferences_email_enabled'))
    op.drop_table('account_alert_preferences')

    with op.batch_alter_table('account_watchlist_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_account_watchlist_items_source'))
        batch_op.drop_index(batch_op.f('ix_account_watchlist_items_network'))
        batch_op.drop_index(batch_op.f('ix_account_watchlist_items_name'))
        batch_op.drop_index(batch_op.f('ix_account_watchlist_items_alerts_enabled'))
        batch_op.drop_index(batch_op.f('ix_account_watchlist_items_account_id'))
    op.drop_table('account_watchlist_items')

    with op.batch_alter_table('account_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_account_sessions_session_token_hash'))
        batch_op.drop_index(batch_op.f('ix_account_sessions_revoked_at'))
        batch_op.drop_index(batch_op.f('ix_account_sessions_expires_at'))
        batch_op.drop_index(batch_op.f('ix_account_sessions_account_id'))
    op.drop_table('account_sessions')

    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_accounts_username'))
        batch_op.drop_index(batch_op.f('ix_accounts_local_tier'))
        batch_op.drop_index(batch_op.f('ix_accounts_last_login_at'))
        batch_op.drop_index(batch_op.f('ix_accounts_gfavip_user_id'))
        batch_op.drop_index(batch_op.f('ix_accounts_gfavip_tier'))
        batch_op.drop_index(batch_op.f('ix_accounts_email'))
    op.drop_table('accounts')
