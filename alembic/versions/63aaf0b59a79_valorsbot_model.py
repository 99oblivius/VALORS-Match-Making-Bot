"""ValorsBot model

Revision ID: 63aaf0b59a79
Revises: a49e48f25508
Create Date: 2024-07-19 18:39:07.235038

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63aaf0b59a79'
down_revision: Union[str, None] = 'a49e48f25508'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_blocked_users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('id', sa.Integer(), nullable=False))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_blocked_users', schema=None) as batch_op:
        batch_op.drop_column('id')

    # ### end Alembic commands ###
