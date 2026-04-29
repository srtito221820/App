from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import case, func

from models import db, Proveedor, MovimientoTela

bp = Blueprint('stock', __name__)

TELAS_SIN_PIEZAS = {'MORLEY', 'RIBB', 'REEB'}


@bp.route('/stock')
def stock():
    proveedor_id = request.args.get('proveedor_id', type=int)
    tipo_tela = request.args.get('tipo_tela', '').strip()
    color = request.args.get('color', '').strip()
    cod_art = request.args.get('cod_art', '').strip()
    cod_color = request.args.get('cod_color', '').strip()
    cuenta_sel = request.args.get('cuenta', '').strip()
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    tipos_tela = [t[0] for t in db.session.query(MovimientoTela.tipo_tela).distinct().order_by(MovimientoTela.tipo_tela).all() if t[0]]
    colores = [c[0] for c in db.session.query(MovimientoTela.color).distinct().order_by(MovimientoTela.color).all() if c[0]]
    cod_arts = [c[0] for c in db.session.query(MovimientoTela.cod_art).distinct().order_by(MovimientoTela.cod_art).all() if c[0]]
    cod_colors = [c[0] for c in db.session.query(MovimientoTela.cod_color).distinct().order_by(MovimientoTela.cod_color).all() if c[0]]

    query = db.session.query(
        MovimientoTela.tipo_tela,
        MovimientoTela.color,
        MovimientoTela.cod_art,
        MovimientoTela.cod_color,
        MovimientoTela.proveedor_id,
        Proveedor.nombre.label('proveedor_nombre'),
        db.func.sum(MovimientoTela.cant_kg).label('total_kg'),
        db.func.sum(MovimientoTela.piezas).label('total_piezas'),
    ).join(Proveedor).group_by(
        MovimientoTela.tipo_tela,
        MovimientoTela.color,
        MovimientoTela.cod_art,
        MovimientoTela.cod_color,
        MovimientoTela.proveedor_id,
        Proveedor.nombre
    )

    if proveedor_id:
        query = query.filter(MovimientoTela.proveedor_id == proveedor_id)
    if tipo_tela:
        query = query.filter(MovimientoTela.tipo_tela == tipo_tela)
    if color:
        query = query.filter(MovimientoTela.color == color)
    if cod_art:
        query = query.filter(MovimientoTela.cod_art == cod_art)
    if cod_color:
        query = query.filter(MovimientoTela.cod_color == cod_color)
    if cuenta_sel:
        query = query.filter(MovimientoTela.cuenta == cuenta_sel)

    stock_items = query.order_by(MovimientoTela.tipo_tela, MovimientoTela.color).all()

    total_kg = sum((it.total_kg or 0) for it in stock_items)
    total_kg_sin_morley_ribb = sum(
        (it.total_kg or 0) for it in stock_items
        if (it.tipo_tela or '').upper() not in TELAS_SIN_PIEZAS
    )
    total_piezas = sum(
        (it.total_piezas or 0) for it in stock_items
        if (it.tipo_tela or '').upper() not in TELAS_SIN_PIEZAS
    )

    return render_template('stock/list.html',
                           stock_items=stock_items,
                           proveedores=proveedores,
                           proveedor_id=proveedor_id,
                           tipos_tela=tipos_tela,
                           colores=colores,
                           cod_arts=cod_arts,
                           cod_colors=cod_colors,
                           tipo_tela_sel=tipo_tela,
                           color_sel=color,
                           cod_art_sel=cod_art,
                           cod_color_sel=cod_color,
                           cuenta_sel=cuenta_sel,
                           total_kg=total_kg,
                           total_kg_sin_morley_ribb=total_kg_sin_morley_ribb,
                           total_piezas=total_piezas,
                           telas_sin_piezas=TELAS_SIN_PIEZAS)


