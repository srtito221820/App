from flask import Blueprint, render_template, request

from models import (db, Proveedor, CuentaCorriente, MovimientoTela,
                    NotaCreditoItem)

bp = Blueprint('cuenta_corriente', __name__)


@bp.route('/cuenta-corriente')
def cuenta_corriente_list():
    proveedor_id = request.args.get('proveedor_id', type=int)
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    movimientos = []
    proveedor = None
    saldo_acumulado = []

    if proveedor_id:
        proveedor = db.session.get(Proveedor, proveedor_id)
        movimientos = CuentaCorriente.query.filter_by(
            proveedor_id=proveedor_id
        ).order_by(CuentaCorriente.fecha, CuentaCorriente.id).all()

        saldo = 0
        for m in movimientos:
            saldo += m.debe - m.haber
            saldo_acumulado.append(saldo)

    return render_template('cuenta_corriente/list.html',
                           proveedores=proveedores,
                           movimientos=movimientos,
                           proveedor=proveedor,
                           saldo_acumulado=saldo_acumulado,
                           proveedor_id=proveedor_id)


@bp.route('/cuenta-corriente-analitica/<int:proveedor_id>')
def cc_analitica(proveedor_id):
    proveedor = Proveedor.query.get_or_404(proveedor_id)
    cuenta_sel = request.args.get('cuenta', '').strip() or None

    q = CuentaCorriente.query.filter_by(proveedor_id=proveedor_id)
    if cuenta_sel:
        q = q.filter(CuentaCorriente.cuenta == cuenta_sel)
    movs = q.order_by(CuentaCorriente.fecha, CuentaCorriente.id).all()

    def clasif(cc):
        t = (cc.tipo or '').upper()
        if 'PAGO' in t or 'ANTICIPO' in t or 'RETENC' in t:
            return 'Pago'
        if 'NOTA DE CREDITO' in t or t == 'NC':
            return 'NC'
        if 'NOTA DE DEBITO' in t or t == 'ND':
            return 'ND'
        if 'FACTURA' in t:
            return 'Factura'
        d = (cc.descripcion or '').upper()
        if 'PAGO' in d or 'ANTICIPO' in d:
            return 'Pago'
        if 'NOTA DE CREDITO' in d or d.startswith('NC'):
            return 'NC'
        if 'NOTA DE DEBITO' in d or d.startswith('ND'):
            return 'ND'
        if 'FACTURA' in d or d.startswith('FC') or d.startswith('FA'):
            return 'Factura'
        return 'Otro'

    lineas = []
    saldo_acum = 0
    total_facturado = 0
    total_nc = 0
    total_nd = 0
    total_pagos = 0
    for cc in movs:
        saldo_acum += (cc.debe or 0) - (cc.haber or 0)
        t = clasif(cc)
        if t == 'Factura':
            total_facturado += (cc.debe or 0)
        elif t == 'NC':
            total_nc += (cc.haber or 0)
        elif t == 'ND':
            total_nd += (cc.debe or 0)
        elif t == 'Pago':
            total_pagos += (cc.haber or 0)
        lineas.append({'cc': cc, 'tipo': t, 'saldo': saldo_acum})

    saldo_real = saldo_acum

    q_dev = MovimientoTela.query.filter(
        MovimientoTela.proveedor_id == proveedor_id,
        MovimientoTela.movimiento == 'Devolucion',
    ).filter(
        ~MovimientoTela.id.in_(db.session.query(NotaCreditoItem.movimiento_id))
    )
    if cuenta_sel:
        q_dev = q_dev.filter(MovimientoTela.cuenta == cuenta_sel)
    devs_pendientes = q_dev.all()
    kg_pendientes = sum(abs(m.cant_kg or 0) for m in devs_pendientes)
    monto_pendiente_estimado = sum(
        abs(m.cant_kg or 0) * (m.precio_sin_iva or 0) * 1.21
        for m in devs_pendientes
    )

    saldo_estimativo = saldo_real - monto_pendiente_estimado

    return render_template('cuenta_corriente/analitica.html',
                           proveedor=proveedor,
                           lineas=lineas,
                           saldo_real=saldo_real,
                           saldo_estimativo=saldo_estimativo,
                           total_facturado=total_facturado,
                           total_nc=total_nc,
                           total_nd=total_nd,
                           total_pagos=total_pagos,
                           devs_pendientes=devs_pendientes,
                           kg_pendientes=kg_pendientes,
                           monto_pendiente_estimado=monto_pendiente_estimado,
                           cuenta_sel=cuenta_sel)
