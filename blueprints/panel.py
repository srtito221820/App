from datetime import date

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash)
from sqlalchemy.orm import joinedload

from models import (db, Proveedor, CuentaCorriente, Anticipo, MovimientoTela,
                    Pedido, PedidoDetalle, CuentaAsignacion,
                    ConceptoRetencionGanancias, PagoFactura,
                    RetencionGanancias, NotaCredito)
from money import D, ZERO, q2, parse_money, parse_kg
from utils import registrar_auditoria, obtener_o_crear_partida

bp = Blueprint('panel', __name__)


@bp.route('/panel')
def panel():
    proveedor_id = request.args.get('proveedor_id', type=int)
    vista = request.args.get('vista', 'resumen')
    tipo_op = request.args.get('tipo_op', '')
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    proveedor = None
    cc_movimientos = []
    saldo_acumulado = []
    anticipos = []
    tela_movimientos = []
    cuentas_asignacion_resumen = []
    tela_cuentas_unicas = []
    tela_remitos_unicos = []
    tela_tipos_unicos = []
    tela_colores_unicos = []
    tela_cod_arts_unicos = []
    tela_temporadas_unicas = []

    if proveedor_id:
        proveedor = db.session.get(Proveedor, proveedor_id)

        cc_movimientos = CuentaCorriente.query.filter_by(
            proveedor_id=proveedor_id
        ).order_by(CuentaCorriente.fecha, CuentaCorriente.id).all()
        saldo = 0
        for m in cc_movimientos:
            saldo += m.debe - m.haber
            saldo_acumulado.append(saldo)

        anticipos = Anticipo.query.filter_by(
            proveedor_id=proveedor_id
        ).order_by(Anticipo.fecha.desc()).all()
        # Precarga totales agregados (evita N+1 al renderizar la grilla).
        Anticipo.precompute_totales(anticipos)

        if proveedor and proveedor.usa_cuentas_asignacion:
            anticipos_abiertos_ids = [a.id for a in anticipos if a.estado == 'Abierto']
            if anticipos_abiertos_ids:
                cuentas_asignacion_resumen = CuentaAsignacion.query.filter(
                    CuentaAsignacion.anticipo_id.in_(anticipos_abiertos_ids)
                ).order_by(CuentaAsignacion.anticipo_id, CuentaAsignacion.numero).all()
                CuentaAsignacion.precompute_totales(cuentas_asignacion_resumen)

        tela_q = MovimientoTela.query.filter_by(proveedor_id=proveedor_id)

        tela_fecha_desde = request.args.get('tela_fecha_desde', '')
        tela_fecha_hasta = request.args.get('tela_fecha_hasta', '')
        tela_cuenta = request.args.get('tela_cuenta', '')
        tela_remito = request.args.get('tela_remito', '')
        tela_tipo_tela = request.args.get('tela_tipo_tela', '')
        tela_color = request.args.get('tela_color', '')
        tela_cod_art = request.args.get('tela_cod_art', '')
        tela_temporada = request.args.get('tela_temporada', '')

        if tela_fecha_desde:
            tela_q = tela_q.filter(MovimientoTela.fecha >= date.fromisoformat(tela_fecha_desde))
        if tela_fecha_hasta:
            tela_q = tela_q.filter(MovimientoTela.fecha <= date.fromisoformat(tela_fecha_hasta))
        if tela_cuenta:
            tela_q = tela_q.filter(MovimientoTela.cuenta == tela_cuenta)
        if tela_remito:
            tela_q = tela_q.filter(MovimientoTela.remito_factura == tela_remito)
        if tela_tipo_tela:
            tela_q = tela_q.filter(MovimientoTela.tipo_tela == tela_tipo_tela)
        if tela_color:
            tela_q = tela_q.filter(MovimientoTela.color == tela_color)
        if tela_cod_art:
            tela_q = tela_q.filter(MovimientoTela.cod_art == tela_cod_art)
        if tela_temporada:
            tela_q = tela_q.filter(MovimientoTela.temporada == tela_temporada)

        tela_movimientos = tela_q.options(
            joinedload(MovimientoTela.anticipo),
            joinedload(MovimientoTela.pedido),
        ).order_by(MovimientoTela.fecha.desc()).limit(200).all()

        # Una sola query para los 6 valores distintos. Antes eran 6 round-trips
        # con SELECT DISTINCT separados; ahora se trae una grilla unica y se
        # construyen los sets en Python (la cardinalidad por proveedor es chica).
        cols_filtros = (
            MovimientoTela.cuenta, MovimientoTela.remito_factura,
            MovimientoTela.tipo_tela, MovimientoTela.color,
            MovimientoTela.cod_art, MovimientoTela.temporada,
        )
        rows_filtros = db.session.query(*cols_filtros).filter_by(
            proveedor_id=proveedor_id
        ).distinct().all()
        s_cuenta, s_remito, s_tipo, s_color, s_codart, s_temp = (set() for _ in range(6))
        for r in rows_filtros:
            if r[0]: s_cuenta.add(r[0])
            if r[1]: s_remito.add(r[1])
            if r[2]: s_tipo.add(r[2])
            if r[3]: s_color.add(r[3])
            if r[4]: s_codart.add(r[4])
            if r[5]: s_temp.add(r[5])
        tela_cuentas_unicas = sorted(s_cuenta)
        tela_remitos_unicos = sorted(s_remito)
        tela_tipos_unicos = sorted(s_tipo)
        tela_colores_unicos = sorted(s_color)
        tela_cod_arts_unicos = sorted(s_codart)
        tela_temporadas_unicas = sorted(s_temp)

    conceptos_retencion = ConceptoRetencionGanancias.query.filter_by(activo=True).order_by(ConceptoRetencionGanancias.codigo).all()
    return render_template('panel/index.html',
                           proveedores=proveedores,
                           proveedor=proveedor,
                           proveedor_id=proveedor_id,
                           vista=vista,
                           tipo_op=tipo_op,
                           conceptos_retencion=conceptos_retencion,
                           cc_movimientos=cc_movimientos,
                           saldo_acumulado=saldo_acumulado,
                           anticipos=anticipos,
                           tela_movimientos=tela_movimientos,
                           tela_cuentas_unicas=tela_cuentas_unicas,
                           tela_remitos_unicos=tela_remitos_unicos,
                           tela_tipos_unicos=tela_tipos_unicos,
                           tela_colores_unicos=tela_colores_unicos,
                           tela_cod_arts_unicos=tela_cod_arts_unicos,
                           tela_temporadas_unicas=tela_temporadas_unicas,
                           cuentas_asignacion_resumen=cuentas_asignacion_resumen,
                           tela_filtros={
                               'fecha_desde': request.args.get('tela_fecha_desde', ''),
                               'fecha_hasta': request.args.get('tela_fecha_hasta', ''),
                               'cuenta': request.args.get('tela_cuenta', ''),
                               'remito': request.args.get('tela_remito', ''),
                               'tipo_tela': request.args.get('tela_tipo_tela', ''),
                               'color': request.args.get('tela_color', ''),
                               'cod_art': request.args.get('tela_cod_art', ''),
                               'temporada': request.args.get('tela_temporada', ''),
                           })


