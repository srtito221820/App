"""
Modulo de retenciones de Ganancias - RG AFIP 830.

Calcula la retencion considerando acumulado mensual por CUIT+concepto,
MNI, escala progresiva o alicuota fija, y minimo de retencion.

Basado en la plantilla Excel RG830 MEJORADA (Anexo VIII).
"""
from datetime import date
from money import D, ZERO, q2
from models import (
    db, Proveedor, ConceptoRetencionGanancias, EscalaGanancias,
    RetencionGanancias, CuentaCorriente, FacturaCompra, MovimientoTela,
    Anticipo
)


def base_imponible_factura(cc_factura, monto_aplicado):
    """Devuelve la base imponible (neto gravado) sujeta a retenciones Ganancias.

    RG AFIP 830/2000 art. 23: la base se calcula sobre el importe del
    comprobante excluyendo IVA, impuestos internos y combustibles. Las
    percepciones tampoco integran la base.

    Origenes contemplados:
      - FacturaCompra (modulo Compras): neto_gravado proporcional al monto aplicado.
      - Factura de tela (Panel): se reconstruye el neto desde MovimientoTela
        sumando subtotal sin IVA por remito_factura, y se aplica proporcion.
      - Factura de Anticipo (Panel): el neto se guarda en Anticipo.neto al
        crear el comprobante; se aplica proporcion sobre el bruto (CC.debe).
      - Otros (Nota de Debito manual sin desglose): se asume que el monto
        ingresado ya es neto y se usa tal cual.
    """
    monto_aplicado = D(monto_aplicado)
    if monto_aplicado <= 0:
        return ZERO

    fc = FacturaCompra.query.filter_by(cc_id=cc_factura.id).first()
    if fc and D(fc.total) > 0 and D(fc.neto_gravado) > 0:
        proporcion = monto_aplicado / D(fc.total)
        return q2(D(fc.neto_gravado) * proporcion)

    if cc_factura.tipo == 'Factura' and cc_factura.numero_comprobante:
        neto_tela = db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.subtotal), 0)
        ).filter(
            MovimientoTela.proveedor_id == cc_factura.proveedor_id,
            MovimientoTela.remito_factura == cc_factura.numero_comprobante,
            MovimientoTela.movimiento == 'Ingreso',
        ).scalar()
        total_cc = D(cc_factura.debe)
        neto_tela = D(neto_tela)
        if neto_tela > 0 and total_cc > 0:
            proporcion = monto_aplicado / total_cc
            return q2(neto_tela * proporcion)

        anticipo = Anticipo.query.filter_by(
            proveedor_id=cc_factura.proveedor_id,
            numero_factura=cc_factura.numero_comprobante,
        ).first()
        if anticipo and D(anticipo.neto) > 0 and D(anticipo.monto) > 0:
            proporcion = monto_aplicado / D(anticipo.monto)
            return q2(D(anticipo.neto) * proporcion)

    return q2(monto_aplicado)


# ─── Agentes de retencion (empresas del grupo) ───
AGENTES_RETENCION = [
    {
        'codigo': 'JUMAF',
        'razon_social': 'JUMAF S.A.',
        'cuit': '30-70915442-3',
        'domicilio': 'Av. Escalada 1540',
    },
    {
        'codigo': 'JUMASA',
        'razon_social': 'JUMASA S.A.',
        'cuit': '30-71538254-3',
        'domicilio': 'Av. Escalada 1540',
    },
]


def agente_por_codigo(codigo):
    for a in AGENTES_RETENCION:
        if a['codigo'] == codigo:
            return a
    return AGENTES_RETENCION[0]


