"""add support wall posts

Revision ID: 7b2c9d4e8f10
Revises: e6a1d2c3b4f5
Create Date: 2026-06-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '7b2c9d4e8f10'
down_revision = 'e6a1d2c3b4f5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'support_wall_posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('submitted_by_account_id', sa.Integer(), nullable=True),
        sa.Column('approved_by_account_id', sa.Integer(), nullable=True),
        sa.Column('submitted_on_behalf_of', sa.Boolean(), nullable=False),
        sa.Column('public_name', sa.String(length=120), nullable=False),
        sa.Column('role', sa.String(length=80), nullable=False),
        sa.Column('location', sa.String(length=120), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('link', sa.String(length=500), nullable=True),
        sa.Column('hns_name', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('verification_status', sa.String(length=40), nullable=False),
        sa.Column('verification_method', sa.String(length=40), nullable=True),
        sa.Column('verification_payload_private', sa.Text(), nullable=True),
        sa.Column('verification_nonce', sa.String(length=120), nullable=True),
        sa.Column('source_channel', sa.String(length=40), nullable=True),
        sa.Column('source_note_private', sa.Text(), nullable=True),
        sa.Column('consent_status', sa.String(length=40), nullable=False),
        sa.Column('admin_note_private', sa.Text(), nullable=True),
        sa.Column('badges_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.ForeignKeyConstraint(['approved_by_account_id'], ['accounts.id']),
        sa.ForeignKeyConstraint(['submitted_by_account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('verification_nonce'),
    )
    with op.batch_alter_table('support_wall_posts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_support_wall_posts_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_approved_at'), ['approved_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_approved_by_account_id'), ['approved_by_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_consent_status'), ['consent_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_hns_name'), ['hns_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_source_channel'), ['source_channel'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_submitted_by_account_id'), ['submitted_by_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_submitted_on_behalf_of'), ['submitted_on_behalf_of'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_verification_method'), ['verification_method'], unique=False)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_verification_nonce'), ['verification_nonce'], unique=True)
        batch_op.create_index(batch_op.f('ix_support_wall_posts_verification_status'), ['verification_status'], unique=False)


def downgrade():
    with op.batch_alter_table('support_wall_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_verification_status'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_verification_nonce'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_verification_method'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_submitted_on_behalf_of'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_submitted_by_account_id'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_status'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_source_channel'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_hns_name'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_created_at'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_consent_status'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_approved_by_account_id'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_approved_at'))
        batch_op.drop_index(batch_op.f('ix_support_wall_posts_account_id'))
    op.drop_table('support_wall_posts')