@bp.route('/panel/operacion', methods=['POST'])
def panel_operacion():
    """Formulario unificado: segun tipo_operacion dispara a CC, Stock, Anticipos."""
    proveedor_id = int(request.form['proveedor_id'])
    tipo_op = request.form['tipo_operacion']

    fecha_str = request.form['fecha']
    try:
        fecha = date.fromisoformat(fecha_str)
        if fecha.year > 2100 or fecha.year < 2000:
            flash(f'Fecha invalida: {fecha_str}. Verifica el año.', 'danger')
            return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))
    except (ValueError, TypeError):
        flash(f'Fecha invalida: {fecha_str}', 'danger')
        return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))
    nro_comprobante = request.form.get('nro_comprobante', '')
    observaciones = request.form.get('observaciones', '')

    tipos_tela = request.form.getlist('tipo_tela[]')
    colores = request.form.getlist('color[]')
    cod_arts = request.form.getlist('cod_art[]')
    cod_colors = request.form.getlist('cod_color[]')
    cant_kgs = request.form.getlist('cant_kg[]')
    piezas_list = request.form.getlist('piezas[]')
    partidas = request.form.getlist('partida[]')
    precios_sin_iva = request.form.getlist('precio_sin_iva[]')
    precios_con_iva = request.form.getlist('precio_con_iva[]')
    subtotales = request.form.getlist('subtotal[]')
    subtotales_iva = request.form.getlist('subtotal_iva[]')

    cuenta = request.form.get('cuenta', '')
    percp_iva = parse_money(request.form.get('percp_iva'))
    percp_iibb = parse_money(request.form.get('percp_iibb'))
    temporada = request.form.get('temporada', '')
    anticipo_id = int(request.form['anticipo_id']) if request.form.get('anticipo_id') else None
    monto = parse_money(request.form.get('monto'))
    nro_anticipo = request.form.get('nro_anticipo', '')

    if nro_comprobante:
        dup_cc = CuentaCorriente.query.filter_by(
            proveedor_id=proveedor_id,
            numero_comprobante=nro_comprobante
        ).first()
        if dup_cc:
            flash(f'Ya existe un comprobante "{nro_comprobante}" para este proveedor ({dup_cc.tipo} del {dup_cc.fecha.strftime("%d/%m/%Y")}). Operacion cancelada.', 'danger')
            return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))

    if tipo_op != 'nc_devolucion':
        if monto < 0:
            flash('El monto no puede ser negativo.', 'danger')
            return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))
        if tipo_op == 'factura_anticipo' and parse_money(request.form.get('neto')) < 0:
            flash('El neto no puede ser negativo.', 'danger')
            return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))
        for i, ck in enumerate(cant_kgs):
            if parse_kg(ck) < 0:
                flash(f'Los Kg no pueden ser negativos (linea {i+1}).', 'danger')
                return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))
        for i, psi in enumerate(precios_sin_iva):
            if parse_money(psi) < 0:
                flash(f'El precio no puede ser negativo (linea {i+1}).', 'danger')
                return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))

    if tipo_op == 'factura_anticipo':
        kg_anticipo = parse_kg(request.form.get('kg_anticipo'))
        # La factura de anticipo se carga por NETO + alicuota de IVA. El bruto
        # (lo que efectivamente se debe en Cta. Cte.) se calcula a partir de eso
        # y queda guardado en monto. Guardar el neto aparte permite que las
        # retenciones de Ganancias usen la base imponible correcta.
        neto = parse_money(request.form.get('neto'))
        iva_alic = D(request.form.get('iva_alicuota') or '21')
        bruto = q2(neto * (D(1) + iva_alic / D(100)))
        a = Anticipo(
            numero=nro_anticipo or nro_comprobante,
            fecha=fecha,
            proveedor_id=proveedor_id,
            numero_factura=nro_comprobante,
            monto=bruto,
            neto=neto,
            iva_alicuota=iva_alic,
            cant_kg=kg_anticipo,
            descripcion=observaciones,
        )
        db.session.add(a)
        cc = CuentaCorriente(
            fecha=fecha, proveedor_id=proveedor_id,
            tipo='Factura', numero_comprobante=nro_comprobante,
            descripcion=f'Factura Anticipo {nro_anticipo or nro_comprobante}',
            cuenta=cuenta, debe=bruto, haber=0
        )
        db.session.add(cc)
        monto = bruto  # para el log de auditoria mas abajo
        flash(f'Anticipo creado y factura registrada en Cta. Cte. (Neto ${neto:,.2f} + IVA {iva_alic}% = Bruto ${bruto:,.2f}).', 'success')

    elif tipo_op == 'ingreso_tela':
        total_kg_all = ZERO
        total_subtotal_iva_all = ZERO
        n_lineas = len(tipos_tela)
        first_mov = True
        for i in range(n_lineas):
            tt = tipos_tela[i] if i < len(tipos_tela) else ''
            col = colores[i] if i < len(colores) else ''
            ca = cod_arts[i] if i < len(cod_arts) else ''
            cc_val = cod_colors[i] if i < len(cod_colors) else ''
            ck = parse_kg(cant_kgs[i]) if i < len(cant_kgs) else ZERO
            pz = int(piezas_list[i] or 0) if i < len(piezas_list) else 0
            pa = partidas[i] if i < len(partidas) else ''
            psi = parse_money(precios_sin_iva[i]) if i < len(precios_sin_iva) else ZERO
            pci = parse_money(precios_con_iva[i]) if i < len(precios_con_iva) else ZERO
            st = parse_money(subtotales[i]) if i < len(subtotales) else ZERO
            sti = parse_money(subtotales_iva[i]) if i < len(subtotales_iva) else ZERO
            if not tt and ck == 0:
                continue
            part_obj = obtener_o_crear_partida(
                pa, proveedor_id, fecha, tt, col, ca, cc_val, pz, ck
            )
            m = MovimientoTela(
                fecha=fecha, proveedor_id=proveedor_id,
                cuenta=cuenta, remito_factura=nro_comprobante,
                tipo_tela=tt, color=col,
                cod_art=ca, cod_color=cc_val,
                cant_kg=ck, piezas=pz, partida=pa,
                partida_id=(part_obj.id if part_obj else None),
                precio_sin_iva=psi, precio_con_iva=pci,
                subtotal=st, subtotal_iva=sti,
                percp_iva=percp_iva if first_mov else ZERO,
                percp_iibb=percp_iibb if first_mov else ZERO,
                movimiento='Ingreso', temporada=temporada,
                anticipo_id=anticipo_id, observaciones=observaciones,
            )
            db.session.add(m)
            first_mov = False
            total_kg_all += ck
            total_subtotal_iva_all += sti

        total_factura = total_subtotal_iva_all + percp_iva + percp_iibb
        if total_factura and nro_comprobante:
            cc = CuentaCorriente(
                fecha=fecha, proveedor_id=proveedor_id,
                tipo='Factura', numero_comprobante=nro_comprobante,
                descripcion=f'Ingreso tela ({n_lineas} lineas) {total_kg_all:.2f}kg',
                cuenta=cuenta, debe=total_factura, haber=ZERO
            )
            db.session.add(cc)

        flash(f'Ingreso de {total_kg_all:.2f}kg de tela registrado ({n_lineas} lineas).', 'success')

    elif tipo_op == 'ingreso_tela_anticipo':
        pedido_id_val = request.form.get('pedido_id', type=int) or None
        cuenta_asignacion_id = request.form.get('cuenta_asignacion_id', type=int) or None

        total_kg_all = ZERO
        total_subtotal_iva_all = ZERO
        n_lineas = len(tipos_tela)
        for i in range(n_lineas):
            ck = parse_kg(cant_kgs[i]) if i < len(cant_kgs) else ZERO
            sti = parse_money(subtotales_iva[i]) if i < len(subtotales_iva) else ZERO
            tt = tipos_tela[i] if i < len(tipos_tela) else ''
            if not tt and ck == 0:
                continue
            total_kg_all += ck
            total_subtotal_iva_all += sti

        if cuenta_asignacion_id:
            ca_obj = db.session.get(CuentaAsignacion, cuenta_asignacion_id)
            if ca_obj:
                if D(ca_obj.cant_kg) > 0 and D(ca_obj.kg_entregados()) + total_kg_all > D(ca_obj.cant_kg):
                    flash(f'Se exceden los Kg de la cuenta {ca_obj.numero}. '
                          f'Disponible: {D(ca_obj.kg_pendientes()):.2f} kg, Ingresando: {total_kg_all:.2f} kg', 'danger')
                    return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))
                if D(ca_obj.monto) > 0 and D(ca_obj.valor_entregado()) + total_subtotal_iva_all > D(ca_obj.monto):
                    flash(f'Se excede el monto de la cuenta {ca_obj.numero}. '
                          f'Disponible: ${D(ca_obj.saldo_pendiente()):,.2f}, Ingresando: ${total_subtotal_iva_all:,.2f}', 'danger')
                    return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))

        total_kg_all = ZERO
        for i in range(n_lineas):
            tt = tipos_tela[i] if i < len(tipos_tela) else ''
            col = colores[i] if i < len(colores) else ''
            ca = cod_arts[i] if i < len(cod_arts) else ''
            cc_val = cod_colors[i] if i < len(cod_colors) else ''
            ck = parse_kg(cant_kgs[i]) if i < len(cant_kgs) else ZERO
            pz = int(piezas_list[i] or 0) if i < len(piezas_list) else 0
            pa = partidas[i] if i < len(partidas) else ''
            psi = parse_money(precios_sin_iva[i]) if i < len(precios_sin_iva) else ZERO
            pci = parse_money(precios_con_iva[i]) if i < len(precios_con_iva) else ZERO
            st = parse_money(subtotales[i]) if i < len(subtotales) else ZERO
            sti = parse_money(subtotales_iva[i]) if i < len(subtotales_iva) else ZERO
            if not tt and ck == 0:
                continue
            part_obj = obtener_o_crear_partida(
                pa, proveedor_id, fecha, tt, col, ca, cc_val, pz, ck
            )
            m = MovimientoTela(
                fecha=fecha, proveedor_id=proveedor_id,
                cuenta=cuenta, remito_factura=nro_comprobante,
                tipo_tela=tt, color=col,
                cod_art=ca, cod_color=cc_val,
                cant_kg=ck, piezas=pz, partida=pa,
                partida_id=(part_obj.id if part_obj else None),
                precio_sin_iva=psi, precio_con_iva=pci,
                subtotal=st, subtotal_iva=sti,
                movimiento='Ingreso', temporada=temporada,
                anticipo_id=anticipo_id, pedido_id=pedido_id_val,
                cuenta_asignacion_id=cuenta_asignacion_id,
                observaciones=observaciones,
            )
            db.session.add(m)
            total_kg_all += ck

        msg = f'Ingreso de {total_kg_all:.2f}kg ({n_lineas} lineas) asociado a anticipo'
        if pedido_id_val:
            ped = db.session.get(Pedido, pedido_id_val)
            if ped:
                msg += f' y pedido {ped.numero}'
        flash(msg + '.', 'success')

        if pedido_id_val:
            ped = db.session.get(Pedido, pedido_id_val)
            if ped:
                ped.actualizar_estado()
                kg_ent_ped = D(ped.kg_entregados())
                kg_tot_ped = D(ped.total_kg())
                val_ent_ped = D(ped.valor_entregado())
                val_tot_ped = D(ped.total_valor())
                if kg_tot_ped > 0 and kg_ent_ped > kg_tot_ped:
                    flash(f'⚠️ ATENCION: Se excedieron los Kg del pedido {ped.numero}. Entregados: {kg_ent_ped:.2f} kg / Pedido: {kg_tot_ped:.2f} kg (exceso: {kg_ent_ped - kg_tot_ped:.2f} kg)', 'warning')
                if val_tot_ped > 0 and val_ent_ped > val_tot_ped:
                    flash(f'⚠️ ATENCION: Se excedio el importe del pedido {ped.numero}. Entregado: ${val_ent_ped:,.2f} / Pedido: ${val_tot_ped:,.2f}', 'warning')

        ant = db.session.get(Anticipo, anticipo_id)
        if ant:
            nuevo_total_kg = D(ant.total_kg_entregados())
            nuevo_total_val = D(ant.total_valor_entregado())
            if D(ant.cant_kg) > 0 and nuevo_total_kg > D(ant.cant_kg):
                flash(f'⚠️ ATENCION: Se excedieron los Kg del anticipo. Entregados: {nuevo_total_kg:.2f} kg / Anticipo: {D(ant.cant_kg):.2f} kg', 'warning')
            if D(ant.monto) > 0 and nuevo_total_val > D(ant.monto):
                flash(f'⚠️ ATENCION: Se excedio el monto del anticipo. Entregado: ${nuevo_total_val:,.2f} / Anticipo: ${D(ant.monto):,.2f}', 'warning')

    elif tipo_op == 'nc_devolucion':
        total_kg_all = ZERO
        n_lineas = len(tipos_tela)
        first_mov = True
        for i in range(n_lineas):
            tt = tipos_tela[i] if i < len(tipos_tela) else ''
            col = colores[i] if i < len(colores) else ''
            ca = cod_arts[i] if i < len(cod_arts) else ''
            cc_val = cod_colors[i] if i < len(cod_colors) else ''
            ck = parse_kg(cant_kgs[i]) if i < len(cant_kgs) else ZERO
            pz = int(piezas_list[i] or 0) if i < len(piezas_list) else 0
            pa = partidas[i] if i < len(partidas) else ''
            psi = parse_money(precios_sin_iva[i]) if i < len(precios_sin_iva) else ZERO
            pci = parse_money(precios_con_iva[i]) if i < len(precios_con_iva) else ZERO
            st = parse_money(subtotales[i]) if i < len(subtotales) else ZERO
            sti = parse_money(subtotales_iva[i]) if i < len(subtotales_iva) else ZERO
            if not tt and ck == 0:
                continue
            m = MovimientoTela(
                fecha=fecha, proveedor_id=proveedor_id,
                cuenta=cuenta, remito_factura=nro_comprobante,
                tipo_tela=tt, color=col,
                cod_art=ca, cod_color=cc_val,
                cant_kg=-abs(ck), piezas=-abs(pz), partida=pa,
                precio_sin_iva=psi, precio_con_iva=pci,
                subtotal=st, subtotal_iva=sti,
                percp_iva=percp_iva if first_mov else ZERO,
                percp_iibb=percp_iibb if first_mov else ZERO,
                movimiento='Devolucion', estado='Pendiente NC',
                temporada=temporada, observaciones=observaciones,
            )
            db.session.add(m)
            first_mov = False
            total_kg_all += ck

        flash(f'Devolucion de {total_kg_all:.2f}kg registrada como "Pendiente NC". '
              f'Cuando recibas la NC del proveedor, asociala desde Notas de Credito.', 'success')

    elif tipo_op == 'nd':
        cc = CuentaCorriente(
            fecha=fecha, proveedor_id=proveedor_id,
            tipo='Nota de Debito', numero_comprobante=nro_comprobante,
            descripcion=observaciones or 'Nota de Debito',
            cuenta=cuenta, debe=monto, haber=ZERO
        )
        db.session.add(cc)
        flash('Nota de Debito registrada.', 'success')

    detalle_ops = {
        'factura_anticipo': f'Anticipo+CC factura {nro_comprobante} ${monto}',
        'ingreso_tela': f'Ingreso tela {nro_comprobante}',
        'ingreso_tela_anticipo': f'Ingreso tela contra anticipo {nro_comprobante}',
        'nc_devolucion': f'Devolucion pendiente NC {nro_comprobante}',
        'nd': f'Nota de Debito {nro_comprobante} ${monto}',
    }
    entidad_ops = {
        'factura_anticipo': 'Anticipo',
        'ingreso_tela': 'MovimientoTela',
        'ingreso_tela_anticipo': 'MovimientoTela',
        'nc_devolucion': 'MovimientoTela',
        'nd': 'CuentaCorriente',
    }
    registrar_auditoria('Crear', entidad_ops.get(tipo_op, 'CuentaCorriente'), proveedor_id, detalle_ops.get(tipo_op, tipo_op))
    db.session.commit()
    return redirect(url_for('panel.panel', proveedor_id=proveedor_id, vista='resumen'))


