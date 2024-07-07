"""ValorsBot model

Revision ID: aa08ef5db5c1
Revises: 274555eb7d6e
Create Date: 2024-07-07 10:49:22.946945

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa08ef5db5c1'
down_revision: Union[str, None] = '274555eb7d6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('bot_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('leaderboard_channel', sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column('leaderboard_message', sa.BigInteger(), nullable=True))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('bot_settings', schema=None) as batch_op:
        batch_op.drop_column('leaderboard_message')
        batch_op.drop_column('leaderboard_channel')

    # ### end Alembic commands ###
