import io
from datetime import date

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, send_file)
from sqlalchemy.orm import joinedload

from models import (db, Proveedor, ConceptoRetencionGanancias,
                    EscalaGanancias, RetencionGanancias, CuentaCorriente)
from money import D, ZERO, parse_money, q4
from retenciones import AGENTES_RETENCION, calcular_retencion, base_imponible_factura
from utils import registrar_auditoria

bp = Blueprint('impuestos', __name__)


@bp.route('/retenciones')
@bp.route('/impuestos')
def impuestos_index():
    """Dashboard de impuestos con totales del mes."""
    mes = request.args.get('mes', '') or date.today().strftime('%Y-%m')
    retenciones_mes = RetencionGanancias.query.filter_by(mes_anio=mes).all()
    total_mes = sum(r.retencion or 0 for r in retenciones_mes)
    total_sujeto_mes = sum(r.monto_sujeto or 0 for r in retenciones_mes)
    por_agente = {}
    for r in retenciones_mes:
        k = r.agente_cuit
        if k not in por_agente:
            por_agente[k] = {'nombre': r.agente_nombre, 'cantidad': 0,
                             'retencion': 0, 'monto_sujeto': 0}
        por_agente[k]['cantidad'] += 1
        por_agente[k]['retencion'] += r.retencion or 0
        por_agente[k]['monto_sujeto'] += r.monto_sujeto or 0
    return render_template('impuestos/index.html',
                           mes=mes,
                           total_mes=total_mes,
                           total_sujeto_mes=total_sujeto_mes,
                           cantidad_mes=len(retenciones_mes),
                           por_agente=por_agente,
                           agentes=AGENTES_RETENCION)


@bp.route('/retenciones/calculadora', methods=['GET', 'POST'])
@bp.route('/impuestos/calculadora', methods=['GET', 'POST'])
def retenciones_calculadora():
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    conceptos = ConceptoRetencionGanancias.query.filter_by(activo=True).order_by(ConceptoRetencionGanancias.codigo).all()

    resultado = None
    proveedor = None
    concepto = None
    fecha_pago = date.today()
    monto = 0
    numero_comprobante = ''
    agente_codigo = 'JUMAF'

    if request.method == 'POST':
        prov_id = int(request.form.get('proveedor_id') or 0)
        concepto_id = int(request.form.get('concepto_id') or 0)
        monto = parse_money(request.form.get('monto'))
        fecha_str = request.form.get('fecha') or ''
        numero_comprobante = request.form.get('numero_comprobante', '')
        agente_codigo = request.form.get('agente_codigo', 'JUMAF')
        if fecha_str:
            fecha_pago = date.fromisoformat(fecha_str)

        proveedor = db.session.get(Proveedor, prov_id) if prov_id else None
        concepto = db.session.get(ConceptoRetencionGanancias, concepto_id) if concepto_id else None

        if proveedor and concepto:
            resultado = calcular_retencion(proveedor, concepto, monto, fecha_pago)

    return render_template('retenciones/calculadora.html',
                           proveedores=proveedores, conceptos=conceptos,
                           resultado=resultado, proveedor=proveedor,
                           concepto=concepto, fecha_pago=fecha_pago,
                           monto=monto, numero_comprobante=numero_comprobante,
                           agente_codigo=agente_codigo,
                           agentes=AGENTES_RETENCION)