@bp.route('/panel/anticipo/<int:id>/cerrar', methods=['POST'])
def panel_anticipo_cerrar(id):
    a = Anticipo.query.get_or_404(id)
    a.estado = 'Cerrado'
    registrar_auditoria('Cerrar', 'Anticipo', a.id,
                        f'Anticipo {a.numero} ${a.monto} - Kg pedidos: {a.cant_kg or 0}, Kg entregados: {a.total_kg_entregados()}, $ entregado: {a.total_valor_entregado()}')
    db.session.commit()
    flash(f'Anticipo "{a.numero}" cerrado.', 'success')
    return redirect(url_for('panel.panel', proveedor_id=a.proveedor_id, vista='resumen'))


@bp.route('/panel/cc/<int:id>/editar', methods=['GET', 'POST'])
def panel_cc_editar(id):
    cc = CuentaCorriente.query.get_or_404(id)
    if request.method == 'POST':
        cc.fecha = date.fromisoformat(request.form['fecha'])
        cc.tipo = request.form.get('tipo', '')
        cc.numero_comprobante = request.form.get('numero_comprobante', '')
        cc.descripcion = request.form.get('descripcion', '')
        cc.debe = parse_money(request.form.get('debe'))
        cc.haber = parse_money(request.form.get('haber'))
        registrar_auditoria('Editar', 'CuentaCorriente', cc.id, f'{cc.tipo} Comp:{cc.numero_comprobante}')
        db.session.commit()
        flash('Movimiento de Cta. Cte. actualizado.', 'success')
        return redirect(url_for('panel.panel', proveedor_id=cc.proveedor_id, vista='cc'))
    return render_template('panel/editar_cc.html', cc=cc)


