from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy.orm import joinedload

from models import (db, Proveedor, CuentaCorriente, Pago, PagoFactura,
                    ConceptoRetencionGanancias, RetencionGanancias)
from money import D, ZERO, parse_money
from retenciones import (AGENTES_RETENCION, agente_por_codigo, calcular_retencion,
                         base_imponible_factura)
from utils import registrar_auditoria

bp = Blueprint('pagos', __name__, url_prefix='/pagos')


def _formatear_numero_pago(pago_id):
    """OP-NNNNN derivado del id ya asignado por la DB.

    Antes se calculaba MAX(id)+1 antes del INSERT, lo que abria una race
    condition con dos pagos creandose en paralelo (ambos leian el mismo MAX
    y generaban el mismo OP-XXXXX). Ahora se llama post-flush con el id real.
    """
    return f'OP-{pago_id:05d}'


@bp.route('')
def pagos_list():
    proveedor_id = request.args.get('proveedor_id', type=int)
    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')
    agente = request.args.get('agente', '')
    page = request.args.get('page', 1, type=int)

    q = Pago.query
    if proveedor_id:
        q = q.filter_by(proveedor_id=proveedor_id)
    if agente:
        q = q.filter_by(agente_codigo=agente)
    if desde:
        q = q.filter(Pago.fecha >= date.fromisoformat(desde))
    if hasta:
        q = q.filter(Pago.fecha <= date.fromisoformat(hasta))

    # Totales agregados sobre TODO el filtro (no solo la pagina visible).
    sub = q.with_entities(
        Pago.monto_bruto, Pago.total_retenciones, Pago.monto_neto
    ).subquery()
    totales = db.session.query(
        db.func.coalesce(db.func.sum(sub.c.monto_bruto), 0),
        db.func.coalesce(db.func.sum(sub.c.total_retenciones), 0),
        db.func.coalesce(db.func.sum(sub.c.monto_neto), 0),
    ).one()
    total_bruto, total_retenciones, total_neto = totales

    pagos = q.options(joinedload(Pago.proveedor)).order_by(
        Pago.fecha.desc(), Pago.id.desc()
    ).paginate(page=page, per_page=50, error_out=False)
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    return render_template('pagos/list.html',
                           pagos=pagos, proveedores=proveedores,
                           total_bruto=total_bruto,
                           total_retenciones=total_retenciones,
                           total_neto=total_neto,
                           filtros={'proveedor_id': proveedor_id, 'desde': desde,
                                    'hasta': hasta, 'agente': agente},
                           agentes=AGENTES_RETENCION)


