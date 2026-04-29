"""anticipo neto e iva alicuota

Revision ID: d4f1a2b8c901
Revises: c3428470c32b
Create Date: 2026-04-29 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4f1a2b8c901'
down_revision = 'c3428470c32b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('anticipos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('neto', sa.Numeric(precision=14, scale=2), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('iva_alicuota', sa.Numeric(precision=8, scale=4), nullable=True, server_default='21'))

    # Backfill: para anticipos viejos cargados como bruto a 21% IVA,
    # calcular el neto = monto / 1.21. Si monto es 0 o null, queda en 0.
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE anticipos SET neto = ROUND(COALESCE(monto, 0) / 1.21, 2), "
        "iva_alicuota = 21 WHERE neto IS NULL OR neto = 0"
    ))


def downgrade():
    with op.batch_alter_table('anticipos', schema=None) as batch_op:
        batch_op.drop_column('iva_alicuota')
        batch_op.drop_column('neto')