@bp.route('/panel/cc/<int:id>/eliminar', methods=['POST'])
def panel_cc_eliminar(id):
    cc = CuentaCorriente.query.get_or_404(id)
    pid = cc.proveedor_id

    pagos_aplicados = PagoFactura.query.filter_by(cc_factura_id=cc.id).all()
    if pagos_aplicados:
        nros = sorted({pf.pago.numero for pf in pagos_aplicados if pf.pago and pf.pago.numero})
        detalle = f' (Pago/s: {", ".join(nros)})' if nros else ''
        flash(f'No se puede eliminar: esta factura tiene pagos aplicados{detalle}. '
              f'Eliminá primero el pago desde el módulo de Pagos.', 'danger')
        return redirect(url_for('panel.panel', proveedor_id=pid, vista='cc'))

    RetencionGanancias.query.filter_by(cc_pago_id=cc.id).update({'cc_pago_id': None})
    RetencionGanancias.query.filter_by(cc_retencion_id=cc.id).update({'cc_retencion_id': None})
    NotaCredito.query.filter_by(cc_id=cc.id).update({'cc_id': None})

    eliminados = []
    if cc.numero_comprobante:
        anticipo = Anticipo.query.filter_by(
            proveedor_id=pid, numero_factura=cc.numero_comprobante
        ).first()
        if anticipo:
            for p in Pedido.query.filter_by(anticipo_id=anticipo.id).all():
                MovimientoTela.query.filter_by(pedido_id=p.id).update({'pedido_id': None})
                PedidoDetalle.query.filter_by(pedido_id=p.id).delete()
                db.session.delete(p)
            MovimientoTela.query.filter_by(anticipo_id=anticipo.id).update({'anticipo_id': None})
            db.session.delete(anticipo)
            eliminados.append(f'Anticipo "{anticipo.numero}" y sus pedidos')
        movs_tela = MovimientoTela.query.filter_by(
            proveedor_id=pid, remito_factura=cc.numero_comprobante
        ).all()
        if movs_tela:
            for m in movs_tela:
                db.session.delete(m)
            eliminados.append(f'{len(movs_tela)} movimiento(s) de tela')
    cascade_info = f' | Cascada: {", ".join(eliminados)}' if eliminados else ''
    registrar_auditoria('Eliminar', 'CuentaCorriente', cc.id, f'{cc.tipo} Comp:{cc.numero_comprobante}{cascade_info}')
    db.session.delete(cc)
    db.session.commit()
    if eliminados:
        flash(f'Eliminado en cascada: {", ".join(eliminados)}.', 'warning')
    flash('Movimiento de Cta. Cte. eliminado.', 'warning')
    return redirect(url_for('panel.panel', proveedor_id=pid, vista='cc'))


