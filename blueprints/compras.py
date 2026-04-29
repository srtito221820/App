from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash

from models import (db, Proveedor, CuentaCorriente, FacturaCompra, FacturaCompraItem,
                    CATEGORIAS_COMPRA, TIPOS_COMPROBANTE_COMPRA,
                    TIPOS_DOCUMENTO_COMPRA, TIPO_DOCUMENTO_LABELS, PagoFactura)
from money import D, ZERO, q2, parse_money
from utils import registrar_auditoria

bp = Blueprint('compras', __name__, url_prefix='/compras')


def _parse_float(v, default=ZERO):
    """Parser tolerante a formularios. Devuelve Decimal cuantizado a 2 decimales.

    Nombre conservado por compatibilidad con el resto del modulo.
    """
    if v in (None, ''):
        return D(default)
    return parse_money(v, D(default))


def _parse_int(v, default=0):
    try:
        return int(v) if v not in (None, '') else default
    except (ValueError, TypeError):
        return default


def _recalcular_totales(factura):
    """Recalcula los totales de cabecera a partir de los items + percepciones."""
    neto_grav = ZERO
    iva_total = ZERO
    imp_internos_total = ZERO
    for it in factura.items:
        # Si la alicuota es 0, el subtotal se considera no gravado? Decision:
        # los items se consideran siempre "gravados" (el neto_no_gravado se ingresa a mano).
        neto_grav += D(it.subtotal_neto)
        iva_total += D(it.iva_monto)
        imp_internos_total += D(it.imp_internos)
    factura.neto_gravado = q2(neto_grav)
    factura.iva_total = q2(iva_total)
    factura.imp_internos_total = q2(imp_internos_total)
    factura.total = q2(
        D(factura.neto_gravado)
        + D(factura.neto_no_gravado)
        + D(factura.iva_total)
        + D(factura.imp_internos_total)
        + D(factura.percep_iva)
        + D(factura.percep_iibb)
        + D(factura.otros_impuestos)
    )


def _sincronizar_cc(factura):
    """Crea o actualiza el asiento en CuentaCorriente para esta factura/NC/ND."""
    tipo_cc = factura.tipo_cc()
    total = D(factura.total)
    if factura.es_nota_credito():
        debe, haber = ZERO, total
        prefix = 'NC compras'
    elif factura.es_nota_debito():
        debe, haber = total, ZERO
        prefix = 'ND compras'
    else:
        debe, haber = total, ZERO
        prefix = 'Factura compras'
    descripcion = f'{prefix}: ' + ', '.join(factura.categorias_resumen() or ['(sin items)'])
    if factura.cc_id:
        cc = db.session.get(CuentaCorriente,factura.cc_id)
        if cc:
            cc.fecha = factura.fecha
            cc.tipo = tipo_cc
            cc.numero_comprobante = factura.numero_completo()
            cc.descripcion = descripcion
            cc.cuenta = factura.cuenta or ''
            cc.debe = debe
            cc.haber = haber
            return cc
    cc = CuentaCorriente(
        fecha=factura.fecha,
        proveedor_id=factura.proveedor_id,
        tipo=tipo_cc,
        numero_comprobante=factura.numero_completo(),
        descripcion=descripcion,
        cuenta=factura.cuenta or '',
        debe=debe,
        haber=haber,
    )
    db.session.add(cc)
    db.session.flush()
    factura.cc_id = cc.id
    return cc


def _leer_items_del_form():
    """Toma los arrays del form y devuelve una lista de dicts por linea."""
    descripciones = request.form.getlist('item_descripcion[]')
    cantidades = request.form.getlist('item_cantidad[]')
    costos = request.form.getlist('item_costo[]')
    subtotales = request.form.getlist('item_subtotal[]')
    alicuotas = request.form.getlist('item_iva_alicuota[]')
    iva_montos = request.form.getlist('item_iva_monto[]')
    internos = request.form.getlist('item_imp_internos[]')
    categorias = request.form.getlist('item_categoria[]')
    observaciones = request.form.getlist('item_observaciones[]')

    n = len(descripciones)
    items = []
    for i in range(n):
        desc = (descripciones[i] if i < len(descripciones) else '').strip()
        cat = (categorias[i] if i < len(categorias) else '').strip()
        cant = _parse_float(cantidades[i] if i < len(cantidades) else 0, ZERO)
        costo = _parse_float(costos[i] if i < len(costos) else 0, ZERO)
        subtotal = _parse_float(subtotales[i] if i < len(subtotales) else 0, ZERO)
        if subtotal <= 0:
            subtotal = q2(cant * costo)
        alic = _parse_float(alicuotas[i] if i < len(alicuotas) else 0, ZERO)
        iva_m = _parse_float(iva_montos[i] if i < len(iva_montos) else 0, ZERO)
        if iva_m <= 0 and alic > 0:
            iva_m = q2(subtotal * alic / D(100))
        internos_m = _parse_float(internos[i] if i < len(internos) else 0, ZERO)
        obs = (observaciones[i] if i < len(observaciones) else '').strip()

        if not desc and subtotal <= 0:
            continue
        items.append({
            'descripcion': desc,
            'cantidad': cant,
            'costo_unitario': costo,
            'subtotal_neto': subtotal,
            'iva_alicuota': alic,
            'iva_monto': iva_m,
            'imp_internos': internos_m,
            'categoria': cat,
            'observaciones': obs,
        })
    return items


