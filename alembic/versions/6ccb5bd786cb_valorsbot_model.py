"""ValorsBot model

Revision ID: 6ccb5bd786cb
Revises: 5a5ea26a0a9b
Create Date: 2025-04-12 08:45:59.469362

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ccb5bd786cb'
down_revision: Union[str, None] = '5a5ea26a0a9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('ticket_transcripts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('guild_id', sa.BigInteger(), nullable=False))
        batch_op.add_column(sa.Column('archived_at', sa.TIMESTAMP(timezone=True), nullable=False))
        batch_op.add_column(sa.Column('data', sa.LargeBinary(), nullable=False))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('ticket_transcripts', schema=None) as batch_op:
        batch_op.drop_column('data')
        batch_op.drop_column('archived_at')
        batch_op.drop_column('guild_id')

    # ### end Alembic commands ###
