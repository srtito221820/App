from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from models import (db, Anticipo, Pedido, PedidoDetalle, MovimientoTela)
from money import D, ZERO, q2, parse_money, parse_kg
from utils import registrar_auditoria

bp = Blueprint('pedidos', __name__)


@bp.route('/pedido/nuevo/<int:anticipo_id>', methods=['GET', 'POST'])
def pedido_nuevo(anticipo_id):
    anticipo = Anticipo.query.get_or_404(anticipo_id)
    if request.method == 'POST':
        kgs = request.form.getlist('cant_kg[]')
        precios = request.form.getlist('precio[]')
        total_kg_nuevo = sum((parse_kg(k) for k in kgs), ZERO)
        total_val_nuevo = sum((parse_kg(k) * parse_money(p) for k, p in zip(kgs, precios)), ZERO)

        kg_ya_pedidos = D(anticipo.total_kg_pedidos())
        val_ya_pedidos = D(anticipo.total_valor_pedidos())
        kg_disponible = D(anticipo.cant_kg) - kg_ya_pedidos
        val_disponible = D(anticipo.monto) - val_ya_pedidos

        if D(anticipo.cant_kg) > 0 and total_kg_nuevo > kg_disponible:
            flash(f'No se puede crear el pedido: solicitas {total_kg_nuevo:.2f} kg pero solo hay {kg_disponible:.2f} kg disponibles para pedir (anticipo: {D(anticipo.cant_kg):.2f} kg, ya pedidos: {kg_ya_pedidos:.2f} kg).', 'danger')
            return redirect(url_for('pedidos.pedido_nuevo', anticipo_id=anticipo_id))

        if D(anticipo.monto) > 0 and total_val_nuevo > val_disponible:
            flash(f'No se puede crear el pedido: el importe ${total_val_nuevo:,.2f} excede los ${val_disponible:,.2f} disponibles para pedir (anticipo: ${D(anticipo.monto):,.2f}, ya pedidos: ${val_ya_pedidos:,.2f}).', 'danger')
            return redirect(url_for('pedidos.pedido_nuevo', anticipo_id=anticipo_id))

        numero = request.form['numero']
        dup = Pedido.query.filter_by(anticipo_id=anticipo_id, numero=numero).first()
        if dup:
            flash(f'Ya existe un pedido "{numero}" en este anticipo.', 'danger')
            return redirect(url_for('pedidos.pedido_nuevo', anticipo_id=anticipo_id))

        p = Pedido(
            numero=numero,
            fecha=date.fromisoformat(request.form['fecha']),
            anticipo_id=anticipo_id,
            observaciones=request.form.get('observaciones', ''),
        )
        db.session.add(p)
        db.session.flush()

        tipos = request.form.getlist('tipo_tela[]')
        colores = request.form.getlist('color[]')
        cod_arts = request.form.getlist('cod_art[]')
        cod_colors = request.form.getlist('cod_color[]')
        subtotales = request.form.getlist('subtotal[]')

        for i in range(len(tipos)):
            kg = parse_kg(kgs[i] if i < len(kgs) else None)
            precio = parse_money(precios[i] if i < len(precios) else None)
            if kg > 0 or precio > 0:
                subtotal_form = parse_money(subtotales[i]) if i < len(subtotales) else None
                subtotal_final = subtotal_form if subtotal_form else q2(kg * precio)
                det = PedidoDetalle(
                    pedido_id=p.id,
                    tipo_tela=tipos[i],
                    color=colores[i],
                    cod_art=cod_arts[i] if i < len(cod_arts) else '',
                    cod_color=cod_colors[i] if i < len(cod_colors) else '',
                    cant_kg=kg,
                    precio_unitario=precio,
                    subtotal=subtotal_final,
                )
                db.session.add(det)

        registrar_auditoria('Crear', 'Pedido', p.id, f'Pedido {p.numero} anticipo {anticipo.numero}')
        db.session.commit()
        flash(f'Pedido "{p.numero}" creado.', 'success')
        return redirect(url_for('panel.panel', proveedor_id=anticipo.proveedor_id, vista='anticipos'))

    return render_template('panel/pedido_form.html', anticipo=anticipo, pedido=None, today=date.today().isoformat())


