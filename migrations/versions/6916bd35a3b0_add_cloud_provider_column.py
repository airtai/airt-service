"""Add cloud provider column

Revision ID: 6916bd35a3b0
Revises: c3a1afa5e677
Create Date: 2022-09-13 05:50:04.961556

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '6916bd35a3b0'
down_revision = '16344bffcee3'
branch_labels = None
depends_on = None

from sqlalchemy.exc import NoResultFound
from airt_service.db.models import get_session_with_context

def set_cloud_provider_for_existing_rows(table: str):
    """Set value for existing row's cloud_provider column"""
    with get_session_with_context() as session:
        try:
            session.exec(f"UPDATE {table} SET cloud_provider = IF(region LIKE '%-%', 'aws', 'azure')")
            session.commit()
        except NoResultFound:
            pass


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('datablob', sa.Column('cloud_provider', sa.Enum('aws', 'azure', name='cloud_provider'), nullable=False))
    set_cloud_provider_for_existing_rows(table="datablob")
    
    op.add_column('datasource', sa.Column('cloud_provider', sa.Enum('aws', 'azure', name='cloud_provider'), nullable=False))
    set_cloud_provider_for_existing_rows(table="datasource")
    
    op.add_column('model', sa.Column('cloud_provider', sa.Enum('aws', 'azure', name='cloud_provider'), nullable=False))
    set_cloud_provider_for_existing_rows(table="model")
    
    op.add_column('prediction', sa.Column('cloud_provider', sa.Enum('aws', 'azure', name='cloud_provider'), nullable=False))
    set_cloud_provider_for_existing_rows(table="prediction")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('prediction', 'cloud_provider')
    op.drop_column('model', 'cloud_provider')
    op.drop_column('datasource', 'cloud_provider')
    op.drop_column('datablob', 'cloud_provider')
    # ### end Alembic commands ###