@bp.route('/stock/cuentas')
def stock_cuentas():
    proveedor_id = request.args.get('proveedor_id', type=int)
    tipo_tela = request.args.get('tipo_tela', '').strip()

    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    tipos_tela = [t[0] for t in db.session.query(MovimientoTela.tipo_tela).distinct()
                  .order_by(MovimientoTela.tipo_tela).all() if t[0]]

    # Pivot por cuenta (JUMAF / JUMASA / SC) hecho en SQL con CASE WHEN.
    # Antes traiamos una fila por (tipo,color,art,cuenta) y haciamos el rollup
    # en Python; ahora la base devuelve las 3 columnas ya sumadas en una sola
    # fila por (tipo,color,art).
    cuenta_norm = func.upper(func.coalesce(MovimientoTela.cuenta, ''))
    sum_kg = func.coalesce(func.sum(MovimientoTela.cant_kg), 0)
    sum_pz = func.coalesce(func.sum(MovimientoTela.piezas), 0)

    def _kg_when(valor):
        return func.coalesce(func.sum(case((cuenta_norm == valor, MovimientoTela.cant_kg), else_=0)), 0)

    def _pz_when(valor):
        return func.coalesce(func.sum(case((cuenta_norm == valor, MovimientoTela.piezas), else_=0)), 0)

    def _kg_else():
        return func.coalesce(func.sum(case(
            (cuenta_norm.in_(('JUMAF', 'JUMASA')), 0), else_=MovimientoTela.cant_kg
        )), 0)

    def _pz_else():
        return func.coalesce(func.sum(case(
            (cuenta_norm.in_(('JUMAF', 'JUMASA')), 0), else_=MovimientoTela.piezas
        )), 0)

    q = db.session.query(
        MovimientoTela.tipo_tela,
        MovimientoTela.color,
        MovimientoTela.cod_art,
        Proveedor.nombre.label('proveedor_nombre'),
        MovimientoTela.proveedor_id,
        _kg_when('JUMAF').label('jumaf_kg'),
        _pz_when('JUMAF').label('jumaf_pzas'),
        _kg_when('JUMASA').label('jumasa_kg'),
        _pz_when('JUMASA').label('jumasa_pzas'),
        _kg_else().label('sc_kg'),
        _pz_else().label('sc_pzas'),
        sum_kg.label('total_kg'),
        sum_pz.label('total_piezas'),
    ).join(Proveedor).group_by(
        MovimientoTela.tipo_tela,
        MovimientoTela.color,
        MovimientoTela.cod_art,
        Proveedor.nombre,
        MovimientoTela.proveedor_id,
    ).order_by(MovimientoTela.tipo_tela, MovimientoTela.color)
    if proveedor_id:
        q = q.filter(MovimientoTela.proveedor_id == proveedor_id)
    if tipo_tela:
        q = q.filter(MovimientoTela.tipo_tela == tipo_tela)

    items = []
    for r in q.all():
        items.append({
            'tipo_tela': r.tipo_tela or '',
            'color': r.color or '',
            'cod_art': r.cod_art or '',
            'proveedor_id': r.proveedor_id,
            'proveedor_nombre': r.proveedor_nombre,
            'jumaf_kg': r.jumaf_kg or 0,   'jumaf_pzas': r.jumaf_pzas or 0,
            'jumasa_kg': r.jumasa_kg or 0, 'jumasa_pzas': r.jumasa_pzas or 0,
            'sc_kg': r.sc_kg or 0,         'sc_pzas': r.sc_pzas or 0,
            'total_kg': r.total_kg or 0,   'total_piezas': r.total_piezas or 0,
            'cuenta_piezas': (r.tipo_tela or '').upper() not in TELAS_SIN_PIEZAS,
        })

    tot_jumaf = sum(i['jumaf_kg'] for i in items)
    tot_jumasa = sum(i['jumasa_kg'] for i in items)
    tot_sc = sum(i['sc_kg'] for i in items)
    tot_general = tot_jumaf + tot_jumasa + tot_sc
    tot_sin_mr = sum(i['total_kg'] for i in items if i['cuenta_piezas'])

    return render_template('stock/cuentas.html',
                           items=items,
                           proveedores=proveedores, tipos_tela=tipos_tela,
                           proveedor_id=proveedor_id, tipo_tela_sel=tipo_tela,
                           tot_jumaf=tot_jumaf, tot_jumasa=tot_jumasa, tot_sc=tot_sc,
                           tot_general=tot_general, tot_sin_mr=tot_sin_mr)


@bp.route('/api/colores')
def api_colores():
    colores = db.session.query(MovimientoTela.color).distinct().all()
    return jsonify([c[0] for c in colores if c[0]])


@bp.route('/api/stock-detalle')
def api_stock_detalle():
    tipo_tela = request.args.get('tipo_tela', '')
    color = request.args.get('color', '')
    proveedor_id = request.args.get('proveedor_id', type=int)
    cod_art = request.args.get('cod_art', '')
    cod_color = request.args.get('cod_color', '')

    query = MovimientoTela.query.filter(
        MovimientoTela.tipo_tela == tipo_tela,
        MovimientoTela.color == color,
        MovimientoTela.proveedor_id == proveedor_id,
    )
    if cod_art:
        query = query.filter(MovimientoTela.cod_art == cod_art)
    if cod_color:
        query = query.filter(MovimientoTela.cod_color == cod_color)

    movs = query.order_by(MovimientoTela.fecha).all()
    result = []
    saldo_kg = 0
    for m in movs:
        saldo_kg += m.cant_kg or 0
        result.append({
            'fecha': m.fecha.strftime('%d/%m/%Y'),
            'remito': m.remito_factura or '-',
            'movimiento': m.movimiento or 'Ingreso',
            'kg': m.cant_kg or 0,
            'piezas': m.piezas or 0,
            'precio': m.precio_sin_iva or 0,
            'subtotal_iva': m.subtotal_iva or 0,
            'saldo_kg': saldo_kg,
            'anticipo': m.anticipo.numero if m.anticipo else '',
            'pedido': m.pedido.numero if m.pedido else '',
        })
    return jsonify(result)


@bp.route('/api/tipos-tela')
def api_tipos_tela():
    tipos = db.session.query(MovimientoTela.tipo_tela).distinct().all()
    return jsonify([t[0] for t in tipos if t[0]])
