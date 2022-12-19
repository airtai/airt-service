"""Include captn as subscription type

Revision ID: 64ad4d8fb7c9
Revises: dc11cc0e88d1
Create Date: 2022-07-07 13:44:30.278833

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = '64ad4d8fb7c9'
down_revision = 'dc11cc0e88d1'
branch_labels = None
depends_on = None

# Based on - https://gitpress.io/@natamacm/mysql-example-alembic_change_enum

def upgrade():
    op.alter_column('user', 'subscription_type',
               existing_type=mysql.ENUM('small', 'medium', 'large', 'infobip', 'test', 'superuser'),
               nullable=False, type_=mysql.ENUM('small', 'medium', 'large', 'infobip', 'captn', 'test', 'superuser'))

def downgrade():
    op.alter_column('user', 'subscription_type',
               existing_type=mysql.ENUM('small', 'medium', 'large', 'infobip', 'captn', 'test', 'superuser'), 
               nullable=False, type_=mysql.ENUM('small', 'medium', 'large', 'infobip', 'test', 'superuser'))

