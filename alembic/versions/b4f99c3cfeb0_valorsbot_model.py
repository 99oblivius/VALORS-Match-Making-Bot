"""ValorsBot model

Revision ID: b4f99c3cfeb0
Revises: a65d748aa112
Create Date: 2024-06-21 06:06:48.499324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f99c3cfeb0'
down_revision: Union[str, None] = 'a65d748aa112'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_user_map_picks', schema=None) as batch_op:
        batch_op.drop_constraint('unique_user_match_map', type_='unique')
        batch_op.create_unique_constraint('unique_user_match_map', ['user_id', 'match_id'])

    with op.batch_alter_table('mm_bot_user_side_picks', schema=None) as batch_op:
        batch_op.drop_constraint('unique_user_match_side', type_='unique')
        batch_op.create_unique_constraint('unique_user_match_side', ['user_id', 'match_id'])

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mm_bot_user_side_picks', schema=None) as batch_op:
        batch_op.drop_constraint('unique_user_match_side', type_='unique')
        batch_op.create_unique_constraint('unique_user_match_side', ['user_id', 'match_id', 'side'])

    with op.batch_alter_table('mm_bot_user_map_picks', schema=None) as batch_op:
        batch_op.drop_constraint('unique_user_match_map', type_='unique')
        batch_op.create_unique_constraint('unique_user_match_map', ['user_id', 'match_id', 'map'])

    # ### end Alembic commands ###
