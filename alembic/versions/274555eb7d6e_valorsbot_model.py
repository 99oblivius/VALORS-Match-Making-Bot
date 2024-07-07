"""ValorsBot model

Revision ID: 274555eb7d6e
Revises: 15e78186d7f0
Create Date: 2024-07-04 20:35:01.948124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '274555eb7d6e'
down_revision: Union[str, None] = '15e78186d7f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_matches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('log_message', sa.BigInteger(), nullable=True))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_matches', schema=None) as batch_op:
        batch_op.drop_column('log_message')

    # ### end Alembic commands ###