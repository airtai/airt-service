"""Make model_id optional

Revision ID: 2d0c9ac716db
Revises: f1b812d5ec5a
Create Date: 2023-03-28 14:02:38.158545

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '2d0c9ac716db'
down_revision = 'f1b812d5ec5a'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('trainingstreamstatus', 'model_id',
               existing_type=mysql.VARCHAR(length=255),
               nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('trainingstreamstatus', 'model_id',
               existing_type=mysql.VARCHAR(length=255),
               nullable=False)
    # ### end Alembic commands ###
