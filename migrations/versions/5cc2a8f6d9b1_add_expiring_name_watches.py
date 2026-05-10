"""add expiring name watches

Revision ID: 5cc2a8f6d9b1
Revises: f2b4a1c7e9d0
Create Date: 2026-05-10 18:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '5cc2a8f6d9b1'
down_revision = 'f2b4a1c7e9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'expiring_name_watches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('network', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('state', sa.String(length=40), nullable=True),
        sa.Column('renewal_height', sa.Integer(), nullable=True),
        sa.Column('expiration_height', sa.Integer(), nullable=True),
        sa.Column('blocks_until_expire', sa.Integer(), nullable=True),
        sa.Column('days_until_expire', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('hours_until_expire', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('expired', sa.Boolean(), nullable=False),
        sa.Column('found', sa.Boolean(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('source_height', sa.Integer(), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'network', name='uq_expiring_name_watches_name_network'),
    )
    with op.batch_alter_table('expiring_name_watches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_blocks_until_expire'), ['blocks_until_expire'], unique=False)
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_expiration_height'), ['expiration_height'], unique=False)
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_expired'), ['expired'], unique=False)
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_found'), ['found'], unique=False)
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_last_checked_at'), ['last_checked_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_network'), ['network'], unique=False)
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_source_height'), ['source_height'], unique=False)
        batch_op.create_index(batch_op.f('ix_expiring_name_watches_state'), ['state'], unique=False)


def downgrade():
    with op.batch_alter_table('expiring_name_watches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_state'))
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_source_height'))
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_source'))
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_network'))
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_name'))
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_last_checked_at'))
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_found'))
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_expired'))
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_expiration_height'))
        batch_op.drop_index(batch_op.f('ix_expiring_name_watches_blocks_until_expire'))

    op.drop_table('expiring_name_watches')