@bp.route('/nuevo', methods=['GET', 'POST'])
def pago_nuevo():
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    conceptos = ConceptoRetencionGanancias.query.filter_by(activo=True).order_by(ConceptoRetencionGanancias.codigo).all()

    if request.method == 'POST':
        proveedor_id = int(request.form['proveedor_id'])
        fecha = date.fromisoformat(request.form['fecha'])
        agente_cod = request.form.get('agente_codigo', 'JUMAF')
        medio_pago = request.form.get('medio_pago', '')
        referencia = request.form.get('referencia', '')
        observaciones = request.form.get('observaciones', '')
        cuenta = request.form.get('cuenta', '')
        aplicar_ret = bool(request.form.get('aplicar_retencion'))
        concepto_id = request.form.get('concepto_retencion_id') or None

        factura_ids = request.form.getlist('factura_ids[]')
        aplicaciones_datos = []
        total_bruto = ZERO
        base_imponible_total = ZERO  # suma de netos gravados (sujetos a retencion)
        for fid in factura_ids:
            fid_int = int(fid)
            monto = parse_money(request.form.get(f'monto_{fid_int}'))
            if monto <= 0:
                continue
            factura = db.session.get(CuentaCorriente, fid_int)
            if not factura or factura.proveedor_id != proveedor_id:
                continue
            if not factura.es_aplicable():
                continue
            saldo = D(factura.saldo_pendiente())
            if monto > saldo + D('0.01'):
                flash(f'El monto aplicado a {factura.numero_comprobante} supera el saldo pendiente.', 'danger')
                return redirect(url_for('pagos.pago_nuevo', proveedor_id=proveedor_id))
            signo = -1 if factura.es_credito() else 1
            aplicaciones_datos.append((factura, monto))
            total_bruto += signo * monto
            base_imponible_total += signo * D(base_imponible_factura(factura, monto))

        if total_bruto <= 0:
            flash('El total bruto a pagar debe ser mayor a 0. Revisa la combinacion de facturas y notas de credito.', 'danger')
            return redirect(url_for('pagos.pago_nuevo', proveedor_id=proveedor_id))
        # No tiene sentido una base imponible negativa para retenciones.
        if base_imponible_total < 0:
            base_imponible_total = ZERO

        prov = db.session.get(Proveedor, proveedor_id)
        agente = agente_por_codigo(agente_cod)

        retencion_monto = ZERO
        resultado_ret = None
        concepto_ret = None
        if aplicar_ret:
            if concepto_id:
                concepto_ret = db.session.get(ConceptoRetencionGanancias, int(concepto_id))
            else:
                concepto_ret = prov.concepto_retencion
            if concepto_ret:
                # Retencion RG 830 se calcula sobre la base imponible (neto gravado),
                # no sobre el total con IVA/percepciones.
                resultado_ret = calcular_retencion(prov, concepto_ret, base_imponible_total, fecha)
                retencion_monto = D(resultado_ret['retencion'])

        total_neto = total_bruto - retencion_monto

        pago = Pago(
            numero='',  # se setea post-flush a partir del id real
            fecha=fecha,
            proveedor_id=proveedor_id,
            agente_codigo=agente_cod,
            agente_cuit=agente['cuit'],
            agente_nombre=agente['razon_social'],
            medio_pago=medio_pago,
            referencia=referencia,
            monto_bruto=total_bruto,
            total_retenciones=retencion_monto,
            monto_neto=total_neto,
            observaciones=observaciones,
        )
        db.session.add(pago)
        db.session.flush()
        pago.numero = _formatear_numero_pago(pago.id)

        desc_pago = f'Pago {pago.numero}'
        if medio_pago:
            desc_pago += f' ({medio_pago}{" " + referencia if referencia else ""})'
        cc_pago = CuentaCorriente(
            fecha=fecha, proveedor_id=proveedor_id,
            tipo='Pago', numero_comprobante=pago.numero,
            descripcion=desc_pago, cuenta=cuenta,
            debe=0, haber=total_neto,
        )
        db.session.add(cc_pago)
        db.session.flush()

        cc_ret = None
        if retencion_monto > 0:
            cc_ret = CuentaCorriente(
                fecha=fecha, proveedor_id=proveedor_id,
                tipo='Retencion Ganancias',
                numero_comprobante=f'RET-GAN-{pago.numero}',
                descripcion=f'Ret. Ganancias RG 830 s/{pago.numero} ({resultado_ret["alicuota_aplicada"]})',
                cuenta=cuenta, debe=0, haber=retencion_monto,
            )
            db.session.add(cc_ret)
            db.session.flush()

            ret = RetencionGanancias(
                fecha=fecha,
                mes_anio=fecha.strftime('%Y-%m'),
                proveedor_id=proveedor_id,
                concepto_id=concepto_ret.id,
                condicion=prov.condicion_ganancias,
                agente_cuit=agente['cuit'],
                agente_nombre=agente['razon_social'],
                numero_comprobante=pago.numero,
                monto_sujeto=total_bruto,
                base_imponible=base_imponible_total,
                base_acumulada=resultado_ret['base_acumulada'],
                mni_aplicado=resultado_ret['mni'],
                base_sujeta=resultado_ret['base_sujeta'],
                impuesto_teorico=resultado_ret['impuesto_teorico'],
                retenido_previo=resultado_ret['retenido_previo'],
                retencion=retencion_monto,
                monto_neto=total_neto,
                alicuota_aplicada=resultado_ret['alicuota_aplicada'],
                cc_pago_id=cc_pago.id,
                cc_retencion_id=cc_ret.id,
                pago_id=pago.id,
                observaciones=observaciones,
            )
            db.session.add(ret)

        for factura, monto in aplicaciones_datos:
            pf = PagoFactura(pago_id=pago.id, cc_factura_id=factura.id, monto_aplicado=monto)
            db.session.add(pf)

        registrar_auditoria('Crear', 'Pago', pago.id,
                            f'{pago.numero} ${total_bruto} (ret ${retencion_monto}) -> {prov.nombre}')
        db.session.commit()
        flash(f'Pago {pago.numero} registrado. Bruto ${total_bruto:,.2f} — Retencion ${retencion_monto:,.2f} — Neto ${total_neto:,.2f}', 'success')
        return redirect(url_for('pagos.pago_detalle', id=pago.id))

    prov_id = request.args.get('proveedor_id', type=int)
    proveedor = db.session.get(Proveedor, prov_id) if prov_id else None
    facturas_pendientes = []
    if proveedor:
        cc_list = CuentaCorriente.query.filter(
            CuentaCorriente.proveedor_id == proveedor.id,
            CuentaCorriente.tipo.in_(['Factura', 'Nota de Debito', 'Nota de Credito'])
        ).order_by(CuentaCorriente.fecha).all()
        facturas_pendientes = [f for f in cc_list if f.saldo_pendiente() > 0.01]
    return render_template('pagos/form.html',
                           proveedores=proveedores, proveedor=proveedor,
                           conceptos=conceptos,
                           facturas_pendientes=facturas_pendientes,
                           fecha_default=date.today().isoformat(),
                           agentes=AGENTES_RETENCION)


