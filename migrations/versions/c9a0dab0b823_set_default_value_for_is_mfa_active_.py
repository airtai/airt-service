"""Set default value for is_mfa_active column to False for existing users

Revision ID: c9a0dab0b823
Revises: 64ad4d8fb7c9
Create Date: 2022-07-11 08:31:03.588639

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'c9a0dab0b823'
down_revision = '64ad4d8fb7c9'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("UPDATE user SET is_mfa_active = false WHERE is_mfa_active IS NULL")
    op.alter_column('user', 'is_mfa_active',
               existing_type=mysql.TINYINT(display_width=1),
               nullable=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('user', 'is_mfa_active',
               existing_type=mysql.TINYINT(display_width=1),
               nullable=True)
    # ### end Alembic commands ###
