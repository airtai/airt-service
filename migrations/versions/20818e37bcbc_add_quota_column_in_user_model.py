"""Add quota column in user model

Revision ID: 20818e37bcbc
Revises: b987e57c4e1d
Create Date: 2021-10-19 07:07:36.432600

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '20818e37bcbc'
down_revision = 'b987e57c4e1d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('user', sa.Column('quota', sa.Boolean(), nullable=True))
    op.create_index(op.f('ix_user_quota'), 'user', ['quota'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_user_quota'), table_name='user')
    op.drop_column('user', 'quota')
    # ### end Alembic commands ###
