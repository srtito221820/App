from datetime import date, datetime as _dt

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify)

from models import (db, Proveedor, CuentaCorriente, MovimientoTela,
                    NotaCredito, NotaCreditoItem)
from money import D, ZERO, parse_money, parse_kg
from utils import registrar_auditoria

bp = Blueprint('notas_credito', __name__)


@bp.route('/notas-credito')
def notas_credito_list():
    proveedor_id = request.args.get('proveedor_id', type=int)
    q = NotaCredito.query
    if proveedor_id:
        q = q.filter(NotaCredito.proveedor_id == proveedor_id)
    ncs = q.order_by(NotaCredito.fecha.desc(), NotaCredito.id.desc()).all()

    devoluciones_pendientes = MovimientoTela.query.filter(
        MovimientoTela.movimiento == 'Devolucion'
    ).filter(
        ~MovimientoTela.id.in_(db.session.query(NotaCreditoItem.movimiento_id))
    ).order_by(MovimientoTela.fecha.desc()).all()

    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    return render_template('notas_credito/list.html',
                           ncs=ncs,
                           devoluciones_pendientes=devoluciones_pendientes,
                           proveedores=proveedores,
                           proveedor_id=proveedor_id)


@bp.route('/notas-credito/nuevo', methods=['GET', 'POST'])
def nota_credito_nuevo():
    if request.method == 'POST':
        try:
            proveedor_id = request.form.get('proveedor_id', type=int)
            numero = request.form.get('numero', '').strip()
            fecha_str = request.form.get('fecha') or date.today().isoformat()
            cuenta = request.form.get('cuenta', '').strip() or None
            monto_total = request.form.get('monto_total', type=float) or 0
            iva = request.form.get('iva', type=float) or 0
            monto_con_iva = request.form.get('monto_con_iva', type=float) or (monto_total + iva)
            obs = request.form.get('observaciones', '').strip() or None

            if not proveedor_id or not numero:
                flash('Proveedor y numero son obligatorios.', 'danger')
                raise ValueError('Datos invalidos')

            nc = NotaCredito(
                numero=numero,
                fecha=_dt.strptime(fecha_str, '%Y-%m-%d').date(),
                proveedor_id=proveedor_id,
                cuenta=cuenta,
                monto_total=monto_total,
                iva=iva,
                monto_con_iva=monto_con_iva,
                observaciones=obs,
            )
            db.session.add(nc)
            db.session.flush()

            mov_ids = request.form.getlist('mov_id[]')
            kg_ac_list = request.form.getlist('kg_aceptado[]')
            monto_ac_list = request.form.getlist('monto_aceptado[]')
            obs_item_list = request.form.getlist('obs_item[]')

            for i, mid in enumerate(mov_ids):
                mid_i = int(mid) if mid else None
                if not mid_i:
                    continue
                kg_ac = parse_kg(kg_ac_list[i]) if i < len(kg_ac_list) else ZERO
                monto_ac = parse_money(monto_ac_list[i]) if i < len(monto_ac_list) else ZERO
                obs_it = obs_item_list[i] if i < len(obs_item_list) else None
                item = NotaCreditoItem(
                    nc_id=nc.id,
                    movimiento_id=mid_i,
                    kg_aceptados=kg_ac,
                    monto_aceptado=monto_ac,
                    observaciones=obs_it,
                )
                db.session.add(item)
                mov = db.session.get(MovimientoTela, mid_i)
                if mov:
                    mov.estado = 'NC Aplicada'

            cc = CuentaCorriente(
                fecha=nc.fecha,
                proveedor_id=nc.proveedor_id,
                cuenta=nc.cuenta,
                tipo='Nota de Credito',
                numero_comprobante=nc.numero,
                descripcion=f'Nota de Credito {nc.numero}' + (f' - {obs}' if obs else ''),
                debe=0,
                haber=nc.monto_con_iva or 0,
            )
            db.session.add(cc)
            db.session.flush()
            nc.cc_id = cc.id

            registrar_auditoria('CREAR', 'NotaCredito', nc.id, f'NC {nc.numero}')
            db.session.commit()
            flash(f'NC {nc.numero} creada y vinculada.', 'success')
            return redirect(url_for('notas_credito.nota_credito_detalle', id=nc.id))
        except ValueError:
            pass
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')

    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    proveedor_pre = request.args.get('proveedor_id', type=int)
    mov_pre_ids = request.args.getlist('mov_id')

    devoluciones = []
    if proveedor_pre:
        q = MovimientoTela.query.filter(
            MovimientoTela.proveedor_id == proveedor_pre,
            MovimientoTela.movimiento == 'Devolucion',
        ).filter(
            ~MovimientoTela.id.in_(db.session.query(NotaCreditoItem.movimiento_id))
        ).order_by(MovimientoTela.fecha.desc())
        devoluciones = q.all()

    return render_template('notas_credito/form.html',
                           nc=None, proveedores=proveedores,
                           proveedor_pre=proveedor_pre,
                           devoluciones=devoluciones,
                           mov_pre_ids=set(int(x) for x in mov_pre_ids if x))


