"""ValorsBot model

Revision ID: fffaa49d171f
Revises: 010ed3ae9fd3
Create Date: 2024-07-02 00:43:39.298050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fffaa49d171f'
down_revision: Union[str, None] = '010ed3ae9fd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('mm_bot_ranks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('mmr_threshold', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.BigInteger(), nullable=False),
    sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['guild_id'], ['bot_settings.guild_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mm_bot_user_summary_stats', schema=None) as batch_op:
        batch_op.drop_column('top_winstreak')
        batch_op.drop_column('top_losestreak')

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_user_summary_stats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('top_losestreak', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('top_winstreak', sa.INTEGER(), autoincrement=False, nullable=True))

    op.drop_table('mm_bot_ranks')
    # ### end Alembic commands ###
