from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from models import Proveedor, CuentaCorriente, PagoFactura

bp = Blueprint('facturas', __name__)


@bp.route('/facturas')
def facturas_list():
    proveedor_id = request.args.get('proveedor_id', type=int)
    estado = request.args.get('estado', '')
    tipo = request.args.get('tipo', '')
    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')

    q = CuentaCorriente.query.filter(CuentaCorriente.tipo.in_(['Factura', 'Nota de Debito']))
    if proveedor_id:
        q = q.filter_by(proveedor_id=proveedor_id)
    if tipo:
        q = q.filter_by(tipo=tipo)
    if desde:
        q = q.filter(CuentaCorriente.fecha >= date.fromisoformat(desde))
    if hasta:
        q = q.filter(CuentaCorriente.fecha <= date.fromisoformat(hasta))

    facturas = q.order_by(CuentaCorriente.fecha.desc(), CuentaCorriente.id.desc()).all()

    if estado:
        facturas = [f for f in facturas if f.estado_pago() == estado]

    total_pendiente = sum(f.saldo_pendiente() for f in facturas)
    total_facturado = sum(f.debe or 0 for f in facturas)

    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    return render_template('facturas/list.html',
                           facturas=facturas, proveedores=proveedores,
                           total_pendiente=total_pendiente,
                           total_facturado=total_facturado,
                           filtros={'proveedor_id': proveedor_id, 'estado': estado,
                                    'tipo': tipo, 'desde': desde, 'hasta': hasta})


@bp.route('/facturas/<int:id>')
def factura_detalle(id):
    f = CuentaCorriente.query.get_or_404(id)
    if not f.es_pagable():
        flash('Esta entrada no es una factura.', 'warning')
        return redirect(url_for('facturas.facturas_list'))
    aplicaciones = PagoFactura.query.filter_by(cc_factura_id=id).all()
    return render_template('facturas/detalle.html', f=f, aplicaciones=aplicaciones)


@bp.route('/api/proveedor/<int:id>/facturas-pendientes')
def api_facturas_pendientes(id):
    facturas = CuentaCorriente.query.filter(
        CuentaCorriente.proveedor_id == id,
        CuentaCorriente.tipo.in_(['Factura', 'Nota de Debito'])
    ).order_by(CuentaCorriente.fecha).all()
    data = []
    for f in facturas:
        saldo = f.saldo_pendiente()
        if saldo > 0.01:
            data.append({
                'id': f.id,
                'fecha': f.fecha.strftime('%d/%m/%Y'),
                'tipo': f.tipo,
                'numero': f.numero_comprobante or '',
                'descripcion': f.descripcion or '',
                'cuenta': f.cuenta or '',
                'total': f.debe or 0,
                'aplicado': f.monto_aplicado(),
                'saldo': saldo,
            })
    return jsonify(data)