@bp.route('/pedido/<int:id>/editar', methods=['GET', 'POST'])
def pedido_editar(id):
    p = Pedido.query.get_or_404(id)
    anticipo = p.anticipo
    if request.method == 'POST':
        kgs = request.form.getlist('cant_kg[]')
        precios = request.form.getlist('precio[]')
        total_kg_nuevo = sum((parse_kg(k) for k in kgs), ZERO)
        total_val_nuevo = sum((parse_kg(k) * parse_money(pr) for k, pr in zip(kgs, precios)), ZERO)

        kg_otros = D(anticipo.total_kg_pedidos()) - D(p.total_kg())
        val_otros = D(anticipo.total_valor_pedidos()) - D(p.total_valor())
        kg_disponible = D(anticipo.cant_kg) - kg_otros
        val_disponible = D(anticipo.monto) - val_otros

        if D(anticipo.cant_kg) > 0 and total_kg_nuevo > kg_disponible:
            flash(f'No se puede guardar: solicitas {total_kg_nuevo:.2f} kg pero solo hay {kg_disponible:.2f} kg disponibles.', 'danger')
            return redirect(url_for('pedidos.pedido_editar', id=id))

        if D(anticipo.monto) > 0 and total_val_nuevo > val_disponible:
            flash(f'No se puede guardar: el importe ${total_val_nuevo:,.2f} excede los ${val_disponible:,.2f} disponibles.', 'danger')
            return redirect(url_for('pedidos.pedido_editar', id=id))

        numero = request.form['numero']
        dup = Pedido.query.filter(
            Pedido.anticipo_id == anticipo.id,
            Pedido.numero == numero,
            Pedido.id != p.id
        ).first()
        if dup:
            flash(f'Ya existe otro pedido "{numero}" en este anticipo.', 'danger')
            return redirect(url_for('pedidos.pedido_editar', id=id))

        p.numero = numero
        p.fecha = date.fromisoformat(request.form['fecha'])
        p.observaciones = request.form.get('observaciones', '')
        p.estado = request.form.get('estado', 'Pendiente')

        PedidoDetalle.query.filter_by(pedido_id=p.id).delete()

        tipos = request.form.getlist('tipo_tela[]')
        colores = request.form.getlist('color[]')
        cod_arts = request.form.getlist('cod_art[]')
        cod_colors = request.form.getlist('cod_color[]')
        subtotales = request.form.getlist('subtotal[]')

        for i in range(len(tipos)):
            kg = parse_kg(kgs[i] if i < len(kgs) else None)
            precio = parse_money(precios[i] if i < len(precios) else None)
            if kg > 0 or precio > 0:
                subtotal_form = parse_money(subtotales[i]) if i < len(subtotales) else None
                subtotal_final = subtotal_form if subtotal_form else q2(kg * precio)
                det = PedidoDetalle(
                    pedido_id=p.id,
                    tipo_tela=tipos[i],
                    color=colores[i],
                    cod_art=cod_arts[i] if i < len(cod_arts) else '',
                    cod_color=cod_colors[i] if i < len(cod_colors) else '',
                    cant_kg=kg,
                    precio_unitario=precio,
                    subtotal=subtotal_final,
                )
                db.session.add(det)

        registrar_auditoria('Editar', 'Pedido', p.id, f'Pedido {p.numero} anticipo {anticipo.numero}')
        db.session.commit()
        flash(f'Pedido "{p.numero}" actualizado.', 'success')
        return redirect(url_for('panel.panel', proveedor_id=anticipo.proveedor_id, vista='anticipos'))

    return render_template('panel/pedido_form.html', anticipo=anticipo, pedido=p, today=date.today().isoformat())


@bp.route('/pedido/<int:id>/detalle')
def pedido_detalle(id):
    p = Pedido.query.get_or_404(id)
    return render_template('panel/pedido_detalle.html', pedido=p, anticipo=p.anticipo)


@bp.route('/pedido/<int:id>/eliminar', methods=['POST'])
def pedido_eliminar(id):
    p = Pedido.query.get_or_404(id)
    pid = p.anticipo.proveedor_id
    MovimientoTela.query.filter_by(pedido_id=id).update({'pedido_id': None})
    registrar_auditoria('Eliminar', 'Pedido', p.id, f'Pedido {p.numero}')
    db.session.delete(p)
    db.session.commit()
    flash('Pedido eliminado.', 'warning')
    return redirect(url_for('panel.panel', proveedor_id=pid, vista='anticipos'))


@bp.route('/api/pedido/<int:pedido_id>/detalles')
def api_pedido_detalles(pedido_id):
    Pedido.query.get_or_404(pedido_id)
    detalles = PedidoDetalle.query.filter_by(pedido_id=pedido_id).all()
    return jsonify([{
        'id': d.id,
        'tipo_tela': d.tipo_tela,
        'color': d.color,
        'cod_art': d.cod_art or '',
        'cod_color': d.cod_color or '',
        'cant_kg': d.cant_kg,
        'precio_unitario': d.precio_unitario,
    } for d in detalles])