@bp.route('/panel/anticipo/<int:id>/editar', methods=['GET', 'POST'])
def panel_anticipo_editar(id):
    a = Anticipo.query.get_or_404(id)
    if request.method == 'POST':
        a.numero = request.form['numero']
        a.fecha = date.fromisoformat(request.form['fecha'])
        a.numero_factura = request.form.get('numero_factura', '')
        # El bruto se recalcula desde neto + IVA% para mantener coherencia.
        # Si el form no manda neto (compatibilidad con flujos viejos), usa el monto crudo.
        neto_raw = request.form.get('neto')
        if neto_raw is not None and neto_raw != '':
            neto = parse_money(neto_raw)
            iva_alic = D(request.form.get('iva_alicuota') or '21')
            a.neto = neto
            a.iva_alicuota = iva_alic
            a.monto = q2(neto * (D(1) + iva_alic / D(100)))
        else:
            a.monto = parse_money(request.form.get('monto'))
        a.cant_kg = parse_kg(request.form.get('cant_kg'))
        a.descripcion = request.form.get('descripcion', '')
        a.estado = request.form.get('estado', 'Abierto')

        # Mantener sincronizado el asiento en Cta. Cte. (Factura) cuando existe.
        if a.numero_factura:
            cc_factura = CuentaCorriente.query.filter_by(
                proveedor_id=a.proveedor_id,
                tipo='Factura',
                numero_comprobante=a.numero_factura,
            ).first()
            if cc_factura:
                cc_factura.debe = a.monto
                cc_factura.fecha = a.fecha

        registrar_auditoria('Editar', 'Anticipo', a.id,
                            f'Anticipo {a.numero} neto ${a.neto} ({a.iva_alicuota}% IVA) bruto ${a.monto}')
        db.session.commit()
        flash(f'Anticipo "{a.numero}" actualizado.', 'success')
        return redirect(url_for('panel.panel', proveedor_id=a.proveedor_id, vista='anticipos'))
    return render_template('panel/editar_anticipo.html', anticipo=a)


