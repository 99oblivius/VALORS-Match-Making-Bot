"""ValorsBot model

Revision ID: 8d4dacee140a
Revises: 6b86454d8f9f
Create Date: 2024-06-21 06:00:18.421566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d4dacee140a'
down_revision: Union[str, None] = '6b86454d8f9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('mm_bot_user_map_picks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('map', sa.String(length=32), nullable=False),
    sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id'], ),
    sa.ForeignKeyConstraint(['match_id'], ['mm_bot_matches.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'match_id', 'map', name='unique_user_match_map')
    )
    op.create_table('mm_bot_user_side_picks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('match_id', sa.Integer(), nullable=False),
    sa.Column('side', sa.Enum('T', 'CT', name='side'), nullable=False),
    sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id'], ),
    sa.ForeignKeyConstraint(['match_id'], ['mm_bot_matches.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'match_id', 'side', name='unique_user_match_side')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('mm_bot_user_side_picks')
    op.drop_table('mm_bot_user_map_picks')
    # ### end Alembic commands ###
