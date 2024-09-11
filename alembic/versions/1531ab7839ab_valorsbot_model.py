"""ValorsBot model

Revision ID: 1531ab7839ab
Revises: 5cdf42e9fc8b
Create Date: 2024-09-08 11:08:50.664723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1531ab7839ab'
down_revision: Union[str, None] = '5cdf42e9fc8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('mm_bot_user_notifications',
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('queue_count', sa.Integer(), nullable=False),
    sa.Column('expiry', sa.Integer(), nullable=True),
    sa.Column('one_time', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id'], ),
    sa.PrimaryKeyConstraint('guild_id', 'user_id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('mm_bot_user_notifications')
    # ### end Alembic commands ###