def _validar_items(items):
    """Devuelve mensaje de error o None si OK."""
    if not items:
        return 'Debe cargar al menos una linea de detalle.'
    for i, it in enumerate(items, start=1):
        if not it['descripcion']:
            return f'Linea {i}: falta descripcion.'
        if not it['categoria']:
            return f'Linea {i}: debe seleccionar una categoria.'
        if it['categoria'] not in CATEGORIAS_COMPRA:
            return f'Linea {i}: categoria "{it["categoria"]}" no es valida.'
        if it['subtotal_neto'] < 0:
            return f'Linea {i}: el subtotal no puede ser negativo.'
    return None


@bp.route('')
def compras_list():
    proveedor_id = request.args.get('proveedor_id', type=int)
    categoria = request.args.get('categoria', '')
    estado = request.args.get('estado', '')
    tipo_documento = request.args.get('tipo_documento', '')
    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')

    q = FacturaCompra.query
    if proveedor_id:
        q = q.filter_by(proveedor_id=proveedor_id)
    if tipo_documento and tipo_documento in TIPOS_DOCUMENTO_COMPRA:
        q = q.filter(FacturaCompra.tipo_documento == tipo_documento)
    if desde:
        try:
            q = q.filter(FacturaCompra.fecha >= date.fromisoformat(desde))
        except ValueError:
            pass
    if hasta:
        try:
            q = q.filter(FacturaCompra.fecha <= date.fromisoformat(hasta))
        except ValueError:
            pass
    if categoria:
        q = q.join(FacturaCompraItem).filter(FacturaCompraItem.categoria == categoria)

    facturas = q.order_by(FacturaCompra.fecha.desc(), FacturaCompra.id.desc()).all()

    # Filtro por estado requiere calcular saldo via CC. Solo aplica a docs pagables.
    if estado:
        def _estado(f):
            if f.es_nota_credito():
                return 'Credito'
            if not f.cc_id:
                return 'Pendiente'
            cc = db.session.get(CuentaCorriente,f.cc_id)
            return cc.estado_pago() if cc else 'Pendiente'
        facturas = [f for f in facturas if _estado(f) == estado]

    total_facturado = sum(
        (f.total or 0) for f in facturas if not f.es_nota_credito()
    )
    total_creditos = sum((f.total or 0) for f in facturas if f.es_nota_credito())
    total_neto = sum(
        (f.neto_gravado or 0) * (-1 if f.es_nota_credito() else 1) for f in facturas
    )
    total_pendiente = 0.0
    for f in facturas:
        if f.es_nota_credito() or not f.cc_id:
            continue
        cc = db.session.get(CuentaCorriente,f.cc_id)
        if cc:
            total_pendiente += cc.saldo_pendiente()

    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    return render_template('compras/list.html',
                           facturas=facturas,
                           proveedores=proveedores,
                           categorias=CATEGORIAS_COMPRA,
                           tipos_documento=TIPOS_DOCUMENTO_COMPRA,
                           tipos_documento_labels=TIPO_DOCUMENTO_LABELS,
                           total_facturado=total_facturado,
                           total_creditos=total_creditos,
                           total_neto=total_neto,
                           total_pendiente=total_pendiente,
                           filtros={
                               'proveedor_id': proveedor_id,
                               'categoria': categoria,
                               'estado': estado,
                               'tipo_documento': tipo_documento,
                               'desde': desde,
                               'hasta': hasta,
                           })