@bp.route('/api/retenciones/calcular', methods=['POST'])
def api_retenciones_calcular():
    data = request.get_json() or request.form
    prov_id = int(data.get('proveedor_id') or 0)
    fecha_str = data.get('fecha') or ''
    concepto_id = data.get('concepto_id')
    fecha_pago = date.fromisoformat(fecha_str) if fecha_str else date.today()

    proveedor = db.session.get(Proveedor, prov_id)
    if not proveedor:
        return jsonify({'error': 'Proveedor no encontrado'}), 404

    concepto = None
    if concepto_id:
        concepto = db.session.get(ConceptoRetencionGanancias, int(concepto_id))
    else:
        concepto = proveedor.concepto_retencion

    # RG 830 art. 23: la base es el neto gravado (sin IVA/percepciones).
    # Si vienen aplicaciones de facturas se reconstruye el neto factura por
    # factura para reflejar exactamente lo que se va a guardar al confirmar.
    aplicaciones = data.get('aplicaciones') or []
    monto = ZERO
    if aplicaciones:
        for a in aplicaciones:
            try:
                fid = int(a.get('factura_id') or 0)
                m = parse_money(a.get('monto'))
            except (TypeError, ValueError):
                continue
            if fid <= 0 or m <= 0:
                continue
            cc = db.session.get(CuentaCorriente, fid)
            if not cc or cc.proveedor_id != prov_id:
                continue
            signo = -1 if cc.es_credito() else 1
            monto += signo * D(base_imponible_factura(cc, m))
        if monto < 0:
            monto = ZERO
    else:
        monto = parse_money(data.get('monto'))

    if not concepto:
        return jsonify({
            'aplica': False,
            'motivo': 'El proveedor no tiene concepto de retencion asignado',
            'retencion': 0, 'monto_neto': monto,
            'condicion_ganancias': proveedor.condicion_ganancias,
        })

    r = calcular_retencion(proveedor, concepto, monto, fecha_pago)
    r['condicion_ganancias'] = proveedor.condicion_ganancias
    r['concepto_nombre'] = concepto.concepto
    r['concepto_codigo'] = concepto.codigo
    return jsonify(r)


@bp.route('/retenciones/historial')
@bp.route('/impuestos/retenciones')
def retenciones_historial():
    proveedor_id = request.args.get('proveedor_id', type=int)
    desde = request.args.get('desde', '')
    hasta = request.args.get('hasta', '')
    agente = request.args.get('agente', '')
    page = request.args.get('page', 1, type=int)

    q = RetencionGanancias.query
    if proveedor_id:
        q = q.filter_by(proveedor_id=proveedor_id)
    if desde:
        q = q.filter(RetencionGanancias.fecha >= date.fromisoformat(desde))
    if hasta:
        q = q.filter(RetencionGanancias.fecha <= date.fromisoformat(hasta))
    if agente:
        q = q.filter_by(agente_cuit=agente)

    # Totales agregados sobre todo el filtro (no solo la pagina visible).
    sub = q.with_entities(
        RetencionGanancias.retencion, RetencionGanancias.monto_sujeto
    ).subquery()
    totales = db.session.query(
        db.func.coalesce(db.func.sum(sub.c.retencion), 0),
        db.func.coalesce(db.func.sum(sub.c.monto_sujeto), 0),
    ).one()
    total_retenido, total_monto = totales

    retenciones = q.options(
        joinedload(RetencionGanancias.proveedor),
        joinedload(RetencionGanancias.concepto),
    ).order_by(
        RetencionGanancias.fecha.desc(), RetencionGanancias.id.desc()
    ).paginate(page=page, per_page=50, error_out=False)
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    return render_template('retenciones/historial.html',
                           retenciones=retenciones, proveedores=proveedores,
                           total_retenido=total_retenido, total_monto=total_monto,
                           filtros={'proveedor_id': proveedor_id, 'desde': desde,
                                    'hasta': hasta, 'agente': agente},
                           agentes=AGENTES_RETENCION)


@bp.route('/retenciones/<int:id>/certificado')
def retenciones_certificado(id):
    r = RetencionGanancias.query.get_or_404(id)
    agente = None
    for a in AGENTES_RETENCION:
        if a['cuit'] == r.agente_cuit:
            agente = a
            break
    if not agente:
        agente = {'razon_social': r.agente_nombre or '',
                  'cuit': r.agente_cuit or '', 'domicilio': 'Av. Escalada 1540'}
    return render_template('retenciones/certificado.html', r=r, agente=agente)


