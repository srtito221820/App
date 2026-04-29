from flask import Blueprint, render_template, request, redirect, url_for, flash

from models import db, Proveedor, ConceptoRetencionGanancias
from utils import registrar_auditoria

bp = Blueprint('proveedores', __name__, url_prefix='/proveedores')


@bp.route('')
def proveedores_list():
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    return render_template('proveedores/list.html', proveedores=proveedores)


@bp.route('/nuevo', methods=['GET', 'POST'])
def proveedor_nuevo():
    if request.method == 'POST':
        concepto_id = request.form.get('concepto_retencion_id') or None
        p = Proveedor(
            nombre=request.form['nombre'],
            cuit=request.form.get('cuit', ''),
            categoria=request.form.get('categoria', ''),
            condicion_pago_dias=int(request.form.get('condicion_pago_dias', 30)),
            usa_cuentas_asignacion=bool(request.form.get('usa_cuentas_asignacion')),
            condicion_ganancias=request.form.get('condicion_ganancias', 'No Aplica'),
            concepto_retencion_id=int(concepto_id) if concepto_id else None,
        )
        db.session.add(p)
        db.session.flush()
        registrar_auditoria('Crear', 'Proveedor', p.id, f'Proveedor: {p.nombre}')
        db.session.commit()
        flash(f'Proveedor "{p.nombre}" creado correctamente.', 'success')
        return redirect(url_for('proveedores.proveedores_list'))
    conceptos = ConceptoRetencionGanancias.query.filter_by(activo=True).order_by(ConceptoRetencionGanancias.codigo).all()
    return render_template('proveedores/form.html', proveedor=None, conceptos=conceptos)


@bp.route('/<int:id>/editar', methods=['GET', 'POST'])
def proveedor_editar(id):
    p = Proveedor.query.get_or_404(id)
    if request.method == 'POST':
        concepto_id = request.form.get('concepto_retencion_id') or None
        p.nombre = request.form['nombre']
        p.cuit = request.form.get('cuit', '')
        p.categoria = request.form.get('categoria', '')
        p.condicion_pago_dias = int(request.form.get('condicion_pago_dias', 30))
        p.usa_cuentas_asignacion = bool(request.form.get('usa_cuentas_asignacion'))
        p.condicion_ganancias = request.form.get('condicion_ganancias', 'No Aplica')
        p.concepto_retencion_id = int(concepto_id) if concepto_id else None
        registrar_auditoria('Editar', 'Proveedor', p.id, f'Proveedor: {p.nombre}')
        db.session.commit()
        flash(f'Proveedor "{p.nombre}" actualizado.', 'success')
        return redirect(url_for('proveedores.proveedores_list'))
    conceptos = ConceptoRetencionGanancias.query.filter_by(activo=True).order_by(ConceptoRetencionGanancias.codigo).all()
    return render_template('proveedores/form.html', proveedor=p, conceptos=conceptos)


@bp.route('/<int:id>/eliminar', methods=['POST'])
def proveedor_eliminar(id):
    p = Proveedor.query.get_or_404(id)
    p.activo = False
    db.session.commit()
    flash(f'Proveedor "{p.nombre}" desactivado.', 'warning')
    return redirect(url_for('proveedores.proveedores_list'))