@bp.route('/nueva', methods=['GET', 'POST'])
def compra_nueva():
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    tipo_doc_pre = request.args.get('tipo_documento', 'Factura')
    if tipo_doc_pre not in TIPOS_DOCUMENTO_COMPRA:
        tipo_doc_pre = 'Factura'

    if request.method == 'POST':
        try:
            proveedor_id = int(request.form['proveedor_id'])
            fecha = date.fromisoformat(request.form['fecha'])
        except (KeyError, ValueError):
            flash('Proveedor y fecha son obligatorios.', 'danger')
            return redirect(url_for('compras.compra_nueva'))

        tipo_doc = request.form.get('tipo_documento', 'Factura')
        if tipo_doc not in TIPOS_DOCUMENTO_COMPRA:
            tipo_doc = 'Factura'
        tipo_comp = request.form.get('tipo_comprobante', 'A')
        if tipo_comp not in TIPOS_COMPROBANTE_COMPRA:
            tipo_comp = 'A'
        punto_venta = request.form.get('punto_venta', '').strip()
        numero = request.form.get('numero', '').strip()
        cuenta = request.form.get('cuenta', '').strip()

        # Validacion de duplicados (mismo proveedor + tipo doc + tipo comp + PV + numero)
        if numero:
            dup = FacturaCompra.query.filter_by(
                proveedor_id=proveedor_id,
                tipo_documento=tipo_doc,
                tipo_comprobante=tipo_comp,
                punto_venta=punto_venta,
                numero=numero,
            ).first()
            if dup:
                etiqueta = TIPO_DOCUMENTO_LABELS.get(tipo_doc, tipo_doc)
                flash(f'Ya existe {etiqueta} {tipo_comp} {punto_venta}-{numero} '
                      f'para este proveedor.', 'danger')
                return redirect(url_for('compras.compra_nueva',
                                        tipo_documento=tipo_doc))

        percep_iva = _parse_float(request.form.get('percep_iva'), 0)
        percep_iibb = _parse_float(request.form.get('percep_iibb'), 0)
        otros_imp = _parse_float(request.form.get('otros_impuestos'), 0)
        neto_no_grav = _parse_float(request.form.get('neto_no_gravado'), 0)
        observaciones = request.form.get('observaciones', '').strip()

        items_data = _leer_items_del_form()
        err = _validar_items(items_data)
        if err:
            flash(err, 'danger')
            return redirect(url_for('compras.compra_nueva',
                                    tipo_documento=tipo_doc))

        factura = FacturaCompra(
            proveedor_id=proveedor_id,
            fecha=fecha,
            tipo_documento=tipo_doc,
            tipo_comprobante=tipo_comp,
            punto_venta=punto_venta,
            numero=numero,
            cuenta=cuenta,
            neto_no_gravado=neto_no_grav,
            percep_iva=percep_iva,
            percep_iibb=percep_iibb,
            otros_impuestos=otros_imp,
            observaciones=observaciones,
        )
        db.session.add(factura)
        db.session.flush()

        for d in items_data:
            it = FacturaCompraItem(factura_id=factura.id, **d)
            db.session.add(it)
        db.session.flush()

        _recalcular_totales(factura)
        _sincronizar_cc(factura)

        etiqueta = factura.tipo_documento_label()
        registrar_auditoria('Crear', 'FacturaCompra', factura.id,
                            f'{etiqueta} {factura.numero_completo()} ${factura.total:.2f} '
                            f'(neto ${factura.neto_gravado:.2f})')
        db.session.commit()
        flash(f'{etiqueta} {factura.numero_completo()} registrada. '
              f'Total ${factura.total:,.2f}.', 'success')
        return redirect(url_for('compras.compra_detalle', id=factura.id))

    return render_template('compras/form.html',
                           factura=None,
                           proveedores=proveedores,
                           categorias=CATEGORIAS_COMPRA,
                           tipos_comprobante=TIPOS_COMPROBANTE_COMPRA,
                           tipos_documento=TIPOS_DOCUMENTO_COMPRA,
                           tipos_documento_labels=TIPO_DOCUMENTO_LABELS,
                           tipo_documento_pre=tipo_doc_pre,
                           fecha_default=date.today().isoformat())


@bp.route('/<int:id>')
def compra_detalle(id):
    factura = FacturaCompra.query.get_or_404(id)
    cc = db.session.get(CuentaCorriente,factura.cc_id) if factura.cc_id else None
    return render_template('compras/detalle.html', factura=factura, cc=cc)


