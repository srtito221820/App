from flask import Blueprint, render_template, request, jsonify

from models import (db, Proveedor, Anticipo, MovimientoTela, Pedido,
                    CuentaAsignacion)
from money import parse_money, parse_kg
from utils import registrar_auditoria

bp = Blueprint('anticipos', __name__)


@bp.route('/anticipos')
def anticipos_list():
    estado = request.args.get('estado', '')
    proveedor_id = request.args.get('proveedor_id', type=int)

    query = Anticipo.query
    if estado:
        query = query.filter_by(estado=estado)
    if proveedor_id:
        query = query.filter_by(proveedor_id=proveedor_id)

    anticipos = query.order_by(Anticipo.fecha.desc()).all()
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    return render_template('anticipos/list.html',
                           anticipos=anticipos,
                           proveedores=proveedores,
                           filtros={'estado': estado, 'proveedor_id': proveedor_id})


@bp.route('/anticipos/<int:id>')
def anticipo_detalle(id):
    anticipo = Anticipo.query.get_or_404(id)
    movimientos = MovimientoTela.query.filter_by(anticipo_id=id).order_by(MovimientoTela.fecha).all()
    return render_template('anticipos/detalle.html', anticipo=anticipo, movimientos=movimientos)


@bp.route('/api/anticipos/<int:proveedor_id>')
def api_anticipos_proveedor(proveedor_id):
    proveedor = Proveedor.query.get_or_404(proveedor_id)
    anticipos = Anticipo.query.filter_by(proveedor_id=proveedor_id, estado='Abierto').all()
    return jsonify({
        'proveedor': {
            'id': proveedor.id,
            'nombre': proveedor.nombre,
            'cuit': proveedor.cuit or '',
            'usa_cuentas_asignacion': bool(proveedor.usa_cuentas_asignacion),
        },
        'anticipos': [{
            'id': a.id,
            'numero': a.numero,
            'monto': a.monto,
            'saldo_pendiente': a.saldo_pendiente(),
        } for a in anticipos],
    })


@bp.route('/api/pedidos/<int:anticipo_id>')
def api_pedidos_anticipo(anticipo_id):
    pedidos = Pedido.query.filter_by(anticipo_id=anticipo_id).filter(Pedido.estado != 'Completo').all()
    return jsonify([{
        'id': p.id,
        'numero': p.numero,
        'total_kg': p.total_kg(),
        'kg_entregados': p.kg_entregados(),
        'kg_pendientes': p.kg_pendientes(),
    } for p in pedidos])


@bp.route('/api/anticipo/<int:anticipo_id>/cuentas_asignacion')
def api_cuentas_asignacion(anticipo_id):
    cuentas = CuentaAsignacion.query.filter_by(anticipo_id=anticipo_id).order_by(CuentaAsignacion.numero).all()
    return jsonify([{
        'id': ca.id,
        'numero': ca.numero,
        'tipo_tela': ca.tipo_tela or '',
        'cant_kg': ca.cant_kg,
        'monto': ca.monto,
        'kg_entregados': ca.kg_entregados(),
        'kg_pendientes': ca.kg_pendientes(),
        'valor_entregado': ca.valor_entregado(),
        'saldo_pendiente': ca.saldo_pendiente(),
    } for ca in cuentas])


@bp.route('/api/anticipo/<int:anticipo_id>/cuentas_asignacion', methods=['POST'])
def api_cuentas_asignacion_crear(anticipo_id):
    anticipo = Anticipo.query.get_or_404(anticipo_id)
    numero = request.form.get('numero', '').strip()
    tipo_tela = request.form.get('tipo_tela', '').strip()
    cant_kg = parse_kg(request.form.get('cant_kg'))
    monto = parse_money(request.form.get('monto'))

    if not numero:
        return jsonify({'error': 'El numero de cuenta es obligatorio.'}), 400

    dup = CuentaAsignacion.query.filter_by(anticipo_id=anticipo_id, numero=numero).first()
    if dup:
        return jsonify({'error': f'Ya existe la cuenta "{numero}" en este anticipo.'}), 400

    cuentas_existentes = CuentaAsignacion.query.filter_by(anticipo_id=anticipo_id).all()
    total_kg_asig = sum(c.cant_kg for c in cuentas_existentes) + cant_kg
    total_monto_asig = sum(c.monto for c in cuentas_existentes) + monto
    if anticipo.cant_kg and total_kg_asig > anticipo.cant_kg:
        return jsonify({'error': f'Se exceden los kg del anticipo. Disponible: {anticipo.cant_kg - sum(c.cant_kg for c in cuentas_existentes):.2f} kg'}), 400
    if anticipo.monto and total_monto_asig > anticipo.monto:
        return jsonify({'error': f'Se excede el monto del anticipo. Disponible: ${anticipo.monto - sum(c.monto for c in cuentas_existentes):,.2f}'}), 400

    ca = CuentaAsignacion(
        anticipo_id=anticipo_id, numero=numero,
        tipo_tela=tipo_tela, cant_kg=cant_kg, monto=monto
    )
    db.session.add(ca)
    registrar_auditoria('Crear', 'CuentaAsignacion', ca.id, f'Cuenta {numero} en anticipo {anticipo.numero}')
    db.session.commit()
    return jsonify({'ok': True, 'id': ca.id})


@bp.route('/api/cuentas_asignacion/<int:cuenta_id>/eliminar', methods=['POST'])
def api_cuentas_asignacion_eliminar(cuenta_id):
    ca = CuentaAsignacion.query.get_or_404(cuenta_id)
    if ca.movimientos.count() > 0:
        return jsonify({'error': f'No se puede eliminar: tiene {ca.movimientos.count()} movimiento(s) vinculado(s).'}), 400
    registrar_auditoria('Eliminar', 'CuentaAsignacion', ca.id, f'Cuenta {ca.numero}')
    db.session.delete(ca)
    db.session.commit()
    return jsonify({'ok': True})
