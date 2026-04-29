from datetime import date
from decimal import Decimal

from flask_login import current_user

from models import db, Auditoria, Partida
from money import D, ZERO


def registrar_auditoria(accion, entidad, entidad_id, detalle=''):
    """Agrega un registro de Auditoria a la sesion (no hace commit)."""
    uid = current_user.id if current_user.is_authenticated else None
    a = Auditoria(usuario_id=uid, accion=accion, entidad=entidad,
                  entidad_id=entidad_id, detalle=detalle)
    db.session.add(a)


def obtener_o_crear_partida(numero, proveedor_id, fecha, tipo_tela, color,
                            cod_art, cod_color, piezas, cant_kg):
    """Find-or-create Partida por (proveedor, numero). Acumula pzas/kg si ya existe.

    Devuelve None si numero esta vacio. Seed de campos descriptivos solo al crear.
    """
    if not numero or not str(numero).strip():
        return None
    numero = str(numero).strip()
    p = Partida.query.filter_by(proveedor_id=proveedor_id, numero=numero).first()
    if p is None:
        p = Partida(
            numero=numero,
            proveedor_id=proveedor_id,
            tipo_tela=(tipo_tela or '').strip() or None,
            color=(color or '').strip() or None,
            cod_art=(cod_art or '').strip() or None,
            cod_color=(cod_color or '').strip() or None,
            piezas_totales=max(int(piezas or 0), 0),
            kg_totales=max(D(cant_kg), ZERO),
            fecha_alta=fecha or date.today(),
        )
        db.session.add(p)
        db.session.flush()
    else:
        p.piezas_totales = (p.piezas_totales or 0) + max(int(piezas or 0), 0)
        p.kg_totales = D(p.kg_totales) + max(D(cant_kg), ZERO)
    return p
