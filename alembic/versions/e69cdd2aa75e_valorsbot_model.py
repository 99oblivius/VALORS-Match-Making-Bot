"""ValorsBot model

Revision ID: e69cdd2aa75e
Revises: ce6e9959690a
Create Date: 2024-06-21 05:31:42.238209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e69cdd2aa75e'
down_revision: Union[str, None] = 'ce6e9959690a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_user_map_picks', schema=None) as batch_op:
        batch_op.create_unique_constraint(None, ['user_id'])
        batch_op.create_unique_constraint(None, ['match_id'])
        batch_op.create_unique_constraint(None, ['map'])

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_user_map_picks', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='unique')
        batch_op.drop_constraint(None, type_='unique')
        batch_op.drop_constraint(None, type_='unique')

    # ### end Alembic commands ###