"""ValorsBot model

Revision ID: 3650f9ec10e1
Revises: 51a66e3a4913
Create Date: 2024-06-12 11:03:25.007440

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3650f9ec10e1'
down_revision: Union[str, None] = '51a66e3a4913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_users', schema=None) as batch_op:
        batch_op.alter_column('team_a',
               existing_type=sa.INTEGER(),
               nullable=True,
               existing_server_default=sa.text('0'))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_users', schema=None) as batch_op:
        batch_op.alter_column('team_a',
               existing_type=sa.INTEGER(),
               nullable=False,
               existing_server_default=sa.text('0'))

    # ### end Alembic commands ###