@bp.route('/notas-credito/<int:id>')
def nota_credito_detalle(id):
    nc = NotaCredito.query.get_or_404(id)
    return render_template('notas_credito/detalle.html', nc=nc)


@bp.route('/notas-credito/<int:id>/editar', methods=['GET', 'POST'])
def nota_credito_editar(id):
    nc = NotaCredito.query.get_or_404(id)
    if request.method == 'POST':
        try:
            numero = request.form.get('numero', '').strip()
            fecha_str = request.form.get('fecha') or nc.fecha.isoformat()
            cuenta = request.form.get('cuenta', '').strip() or None
            monto_total = request.form.get('monto_total', type=float) or 0
            iva = request.form.get('iva', type=float) or 0
            monto_con_iva = request.form.get('monto_con_iva', type=float) or (monto_total + iva)
            obs = request.form.get('observaciones', '').strip() or None

            if not numero:
                flash('El numero es obligatorio.', 'danger')
                raise ValueError('Datos invalidos')

            nc.numero = numero
            nc.fecha = _dt.strptime(fecha_str, '%Y-%m-%d').date()
            nc.cuenta = cuenta
            nc.monto_total = monto_total
            nc.iva = iva
            nc.monto_con_iva = monto_con_iva
            nc.observaciones = obs

            if nc.cc_id:
                cc = db.session.get(CuentaCorriente, nc.cc_id)
                if cc:
                    cc.fecha = nc.fecha
                    cc.cuenta = nc.cuenta
                    cc.numero_comprobante = nc.numero
                    cc.descripcion = f'Nota de Credito {nc.numero}' + (f' - {obs}' if obs else '')
                    cc.haber = nc.monto_con_iva or 0

            registrar_auditoria('EDITAR', 'NotaCredito', nc.id, f'NC {nc.numero}')
            db.session.commit()
            flash(f'NC {nc.numero} actualizada.', 'success')
            return redirect(url_for('notas_credito.nota_credito_detalle', id=nc.id))
        except ValueError:
            pass
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')

    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    return render_template('notas_credito/form.html',
                           nc=nc, proveedores=proveedores,
                           proveedor_pre=nc.proveedor_id,
                           devoluciones=[],
                           mov_pre_ids=set())


@bp.route('/notas-credito/<int:id>/eliminar', methods=['POST'])
def nota_credito_eliminar(id):
    nc = NotaCredito.query.get_or_404(id)
    for item in nc.items:
        if item.movimiento:
            item.movimiento.estado = 'Pendiente NC'
    if nc.cc_id:
        cc = db.session.get(CuentaCorriente, nc.cc_id)
        if cc:
            db.session.delete(cc)
    registrar_auditoria('ELIMINAR', 'NotaCredito', nc.id, f'NC {nc.numero}')
    db.session.delete(nc)
    db.session.commit()
    flash('NC eliminada y CC revertida.', 'info')
    return redirect(url_for('notas_credito.notas_credito_list'))


@bp.route('/api/devoluciones-pendientes/<int:proveedor_id>')
def api_devoluciones_pendientes(proveedor_id):
    q = MovimientoTela.query.filter(
        MovimientoTela.proveedor_id == proveedor_id,
        MovimientoTela.movimiento == 'Devolucion',
    ).filter(
        ~MovimientoTela.id.in_(db.session.query(NotaCreditoItem.movimiento_id))
    ).order_by(MovimientoTela.fecha.desc())
    movs = q.all()
    return jsonify([{
        'id': m.id,
        'fecha': m.fecha.strftime('%d/%m/%Y'),
        'remito': m.remito_factura or '',
        'tipo_tela': m.tipo_tela or '',
        'color': m.color or '',
        'kg_reclamados': abs(m.cant_kg or 0),
        'piezas': abs(m.piezas or 0),
        'precio_sin_iva': m.precio_sin_iva or 0,
        'observaciones': m.observaciones or '',
    } for m in movs])
