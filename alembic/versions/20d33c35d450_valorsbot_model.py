"""ValorsBot model

Revision ID: 20d33c35d450
Revises: 
Create Date: 2024-06-21 02:16:47.765353

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20d33c35d450'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('bot_settings',
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('staff_channel', sa.BigInteger(), nullable=True),
    sa.Column('log_channel', sa.BigInteger(), nullable=True),
    sa.Column('mm_queue_channel', sa.BigInteger(), nullable=True),
    sa.Column('mm_queue_message', sa.BigInteger(), nullable=True),
    sa.Column('mm_queue_periods', sa.Text(), nullable=True),
    sa.Column('mm_accept_period', sa.SmallInteger(), nullable=False),
    sa.Column('mm_maps_range', sa.SmallInteger(), nullable=False),
    sa.Column('mm_maps_phase', sa.SmallInteger(), nullable=False),
    sa.Column('mm_text_channel', sa.BigInteger(), nullable=True),
    sa.Column('mm_queue_reminder', sa.Integer(), nullable=False),
    sa.Column('mm_voice_channel', sa.BigInteger(), nullable=True),
    sa.Column('mm_log_channel', sa.BigInteger(), nullable=True),
    sa.Column('mm_lfg_role', sa.BigInteger(), nullable=True),
    sa.Column('mm_staff_role', sa.BigInteger(), nullable=True),
    sa.Column('region_channel', sa.BigInteger(), nullable=True),
    sa.Column('region_message', sa.BigInteger(), nullable=True),
    sa.PrimaryKeyConstraint('guild_id')
    )
    op.create_table('mm_bot_matches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('queue_channel', sa.BigInteger(), nullable=False),
    sa.Column('match_thread', sa.BigInteger(), nullable=True),
    sa.Column('match_message', sa.BigInteger(), nullable=True),
    sa.Column('maps_range', sa.BigInteger(), nullable=False),
    sa.Column('maps_phase', sa.BigInteger(), nullable=False),
    sa.Column('phase', sa.Enum('NONE', 'A_BAN', 'B_BAN', 'A_PICK', 'B_PICK', name='phase'), nullable=False),
    sa.Column('a_thread', sa.BigInteger(), nullable=True),
    sa.Column('b_thread', sa.BigInteger(), nullable=True),
    sa.Column('a_vc', sa.BigInteger(), nullable=True),
    sa.Column('b_vc', sa.BigInteger(), nullable=True),
    sa.Column('a_message', sa.BigInteger(), nullable=True),
    sa.Column('b_message', sa.BigInteger(), nullable=True),
    sa.Column('a_bans', sa.ARRAY(sa.String(length=32)), nullable=True),
    sa.Column('b_bans', sa.ARRAY(sa.String(length=32)), nullable=True),
    sa.Column('a_mmr', sa.Integer(), nullable=True),
    sa.Column('b_mmr', sa.Integer(), nullable=True),
    sa.Column('map', sa.String(length=32), nullable=True),
    sa.Column('a_score', sa.SmallInteger(), nullable=True),
    sa.Column('b_score', sa.SmallInteger(), nullable=True),
    sa.Column('start_timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('end_timestamp', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('complete', sa.Boolean(), nullable=False),
    sa.Column('state', sa.SmallInteger(), nullable=False),
    sa.Column('b_side', sa.Enum('T', 'CT', name='side'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bot_regions',
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('label', sa.String(length=32), nullable=False),
    sa.Column('emoji', sa.String(length=32), nullable=True),
    sa.Column('index', sa.SmallInteger(), nullable=True),
    sa.ForeignKeyConstraint(['guild_id'], ['bot_settings.guild_id'], ),
    sa.PrimaryKeyConstraint('guild_id', 'label')
    )
    op.create_table('mm_bot_maps',
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('map', sa.String(length=32), nullable=False),
    sa.Column('media', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('order', sa.SmallInteger(), nullable=True),
    sa.ForeignKeyConstraint(['guild_id'], ['bot_settings.guild_id'], ),
    sa.PrimaryKeyConstraint('guild_id', 'map')
    )
    op.create_table('mm_bot_users',
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('display_name', sa.String(length=32), nullable=True),
    sa.Column('region', sa.String(length=32), nullable=True),
    sa.Column('mmr', sa.Integer(), nullable=False),
    sa.Column('games', sa.Integer(), nullable=True),
    sa.Column('wins', sa.Integer(), nullable=True),
    sa.Column('loss', sa.Integer(), nullable=True),
    sa.Column('team_a', sa.Integer(), nullable=True),
    sa.Column('registered', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id', 'region'], ['bot_regions.guild_id', 'bot_regions.label'], ),
    sa.PrimaryKeyConstraint('guild_id', 'user_id')
    )
    op.create_table('mm_bot_match_users',
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('accepted', sa.Boolean(), nullable=False),
    sa.Column('team', sa.Enum('A', 'B', name='team'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id'], ),
    sa.ForeignKeyConstraint(['match_id'], ['mm_bot_matches.id'], ),
    sa.PrimaryKeyConstraint('guild_id', 'user_id', 'match_id')
    )
    op.create_table('mm_bot_mmr_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('mmr', sa.Integer(), nullable=False),
    sa.Column('mmr_delta', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mm_bot_queue_users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('queue_channel', sa.BigInteger(), nullable=False),
    sa.Column('queue_expiry', sa.Integer(), nullable=True),
    sa.Column('in_queue', sa.Boolean(), nullable=False),
    sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mm_bot_user_bans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('map', sa.String(length=32), nullable=False),
    sa.Column('phase', sa.Enum('NONE', 'A_BAN', 'B_BAN', 'A_PICK', 'B_PICK', name='phase'), nullable=True),
    sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id'], ),
    sa.ForeignKeyConstraint(['match_id'], ['mm_bot_matches.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mm_bot_user_map_picks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('map', sa.String(length=32), nullable=False),
    sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id'], ),
    sa.ForeignKeyConstraint(['match_id'], ['mm_bot_matches.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mm_bot_user_side_picks',
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('side', sa.Enum('T', 'CT', name='side'), nullable=False),
    sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id'], ),
    sa.ForeignKeyConstraint(['match_id'], ['mm_bot_matches.id'], ),
    sa.PrimaryKeyConstraint('guild_id', 'user_id', 'match_id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('mm_bot_user_side_picks')
    op.drop_table('mm_bot_user_map_picks')
    op.drop_table('mm_bot_user_bans')
    op.drop_table('mm_bot_queue_users')
    op.drop_table('mm_bot_mmr_history')
    op.drop_table('mm_bot_match_users')
    op.drop_table('mm_bot_users')
    op.drop_table('mm_bot_maps')
    op.drop_table('bot_regions')
    op.drop_table('mm_bot_matches')
    op.drop_table('bot_settings')
    # ### end Alembic commands ###
