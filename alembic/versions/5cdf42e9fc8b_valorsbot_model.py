"""ValorsBot model

Revision ID: 5cdf42e9fc8b
Revises: 516321a9e12e
Create Date: 2024-07-23 01:29:37.021600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5cdf42e9fc8b'
down_revision: Union[str, None] = '516321a9e12e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_blocked_users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reason', sa.Text(), nullable=True))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_blocked_users', schema=None) as batch_op:
        batch_op.drop_column('reason')

    # ### end Alembic commands ###
