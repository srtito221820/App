from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from models import db, Proveedor, MaestroTela, Partida, MovimientoTela
from utils import registrar_auditoria

bp = Blueprint('maestro', __name__)


def _parse_bool(val):
    return str(val or '').lower() in ('1', 'true', 'on', 'si', 'yes')


@bp.route('/maestro')
def maestro_list():
    proveedor_id = request.args.get('proveedor_id', type=int)
    tipo_tela = request.args.get('tipo_tela', '').strip()
    q = MaestroTela.query.filter_by(activo=True)
    if proveedor_id:
        q = q.filter(MaestroTela.proveedor_id == proveedor_id)
    if tipo_tela:
        q = q.filter(MaestroTela.tipo_tela == tipo_tela)
    telas = q.order_by(MaestroTela.tipo_tela, MaestroTela.color).all()
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    tipos_tela = [t[0] for t in db.session.query(MaestroTela.tipo_tela).distinct()
                  .order_by(MaestroTela.tipo_tela).all() if t[0]]
    return render_template('maestro/list.html',
                           telas=telas, proveedores=proveedores,
                           tipos_tela=tipos_tela,
                           proveedor_id=proveedor_id,
                           tipo_tela_sel=tipo_tela)


@bp.route('/maestro/nuevo', methods=['GET', 'POST'])
def maestro_nuevo():
    if request.method == 'POST':
        tela = MaestroTela(
            proveedor_id=request.form.get('proveedor_id', type=int) or None,
            tipo_tela=request.form.get('tipo_tela', '').strip(),
            cod_art=request.form.get('cod_art', '').strip() or None,
            color=request.form.get('color', '').strip(),
            cod_color=request.form.get('cod_color', '').strip() or None,
            descripcion=request.form.get('descripcion', '').strip() or None,
            cuenta_piezas=_parse_bool(request.form.get('cuenta_piezas')),
        )
        if not tela.tipo_tela or not tela.color:
            flash('Tipo de tela y color son obligatorios.', 'danger')
        else:
            db.session.add(tela)
            try:
                db.session.flush()
                registrar_auditoria('CREAR', 'MaestroTela', tela.id,
                                    f'{tela.tipo_tela}/{tela.color}')
                db.session.commit()
                flash('Tela agregada al maestro.', 'success')
                return redirect(url_for('maestro.maestro_list'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error: {e}', 'danger')
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    return render_template('maestro/form.html', tela=None, proveedores=proveedores)


@bp.route('/maestro/<int:id>/editar', methods=['GET', 'POST'])
def maestro_editar(id):
    tela = MaestroTela.query.get_or_404(id)
    if request.method == 'POST':
        tela.proveedor_id = request.form.get('proveedor_id', type=int) or None
        tela.tipo_tela = request.form.get('tipo_tela', '').strip()
        tela.cod_art = request.form.get('cod_art', '').strip() or None
        tela.color = request.form.get('color', '').strip()
        tela.cod_color = request.form.get('cod_color', '').strip() or None
        tela.descripcion = request.form.get('descripcion', '').strip() or None
        tela.cuenta_piezas = _parse_bool(request.form.get('cuenta_piezas'))
        try:
            registrar_auditoria('EDITAR', 'MaestroTela', tela.id,
                                f'{tela.tipo_tela}/{tela.color}')
            db.session.commit()
            flash('Tela actualizada.', 'success')
            return redirect(url_for('maestro.maestro_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    return render_template('maestro/form.html', tela=tela, proveedores=proveedores)


@bp.route('/maestro/<int:id>/eliminar', methods=['POST'])
def maestro_eliminar(id):
    tela = MaestroTela.query.get_or_404(id)
    tela.activo = False
    registrar_auditoria('ELIMINAR', 'MaestroTela', tela.id,
                        f'{tela.tipo_tela}/{tela.color}')
    db.session.commit()
    flash('Tela desactivada del maestro.', 'info')
    return redirect(url_for('maestro.maestro_list'))


@bp.route('/api/maestro/por-proveedor/<int:proveedor_id>')
def api_maestro_por_proveedor(proveedor_id):
    telas = MaestroTela.query.filter_by(proveedor_id=proveedor_id, activo=True) \
                             .order_by(MaestroTela.tipo_tela, MaestroTela.color).all()
    return jsonify([{
        'id': t.id,
        'tipo_tela': t.tipo_tela,
        'color': t.color,
        'cod_art': t.cod_art or '',
        'cod_color': t.cod_color or '',
        'descripcion': t.descripcion or '',
        'cuenta_piezas': bool(t.cuenta_piezas),
        'label': f"{t.tipo_tela} — {t.color}" + (f" ({t.cod_art})" if t.cod_art else ''),
    } for t in telas])


@bp.route('/api/maestro/<int:id>')
def api_maestro_detalle(id):
    t = MaestroTela.query.get_or_404(id)
    return jsonify({
        'id': t.id,
        'proveedor_id': t.proveedor_id,
        'tipo_tela': t.tipo_tela,
        'color': t.color,
        'cod_art': t.cod_art or '',
        'cod_color': t.cod_color or '',
        'descripcion': t.descripcion or '',
        'cuenta_piezas': bool(t.cuenta_piezas),
    })


@bp.route('/api/partidas/por-proveedor/<int:proveedor_id>')
def api_partidas_por_proveedor(proveedor_id):
    partidas = Partida.query.filter_by(proveedor_id=proveedor_id, activo=True) \
                            .order_by(Partida.fecha_alta.desc(), Partida.numero).all()
    ids = [p.id for p in partidas]
    cuenta_por_partida = {}
    if ids:
        rows = db.session.query(
            MovimientoTela.partida_id, MovimientoTela.cuenta
        ).filter(
            MovimientoTela.partida_id.in_(ids),
            MovimientoTela.movimiento == 'Ingreso',
        ).order_by(MovimientoTela.fecha.asc(), MovimientoTela.id.asc()).all()
        for pid, cuenta in rows:
            if pid not in cuenta_por_partida and cuenta:
                cuenta_por_partida[pid] = cuenta
    return jsonify([{
        'id': p.id,
        'numero': p.numero,
        'tipo_tela': p.tipo_tela or '',
        'color': p.color or '',
        'piezas_totales': p.piezas_totales or 0,
        'piezas_consumidas': p.piezas_consumidas(),
        'piezas_saldo': p.piezas_saldo(),
        'kg_totales': p.kg_totales or 0,
        'kg_saldo': p.kg_saldo(),
        'cuenta': cuenta_por_partida.get(p.id, ''),
        'label': f"{p.numero} — {p.tipo_tela}/{p.color}",
    } for p in partidas])
