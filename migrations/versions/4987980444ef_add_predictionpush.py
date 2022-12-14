"""Add PredictionPush

Revision ID: 4987980444ef
Revises: 20818e37bcbc
Create Date: 2021-11-09 12:13:13.318553

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '4987980444ef'
down_revision = '20818e37bcbc'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('predictionpush',
    sa.Column('total_steps', sa.Integer(), nullable=False),
    sa.Column('completed_steps', sa.Integer(), nullable=True),
    sa.Column('error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('created', sa.DateTime(), nullable=False),
    sa.Column('prediction_id', sa.Integer(), nullable=True),
    sa.Column('datasource_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['datasource_id'], ['datasource.id'], ),
    sa.ForeignKeyConstraint(['prediction_id'], ['prediction.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_predictionpush_completed_steps'), 'predictionpush', ['completed_steps'], unique=False)
    op.create_index(op.f('ix_predictionpush_created'), 'predictionpush', ['created'], unique=False)
    op.create_index(op.f('ix_predictionpush_datasource_id'), 'predictionpush', ['datasource_id'], unique=False)
    op.create_index(op.f('ix_predictionpush_error'), 'predictionpush', ['error'], unique=False)
    op.create_index(op.f('ix_predictionpush_id'), 'predictionpush', ['id'], unique=False)
    op.create_index(op.f('ix_predictionpush_prediction_id'), 'predictionpush', ['prediction_id'], unique=False)
    op.create_index(op.f('ix_predictionpush_total_steps'), 'predictionpush', ['total_steps'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_predictionpush_total_steps'), table_name='predictionpush')
    op.drop_index(op.f('ix_predictionpush_prediction_id'), table_name='predictionpush')
    op.drop_index(op.f('ix_predictionpush_id'), table_name='predictionpush')
    op.drop_index(op.f('ix_predictionpush_error'), table_name='predictionpush')
    op.drop_index(op.f('ix_predictionpush_datasource_id'), table_name='predictionpush')
    op.drop_index(op.f('ix_predictionpush_created'), table_name='predictionpush')
    op.drop_index(op.f('ix_predictionpush_completed_steps'), table_name='predictionpush')
    op.drop_table('predictionpush')
    # ### end Alembic commands ###