@bp.route('/<int:id>/editar', methods=['GET', 'POST'])
def compra_editar(id):
    factura = FacturaCompra.query.get_or_404(id)
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    if factura.cc_id:
        cc = db.session.get(CuentaCorriente,factura.cc_id)
        if cc and cc.monto_aplicado() > 0.01:
            flash('No se puede editar: esta factura ya tiene pagos aplicados. '
                  'Eliminá primero el pago desde el módulo de Pagos.', 'danger')
            return redirect(url_for('compras.compra_detalle', id=id))

    if request.method == 'POST':
        try:
            factura.proveedor_id = int(request.form['proveedor_id'])
            factura.fecha = date.fromisoformat(request.form['fecha'])
        except (KeyError, ValueError):
            flash('Proveedor y fecha son obligatorios.', 'danger')
            return redirect(url_for('compras.compra_editar', id=id))

        tipo_doc = request.form.get('tipo_documento', factura.tipo_documento or 'Factura')
        if tipo_doc not in TIPOS_DOCUMENTO_COMPRA:
            tipo_doc = factura.tipo_documento or 'Factura'
        factura.tipo_documento = tipo_doc
        tipo_comp = request.form.get('tipo_comprobante', 'A')
        if tipo_comp not in TIPOS_COMPROBANTE_COMPRA:
            tipo_comp = 'A'
        factura.tipo_comprobante = tipo_comp
        factura.punto_venta = request.form.get('punto_venta', '').strip()
        factura.numero = request.form.get('numero', '').strip()
        factura.cuenta = request.form.get('cuenta', '').strip()
        factura.neto_no_gravado = _parse_float(request.form.get('neto_no_gravado'), 0)
        factura.percep_iva = _parse_float(request.form.get('percep_iva'), 0)
        factura.percep_iibb = _parse_float(request.form.get('percep_iibb'), 0)
        factura.otros_impuestos = _parse_float(request.form.get('otros_impuestos'), 0)
        factura.observaciones = request.form.get('observaciones', '').strip()

        items_data = _leer_items_del_form()
        err = _validar_items(items_data)
        if err:
            flash(err, 'danger')
            return redirect(url_for('compras.compra_editar', id=id))

        # Reemplazar items
        for it in factura.items.all():
            db.session.delete(it)
        db.session.flush()
        for d in items_data:
            it = FacturaCompraItem(factura_id=factura.id, **d)
            db.session.add(it)
        db.session.flush()

        _recalcular_totales(factura)
        _sincronizar_cc(factura)

        etiqueta = factura.tipo_documento_label()
        registrar_auditoria('Editar', 'FacturaCompra', factura.id,
                            f'{etiqueta} {factura.numero_completo()} ${factura.total:.2f}')
        db.session.commit()
        flash(f'{etiqueta} actualizada.', 'success')
        return redirect(url_for('compras.compra_detalle', id=factura.id))

    items_preload = [{
        'descripcion': it.descripcion,
        'cantidad': it.cantidad,
        'costo_unitario': it.costo_unitario,
        'subtotal_neto': it.subtotal_neto,
        'iva_alicuota': it.iva_alicuota,
        'iva_monto': it.iva_monto,
        'imp_internos': it.imp_internos,
        'categoria': it.categoria,
        'observaciones': it.observaciones or '',
    } for it in factura.items.all()]

    return render_template('compras/form.html',
                           factura=factura,
                           items_preload=items_preload,
                           proveedores=proveedores,
                           categorias=CATEGORIAS_COMPRA,
                           tipos_comprobante=TIPOS_COMPROBANTE_COMPRA,
                           tipos_documento=TIPOS_DOCUMENTO_COMPRA,
                           tipos_documento_labels=TIPO_DOCUMENTO_LABELS,
                           tipo_documento_pre=factura.tipo_documento or 'Factura',
                           fecha_default=factura.fecha.isoformat())


@bp.route('/<int:id>/eliminar', methods=['POST'])
def compra_eliminar(id):
    factura = FacturaCompra.query.get_or_404(id)

    if factura.cc_id:
        aplicados = PagoFactura.query.filter_by(cc_factura_id=factura.cc_id).all()
        if aplicados:
            nros = sorted({pf.pago.numero for pf in aplicados if pf.pago and pf.pago.numero})
            detalle = f' (Pago/s: {", ".join(nros)})' if nros else ''
            flash(f'No se puede eliminar: esta factura tiene pagos aplicados{detalle}. '
                  f'Eliminá primero el pago desde el módulo de Pagos.', 'danger')
            return redirect(url_for('compras.compra_detalle', id=id))

    etiqueta = factura.tipo_documento_label()
    registrar_auditoria('Eliminar', 'FacturaCompra', factura.id,
                        f'{etiqueta} {factura.numero_completo()} ${factura.total:.2f}')

    cc_id = factura.cc_id
    db.session.delete(factura)
    if cc_id:
        cc = db.session.get(CuentaCorriente,cc_id)
        if cc:
            db.session.delete(cc)
    db.session.commit()
    flash(f'{etiqueta} eliminada.', 'warning')
    return redirect(url_for('compras.compras_list'))