@bp.route('/<int:id>')
def pago_detalle(id):
    p = Pago.query.get_or_404(id)
    agente = None
    for a in AGENTES_RETENCION:
        if a['codigo'] == p.agente_codigo:
            agente = a
            break
    if not agente:
        agente = AGENTES_RETENCION[0]
    return render_template('pagos/detalle.html', p=p, agente=agente)


@bp.route('/<int:id>/imprimir')
def pago_imprimir(id):
    p = Pago.query.get_or_404(id)
    agente = None
    for a in AGENTES_RETENCION:
        if a['codigo'] == p.agente_codigo:
            agente = a
            break
    if not agente:
        agente = AGENTES_RETENCION[0]
    return render_template('pagos/orden_pago.html', p=p, agente=agente)


@bp.route('/<int:id>/eliminar', methods=['POST'])
def pago_eliminar(id):
    p = Pago.query.get_or_404(id)
    ccs_a_borrar = set()
    for ret in p.retenciones.all():
        if ret.cc_pago_id: ccs_a_borrar.add(ret.cc_pago_id)
        if ret.cc_retencion_id: ccs_a_borrar.add(ret.cc_retencion_id)
        db.session.delete(ret)
    for cc in CuentaCorriente.query.filter_by(numero_comprobante=p.numero,
                                               proveedor_id=p.proveedor_id).all():
        ccs_a_borrar.add(cc.id)
    for cc in CuentaCorriente.query.filter_by(numero_comprobante=f'RET-GAN-{p.numero}',
                                               proveedor_id=p.proveedor_id).all():
        ccs_a_borrar.add(cc.id)
    for cc_id in ccs_a_borrar:
        cc = db.session.get(CuentaCorriente, cc_id)
        if cc:
            db.session.delete(cc)
    registrar_auditoria('Eliminar', 'Pago', p.id,
                        f'Pago {p.numero} revertido (${p.monto_bruto})')
    db.session.delete(p)
    db.session.commit()
    flash(f'Pago {p.numero} eliminado y asientos CC revertidos.', 'warning')
    return redirect(url_for('pagos.pagos_list'))