@bp.route('/panel/anticipo/<int:id>/eliminar', methods=['POST'])
def panel_anticipo_eliminar(id):
    a = Anticipo.query.get_or_404(id)
    pid = a.proveedor_id
    MovimientoTela.query.filter_by(anticipo_id=id).update({'anticipo_id': None, 'pedido_id': None})
    pedidos_eliminados = []
    for p in Pedido.query.filter_by(anticipo_id=id).all():
        pedidos_eliminados.append(p.numero)
        PedidoDetalle.query.filter_by(pedido_id=p.id).delete()
        db.session.delete(p)
    cascade_info = f' | Pedidos eliminados: {", ".join(pedidos_eliminados)}' if pedidos_eliminados else ''
    registrar_auditoria('Eliminar', 'Anticipo', a.id, f'Anticipo {a.numero} ${a.monto}{cascade_info}')
    db.session.delete(a)
    db.session.commit()
    flash(f'Anticipo eliminado.', 'warning')
    return redirect(url_for('panel.panel', proveedor_id=pid, vista='anticipos'))


@bp.route('/panel/tela/<int:id>/editar', methods=['GET', 'POST'])
def panel_tela_editar(id):
    m = MovimientoTela.query.get_or_404(id)
    if request.method == 'POST':
        m.fecha = date.fromisoformat(request.form['fecha'])
        m.cuenta = request.form.get('cuenta', '')
        m.remito_factura = request.form.get('remito_factura', '')
        m.tipo_tela = request.form.get('tipo_tela', '')
        m.color = request.form.get('color', '')
        m.cod_art = request.form.get('cod_art', '')
        m.cod_color = request.form.get('cod_color', '')
        m.cant_kg = parse_kg(request.form.get('cant_kg'))
        m.piezas = int(request.form.get('piezas', 0) or 0)
        m.partida = request.form.get('partida', '')
        m.precio_sin_iva = parse_money(request.form.get('precio_sin_iva'))
        m.precio_con_iva = parse_money(request.form.get('precio_con_iva'))
        m.subtotal = parse_money(request.form.get('subtotal'))
        m.subtotal_iva = parse_money(request.form.get('subtotal_iva'))
        m.movimiento = request.form.get('movimiento', 'Ingreso')
        m.temporada = request.form.get('temporada', '')
        m.observaciones = request.form.get('observaciones', '')
        m.anticipo_id = int(request.form['anticipo_id']) if request.form.get('anticipo_id') else None
        if m.pedido:
            m.pedido.actualizar_estado()
        registrar_auditoria('Editar', 'MovimientoTela', m.id, f'{m.movimiento} {m.cant_kg}kg {m.tipo_tela}')
        db.session.commit()
        flash('Movimiento de tela actualizado.', 'success')
        return redirect(url_for('panel.panel', proveedor_id=m.proveedor_id, vista='tela'))
    anticipos = Anticipo.query.filter_by(proveedor_id=m.proveedor_id).order_by(Anticipo.numero).all()
    return render_template('panel/editar_tela.html', m=m, anticipos=anticipos)


@bp.route('/panel/tela/<int:id>/eliminar', methods=['POST'])
def panel_tela_eliminar(id):
    m = MovimientoTela.query.get_or_404(id)
    pid = m.proveedor_id
    pedido = m.pedido
    registrar_auditoria('Eliminar', 'MovimientoTela', m.id, f'{m.movimiento} {m.cant_kg}kg {m.tipo_tela}')
    db.session.delete(m)
    if pedido:
        pedido.actualizar_estado()
    db.session.commit()
    flash('Movimiento de tela eliminado.', 'warning')
    return redirect(url_for('panel.panel', proveedor_id=pid, vista='tela'))