@bp.route('/retenciones/<int:id>/eliminar', methods=['POST'])
def retenciones_eliminar(id):
    r = RetencionGanancias.query.get_or_404(id)
    if r.cc_pago_id:
        cc = db.session.get(CuentaCorriente, r.cc_pago_id)
        if cc:
            db.session.delete(cc)
    if r.cc_retencion_id:
        cc = db.session.get(CuentaCorriente, r.cc_retencion_id)
        if cc:
            db.session.delete(cc)
    registrar_auditoria('Eliminar', 'RetencionGanancias', r.id,
                        f'Retencion {r.numero_comprobante} ${r.retencion}')
    db.session.delete(r)
    db.session.commit()
    flash('Retencion eliminada (y asientos de CC revertidos).', 'warning')
    return redirect(url_for('impuestos.retenciones_historial'))


@bp.route('/retenciones/resumen-mensual')
@bp.route('/impuestos/resumen-mensual')
def retenciones_resumen_mensual():
    mes = request.args.get('mes', '') or date.today().strftime('%Y-%m')
    agente = request.args.get('agente', '')

    q = RetencionGanancias.query.options(
        joinedload(RetencionGanancias.proveedor),
        joinedload(RetencionGanancias.concepto),
    ).filter_by(mes_anio=mes)
    if agente:
        q = q.filter_by(agente_cuit=agente)
    retenciones = q.order_by(RetencionGanancias.fecha).all()

    grupos = {}
    for r in retenciones:
        key = (r.proveedor_id, r.concepto_id)
        if key not in grupos:
            grupos[key] = {
                'proveedor': r.proveedor, 'concepto': r.concepto,
                'cantidad': 0, 'monto_sujeto': 0, 'retencion': 0,
            }
        grupos[key]['cantidad'] += 1
        grupos[key]['monto_sujeto'] += r.monto_sujeto or 0
        grupos[key]['retencion'] += r.retencion or 0

    total_monto = sum(g['monto_sujeto'] for g in grupos.values())
    total_retencion = sum(g['retencion'] for g in grupos.values())

    return render_template('retenciones/resumen_mensual.html',
                           mes=mes, agente=agente, grupos=list(grupos.values()),
                           retenciones=retenciones,
                           total_monto=total_monto, total_retencion=total_retencion,
                           agentes=AGENTES_RETENCION)


@bp.route('/retenciones/parametros', methods=['GET', 'POST'])
@bp.route('/impuestos/parametros', methods=['GET', 'POST'])
def retenciones_parametros():
    if request.method == 'POST':
        for c in ConceptoRetencionGanancias.query.all():
            prefix = f'c_{c.id}_'
            if request.form.get(prefix + 'mni') is not None:
                c.mni_inscripto = parse_money(request.form.get(prefix + 'mni'))
                c.alicuota_inscripto = q4(request.form.get(prefix + 'alic_ins') or 0)
                c.alicuota_no_inscripto = q4(request.form.get(prefix + 'alic_noins') or 0)
                c.min_retencion_inscripto = parse_money(request.form.get(prefix + 'min_ins'))
                c.min_retencion_no_inscripto = parse_money(request.form.get(prefix + 'min_noins'))
        for e in EscalaGanancias.query.all():
            prefix = f'e_{e.id}_'
            if request.form.get(prefix + 'desde') is not None:
                e.desde = parse_money(request.form.get(prefix + 'desde'))
                e.hasta = parse_money(request.form.get(prefix + 'hasta'))
                e.monto_fijo = parse_money(request.form.get(prefix + 'monto_fijo'))
                e.alicuota_marginal = q4(request.form.get(prefix + 'alic') or 0)
                e.excedente_sobre = parse_money(request.form.get(prefix + 'excedente'))
        registrar_auditoria('Editar', 'ParametrosAFIP', 0, 'Actualizacion parametros RG 830')
        db.session.commit()
        flash('Parametros AFIP actualizados.', 'success')
        return redirect(url_for('impuestos.retenciones_parametros'))

    conceptos = ConceptoRetencionGanancias.query.order_by(ConceptoRetencionGanancias.codigo).all()
    escala_general = EscalaGanancias.query.filter_by(tipo='General').order_by(EscalaGanancias.desde).all()
    escala_especifica = EscalaGanancias.query.filter_by(tipo='Especifica').order_by(EscalaGanancias.desde).all()
    return render_template('retenciones/parametros.html',
                           conceptos=conceptos,
                           escala_general=escala_general,
                           escala_especifica=escala_especifica)


