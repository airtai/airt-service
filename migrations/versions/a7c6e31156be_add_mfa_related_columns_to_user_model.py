"""Add MFA related columns to User model

Revision ID: a7c6e31156be
Revises: 79b8699cbc23
Create Date: 2022-06-16 12:12:46.183788

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'a7c6e31156be'
down_revision = '79b8699cbc23'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('user', sa.Column('mfa_secret', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('user', sa.Column('is_mfa_activated', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('user', 'mfa_secret')
    op.drop_column('user', 'is_mfa_activated')
    # ### end Alembic commands ###