# ─── Seed de conceptos RG 830 (Anexo VIII) ───
CONCEPTOS_SEED = [
    # codigo, concepto, MNI ins, alic ins, tipo ins, alic no ins, tipo no ins, min ret ins, min ret no ins, escala
    (19, 'Intereses operaciones financieras', 0, 0.03, 'Fija', 0.10, 'Fija', 240, 240, '—'),
    (21, 'Intereses otras operaciones', 7870, 0.06, 'Fija', 0.28, 'Fija', 240, 240, '—'),
    (30, 'Alquiler bienes muebles', 11200, 0.06, 'Fija', 0.28, 'Fija', 240, 240, '—'),
    (31, 'Alquiler inmuebles urbanos', 11200, 0.06, 'Fija', 0.28, 'Fija', 240, 1020, '—'),
    (32, 'Alquiler inmuebles rurales', 11200, 0.06, 'Fija', 0.28, 'Fija', 240, 240, '—'),
    (35, 'Regalias', 7870, 0.06, 'Fija', 0.28, 'Fija', 240, 240, '—'),
    (78, 'Enajenacion bienes muebles/cambio', 224000, 0.02, 'Fija', 0.10, 'Fija', 240, 240, '—'),
    (94, 'Locacion obra/servicios (no prof. liberal)', 67170, 0.02, 'Fija', 0.28, 'Fija', 240, 240, '—'),
    (95, 'Transporte de carga', 67170, 0.0025, 'Fija', 0.28, 'Fija', 240, 240, '—'),
    (110, 'Explotacion derechos de autor', 10000, 0, 'Escala', 0.28, 'Fija', 240, 240, 'General'),
    (25, 'Comisiones / intermediacion', 16830, 0, 'Escala', 0.28, 'Fija', 240, 240, 'General'),
    (116, 'Honorarios directores SA / sindicos', 67170, 0, 'Escala', 0.28, 'Fija', 240, 240, 'General'),
    (119, 'Profesiones liberales y oficios', 160000, 0, 'Escala', 0.28, 'Fija', 240, 240, 'Especifica'),
    (779, 'Subsidios - enajenacion bs. muebles', 76140, 0.02, 'Fija', 0.10, 'Fija', 240, 240, '—'),
    (780, 'Subsidios - locaciones obra/servicios', 31460, 0.02, 'Fija', 0.28, 'Fija', 240, 240, '—'),
]


# ─── Seed de escalas (RG 830 Anexo VIII) ───
ESCALA_GENERAL_SEED = [
    # desde, hasta, monto fijo, alicuota marginal, excedente sobre
    (0, 8000, 0, 0.05, 0),
    (8000, 16000, 400, 0.09, 8000),
    (16000, 24000, 1120, 0.12, 16000),
    (24000, 32000, 2080, 0.15, 24000),
    (32000, 48000, 3280, 0.19, 32000),
    (48000, 64000, 6320, 0.23, 48000),
    (64000, 96000, 10000, 0.27, 64000),
    (96000, 9999999999, 18640, 0.31, 96000),
]

ESCALA_ESPECIFICA_SEED = [
    (0, 71000, 0, 0.05, 0),
    (71000, 142000, 3550, 0.09, 71000),
    (142000, 213000, 9940, 0.12, 142000),
    (213000, 284000, 18460, 0.15, 213000),
    (284000, 426000, 29110, 0.19, 284000),
    (426000, 568000, 56090, 0.23, 426000),
    (568000, 852000, 88750, 0.27, 568000),
    (852000, 9999999999, 165430, 0.31, 852000),
]


def seed_datos_iniciales():
    """Carga conceptos y escalas si no existen. Idempotente."""
    if ConceptoRetencionGanancias.query.count() == 0:
        for row in CONCEPTOS_SEED:
            c = ConceptoRetencionGanancias(
                codigo=row[0], concepto=row[1],
                mni_inscripto=D(row[2]),
                alicuota_inscripto=D(row[3]), tipo_inscripto=row[4],
                alicuota_no_inscripto=D(row[5]), tipo_no_inscripto=row[6],
                min_retencion_inscripto=D(row[7]),
                min_retencion_no_inscripto=D(row[8]),
                escala_aplicable=row[9],
            )
            db.session.add(c)

    if EscalaGanancias.query.count() == 0:
        for row in ESCALA_GENERAL_SEED:
            db.session.add(EscalaGanancias(
                tipo='General', desde=D(row[0]), hasta=D(row[1]),
                monto_fijo=D(row[2]), alicuota_marginal=D(row[3]),
                excedente_sobre=D(row[4]),
            ))
        for row in ESCALA_ESPECIFICA_SEED:
            db.session.add(EscalaGanancias(
                tipo='Especifica', desde=D(row[0]), hasta=D(row[1]),
                monto_fijo=D(row[2]), alicuota_marginal=D(row[3]),
                excedente_sobre=D(row[4]),
            ))
    db.session.commit()


def _aplicar_escala(base, tipo_escala):
    """Calcula impuesto segun tabla progresiva. Devuelve Decimal."""
    base = D(base)
    tramos = EscalaGanancias.query.filter_by(tipo=tipo_escala).order_by(EscalaGanancias.desde).all()
    for t in tramos:
        if base > D(t.desde) and base <= D(t.hasta):
            return D(t.monto_fijo) + (base - D(t.excedente_sobre)) * D(t.alicuota_marginal)
    return ZERO