# ─── Export SICORE (SIAP) ───

def _sicore_pad(valor, ancho, right=False, fill=' '):
    s = str(valor or '')
    if len(s) > ancho:
        s = s[:ancho]
    return s.rjust(ancho, fill) if right else s.ljust(ancho, fill)


def _sicore_importe(n, ancho=14):
    """Formatea importe con 2 decimales sin separadores, con signo."""
    signo = '-' if (n or 0) < 0 else ' '
    entero = int(abs(n or 0) * 100)
    num = f'{entero:0{ancho-1}d}'
    return signo + num


def _codigo_condicion_sicore(condicion):
    if condicion == 'Inscripto':
        return '01'
    if condicion == 'No Inscripto':
        return '02'
    return '04'


@bp.route('/impuestos/sicore', methods=['GET', 'POST'])
def impuestos_sicore():
    mes = request.args.get('mes', '') or request.form.get('mes', '') or date.today().strftime('%Y-%m')
    agente = request.args.get('agente', '') or request.form.get('agente', '')

    if request.method == 'POST':
        q = RetencionGanancias.query.options(
            joinedload(RetencionGanancias.proveedor),
            joinedload(RetencionGanancias.concepto),
        ).filter_by(mes_anio=mes)
        if agente:
            q = q.filter_by(agente_cuit=agente)
        retenciones = q.order_by(RetencionGanancias.fecha, RetencionGanancias.id).all()

        lineas = []
        for r in retenciones:
            cuit_prov = (r.proveedor.cuit or '').replace('-', '').replace(' ', '')
            codigo_regimen = f'{r.concepto.codigo:03d}'
            numero_cert = f'{r.id:014d}'
            fecha_ret = r.fecha.strftime('%d/%m/%Y')
            nro_comp = (r.numero_comprobante or '')[:16]

            linea = (
                _sicore_pad('03', 2)
                + _sicore_pad(fecha_ret, 10)
                + _sicore_pad(nro_comp, 16, right=True, fill='0')
                + _sicore_importe(r.monto_sujeto, 16)
                + _sicore_pad('0217', 4)
                + _sicore_pad(codigo_regimen, 3)
                + _sicore_pad('1', 1)
                + _sicore_importe(r.base_sujeta, 14)
                + _sicore_pad(fecha_ret, 10)
                + _sicore_pad(_codigo_condicion_sicore(r.condicion), 2)
                + _sicore_pad('N', 1)
                + _sicore_importe(r.retencion, 14)
                + _sicore_pad('0' * 6, 6)
                + _sicore_pad('', 10)
                + _sicore_pad('80', 2)
                + _sicore_pad(cuit_prov, 20, right=True, fill='0')
                + _sicore_pad(numero_cert, 14, right=True, fill='0')
            )
            lineas.append(linea)

        contenido = '\r\n'.join(lineas)
        buf = io.BytesIO(contenido.encode('latin-1', errors='replace'))
        nombre = f'SICORE_Ret_Ganancias_{mes}'
        if agente:
            nombre += f'_{agente.replace("-", "")}'
        nombre += '.txt'
        return send_file(buf, download_name=nombre,
                         as_attachment=True, mimetype='text/plain')

    q = RetencionGanancias.query.options(
        joinedload(RetencionGanancias.proveedor),
        joinedload(RetencionGanancias.concepto),
    ).filter_by(mes_anio=mes)
    if agente:
        q = q.filter_by(agente_cuit=agente)
    retenciones = q.order_by(RetencionGanancias.fecha).all()
    total = sum(r.retencion or 0 for r in retenciones)
    return render_template('impuestos/sicore.html',
                           mes=mes, agente=agente,
                           retenciones=retenciones, total=total,
                           agentes=AGENTES_RETENCION)
