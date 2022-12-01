"""Add super_user column

Revision ID: aec2a7dc19fa
Revises: 81a3e3c5fcdc
Create Date: 2021-09-30 07:33:55.022785

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'aec2a7dc19fa'
down_revision = '81a3e3c5fcdc'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('user', sa.Column('super_user', sa.Boolean(), nullable=True))
    op.create_index(op.f('ix_user_super_user'), 'user', ['super_user'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_user_super_user'), table_name='user')
    op.drop_column('user', 'super_user')
    # ### end Alembic commands ###