def calcular_retencion(proveedor, concepto, monto_pago, fecha_pago=None,
                       excluir_retencion_id=None):
    """
    Calcula la retencion a practicar HOY segun RG 830.

    Replica la formula de la hoja Calculadora_Retencion de la plantilla.
    Devuelve un dict con todo el desglose para mostrar y persistir.

    - proveedor: instancia de Proveedor (debe tener condicion_ganancias)
    - concepto: instancia de ConceptoRetencionGanancias
    - monto_pago: monto bruto a pagar hoy
    - fecha_pago: fecha del pago (default: hoy)
    - excluir_retencion_id: al recalcular en edicion, excluir la propia retencion
    """
    if fecha_pago is None:
        fecha_pago = date.today()
    condicion = (proveedor.condicion_ganancias or 'No Aplica').strip()
    mes_anio = fecha_pago.strftime('%Y-%m')

    monto_pago_d = D(monto_pago)
    resultado = {
        'aplica': False,
        'motivo': '',
        'condicion': condicion,
        'concepto_id': concepto.id if concepto else None,
        'concepto': concepto.concepto if concepto else '',
        'codigo': concepto.codigo if concepto else None,
        'mes_anio': mes_anio,
        'monto_pago': monto_pago_d,
        'acumulado_previo': ZERO,
        'retenido_previo': ZERO,
        'base_acumulada': ZERO,
        'mni': ZERO,
        'base_sujeta': ZERO,
        'impuesto_teorico': ZERO,
        'retencion_neta': ZERO,
        'minimo_retencion': ZERO,
        'retencion': ZERO,
        'monto_neto': monto_pago_d,
        'alicuota_aplicada': '',
        'tipo_calculo': '',
        'escala_aplicable': '—',
    }

    if not concepto:
        resultado['motivo'] = 'Sin concepto asignado'
        return resultado

    if condicion not in ('Inscripto', 'No Inscripto'):
        resultado['motivo'] = f'Proveedor {condicion}: no corresponde retencion'
        return resultado

    if monto_pago_d <= 0:
        resultado['motivo'] = 'Monto 0'
        return resultado

    # ── Parametros segun condicion ──
    if condicion == 'Inscripto':
        mni = D(concepto.mni_inscripto)
        alicuota_fija = D(concepto.alicuota_inscripto)
        tipo = concepto.tipo_inscripto or 'Fija'
        min_ret = D(concepto.min_retencion_inscripto)
    else:
        mni = ZERO  # No Inscripto: no aplica MNI
        alicuota_fija = D(concepto.alicuota_no_inscripto)
        tipo = concepto.tipo_no_inscripto or 'Fija'
        min_ret = D(concepto.min_retencion_no_inscripto)

    # ── Acumulado mensual previo (mismo CUIT + concepto + mes) ──
    # RG 830 art. 26: el acumulado se mide sobre la base imponible neta (sin IVA),
    # no sobre el importe bruto del comprobante.
    q = db.session.query(
        db.func.coalesce(db.func.sum(RetencionGanancias.base_imponible), 0),
        db.func.coalesce(db.func.sum(RetencionGanancias.retencion), 0)
    ).filter(
        RetencionGanancias.proveedor_id == proveedor.id,
        RetencionGanancias.concepto_id == concepto.id,
        RetencionGanancias.mes_anio == mes_anio,
    )
    if excluir_retencion_id:
        q = q.filter(RetencionGanancias.id != excluir_retencion_id)
    acum_previo, ret_previo = q.one()
    acum_previo = D(acum_previo)
    ret_previo = D(ret_previo)

    base_acum = acum_previo + monto_pago_d
    base_sujeta = max(ZERO, base_acum - mni)

    # ── Impuesto teorico ──
    if tipo == 'Fija':
        impuesto = q2(base_sujeta * alicuota_fija)
        alic_pct = alicuota_fija * 100
        alic_txt = f'{alic_pct:.2f}%'.rstrip('0').rstrip('.') + '%'
        if alic_txt.endswith('%%'):
            alic_txt = alic_txt[:-1]
    else:
        escala = concepto.escala_aplicable or 'General'
        tipo_escala = 'Especifica' if escala == 'Especifica' else 'General'
        impuesto = q2(_aplicar_escala(base_sujeta, tipo_escala)) if base_sujeta > 0 else ZERO
        alic_txt = f'Escala {escala}'

    retencion_neta = max(ZERO, impuesto - ret_previo)

    # ── Minimo de retencion ──
    if retencion_neta < min_ret:
        retencion_final = ZERO
    else:
        retencion_final = retencion_neta

    resultado.update({
        'aplica': retencion_final > 0,
        'motivo': '' if retencion_final > 0 else f'Retencion bajo minimo (${min_ret:.2f})',
        'acumulado_previo': acum_previo,
        'retenido_previo': ret_previo,
        'base_acumulada': base_acum,
        'mni': mni,
        'base_sujeta': base_sujeta,
        'impuesto_teorico': impuesto,
        'retencion_neta': retencion_neta,
        'minimo_retencion': min_ret,
        'retencion': retencion_final,
        'monto_neto': monto_pago_d - retencion_final,
        'alicuota_aplicada': alic_txt,
        'tipo_calculo': tipo,
        'escala_aplicable': concepto.escala_aplicable or '—',
    })
    return resultado
