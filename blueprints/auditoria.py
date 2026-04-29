from flask import Blueprint, render_template, request
from sqlalchemy.orm import joinedload

from models import Auditoria

bp = Blueprint('auditoria', __name__, url_prefix='/auditoria')


@bp.route('')
def auditoria_list():
    pagina = request.args.get('pagina', 1, type=int)
    entidad_f = request.args.get('entidad', '')
    accion_f = request.args.get('accion', '')
    por_pagina = 50

    query = Auditoria.query.options(joinedload(Auditoria.usuario)).order_by(Auditoria.fecha.desc())
    if entidad_f:
        query = query.filter(Auditoria.entidad == entidad_f)
    if accion_f:
        query = query.filter(Auditoria.accion == accion_f)

    total = query.count()
    registros = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    total_paginas = (total + por_pagina - 1) // por_pagina

    return render_template('auditoria/list.html', registros=registros,
                           pagina=pagina, total_paginas=total_paginas, total=total,
                           entidad_f=entidad_f, accion_f=accion_f)
