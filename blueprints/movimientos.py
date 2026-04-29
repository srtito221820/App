from flask import Blueprint, render_template, request
from sqlalchemy.orm import joinedload

from models import db, Proveedor, MovimientoTela

bp = Blueprint('movimientos', __name__, url_prefix='/movimientos')


@bp.route('')
def movimientos_list():
    page = request.args.get('page', 1, type=int)
    proveedor_id = request.args.get('proveedor_id', type=int)
    tipo_tela = request.args.get('tipo_tela', '')
    movimiento = request.args.get('movimiento', '')
    temporada = request.args.get('temporada', '')

    query = MovimientoTela.query

    if proveedor_id:
        query = query.filter_by(proveedor_id=proveedor_id)
    if tipo_tela:
        query = query.filter_by(tipo_tela=tipo_tela)
    if movimiento:
        query = query.filter_by(movimiento=movimiento)
    if temporada:
        query = query.filter_by(temporada=temporada)

    movimientos = query.options(
        joinedload(MovimientoTela.proveedor),
        joinedload(MovimientoTela.anticipo),
    ).order_by(MovimientoTela.fecha.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    tipos_tela = db.session.query(MovimientoTela.tipo_tela).distinct().all()
    tipos_tela = [t[0] for t in tipos_tela if t[0]]

    temporadas = db.session.query(MovimientoTela.temporada).distinct().all()
    temporadas = [t[0] for t in temporadas if t[0]]

    return render_template('movimientos/list.html',
                           movimientos=movimientos,
                           proveedores=proveedores,
                           tipos_tela=tipos_tela,
                           temporadas=temporadas,
                           filtros={
                               'proveedor_id': proveedor_id,
                               'tipo_tela': tipo_tela,
                               'movimiento': movimiento,
                               'temporada': temporada
                           })
