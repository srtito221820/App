import os
from decimal import Decimal, ROUND_HALF_UP
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv opcional; si no esta instalado se usan las variables del sistema y los fallbacks

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from models import (
    db, Usuario, Proveedor, MovimientoTela, CuentaCorriente, Anticipo,
)
from retenciones import seed_datos_iniciales

from blueprints.auth import bp as auth_bp
from blueprints.auditoria import bp as auditoria_bp
from blueprints.proveedores import bp as proveedores_bp
from blueprints.movimientos import bp as movimientos_bp
from blueprints.cuenta_corriente import bp as cuenta_corriente_bp
from blueprints.anticipos import bp as anticipos_bp
from blueprints.pedidos import bp as pedidos_bp
from blueprints.stock import bp as stock_bp
from blueprints.facturas import bp as facturas_bp
from blueprints.pagos import bp as pagos_bp
from blueprints.impuestos import bp as impuestos_bp
from blueprints.maestro import bp as maestro_bp
from blueprints.consumos import bp as consumos_bp
from blueprints.notas_credito import bp as notas_credito_bp
from blueprints.panel import bp as panel_bp
from blueprints.exportar import bp as exportar_bp
from blueprints.compras import bp as compras_bp


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv('DATABASE_PATH') or os.path.join(BASE_DIR, 'instance', 'inventory.db')

# Asegurar que el directorio de la base de datos exista
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

_SECRET_KEY = os.getenv('SECRET_KEY')
if not _SECRET_KEY or _SECRET_KEY.strip() in ('', 'cambiar-por-un-valor-aleatorio'):
    raise RuntimeError(
        "SECRET_KEY no configurada. Copie .env.example a .env y complete SECRET_KEY "
        "(generar con: python -c \"import secrets; print(secrets.token_hex(32))\")."
    )

app = Flask(__name__)
app.config['SECRET_KEY'] = _SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_TIME_LIMIT'] = None

db.init_app(app)
# render_as_batch=True: requerido por SQLite para soportar ALTER TABLE
# (Alembic recrea la tabla bajo el capot cuando hace falta).
migrate = Migrate(app, db, render_as_batch=True)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Debe iniciar sesion para acceder.'
login_manager.login_message_category = 'warning'

app.register_blueprint(auth_bp)
app.register_blueprint(auditoria_bp)
app.register_blueprint(proveedores_bp)
app.register_blueprint(movimientos_bp)
app.register_blueprint(cuenta_corriente_bp)
app.register_blueprint(anticipos_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(stock_bp)
app.register_blueprint(facturas_bp)
app.register_blueprint(pagos_bp)
app.register_blueprint(impuestos_bp)
app.register_blueprint(maestro_bp)
app.register_blueprint(consumos_bp)
app.register_blueprint(notas_credito_bp)
app.register_blueprint(panel_bp)
app.register_blueprint(exportar_bp)
app.register_blueprint(compras_bp)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))


def _seed_inicial():
    """Siembra usuarios + datos de retenciones. Idempotente.

    Se llama al arrancar la app y desde el comando CLI `flask seed`.
    Si las tablas no existen aun, se aborta con instrucciones.
    """
    from sqlalchemy import inspect
    if not inspect(db.engine).has_table('usuarios'):
        print('[seed] Tablas no encontradas. Ejecutar primero: flask db upgrade')
        return
    _seed_users = (
        ('Admin', 'Administrador', 'ADMIN_PASSWORD'),
        ('Juan', 'Juan', 'JUAN_PASSWORD'),
        ('Ricardo', 'Ricardo', 'RICARDO_PASSWORD'),
    )
    for _username, _nombre, _env in _seed_users:
        if Usuario.query.filter_by(username=_username).first():
            continue
        _pwd = os.getenv(_env)
        if not _pwd:
            print(f"[seed] {_env} no configurada en .env; se omite creacion de '{_username}'.")
            continue
        _u = Usuario(username=_username, nombre=_nombre)
        _u.set_password(_pwd)
        db.session.add(_u)
    db.session.commit()
    seed_datos_iniciales()


@app.cli.command('seed')
def seed_command():
    """Siembra usuarios iniciales y datos de retenciones."""
    _seed_inicial()


# Bootstrap manual (idempotente). Ejecutar UNA VEZ al desplegar:
#   1) flask db upgrade  -> crea/actualiza tablas
#   2) flask seed        -> usuarios y datos de retenciones
# Antes _seed_inicial() corria automaticamente en cada arranque tocando la DB
# innecesariamente; ahora se ejecuta solo via el comando CLI explicito.


def _fmt_ar(value, decimals=2):
    """Formato argentino: punto para miles, coma para decimales (ej: 10.000,50).

    Acepta Decimal, float, int, str. Cuantiza al numero de decimales pedido.
    """
    from money import D
    quantum = Decimal(10) ** -decimals if decimals > 0 else Decimal(1)
    d = D(value).quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{d:,.{decimals}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@app.template_filter('currency')
def currency_filter(value):
    try:
        return f"${_fmt_ar(value, 2)}"
    except (ValueError, TypeError):
        return "$0,00"


@app.template_filter('number')
def number_filter(value):
    try:
        return _fmt_ar(value, 2)
    except (ValueError, TypeError):
        return "0,00"


@app.template_filter('integer')
def integer_filter(value):
    try:
        return _fmt_ar(value, 0)
    except (ValueError, TypeError):
        return "0"


@app.before_request
def require_login():
    allowed = ('auth.login', 'static')
    if not request.endpoint or request.endpoint in allowed or current_user.is_authenticated:
        return
    # Rutas /api/* devuelven 401 JSON para que los fetch() del front no
    # reciban un redirect 302 al HTML del login y rompan al parsear.
    if request.path.startswith('/api/'):
        return jsonify(error='auth required'), 401
    return redirect(url_for('auth.login', next=request.url))


@app.teardown_request
def _rollback_on_exception(exc):
    """Si la view rompio con cualquier excepcion, descarta la sesion abierta
    para que el siguiente request arranque limpio (sin objetos sucios).

    Se complementa con el errorhandler de abajo, que ademas avisa al usuario
    cuando el problema vino de la base.
    """
    if exc is not None:
        db.session.rollback()


@app.errorhandler(SQLAlchemyError)
def _handle_db_error(exc):
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify(error='db error', detail=str(exc)), 500
    flash('Error de base de datos: la operacion fue cancelada. '
          'Verifica los datos e intenta de nuevo.', 'danger')
    # Volvemos al referrer (panel/listado) en vez de tirar 500 al usuario.
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/')
def dashboard():
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()

    stock_tela = db.session.query(
        MovimientoTela.tipo_tela,
        db.func.sum(MovimientoTela.cant_kg).label('total_kg'),
        db.func.count(MovimientoTela.id).label('movimientos')
    ).group_by(MovimientoTela.tipo_tela).all()

    from money import D, ZERO
    saldos_agg = {
        row.proveedor_id: (D(row.debe), D(row.haber))
        for row in db.session.query(
            CuentaCorriente.proveedor_id,
            db.func.coalesce(db.func.sum(CuentaCorriente.debe), 0).label('debe'),
            db.func.coalesce(db.func.sum(CuentaCorriente.haber), 0).label('haber'),
        ).group_by(CuentaCorriente.proveedor_id).all()
    }
    saldos = []
    for p in proveedores:
        debe, haber = saldos_agg.get(p.id, (ZERO, ZERO))
        saldo = debe - haber
        if saldo != 0:
            saldos.append({'proveedor': p, 'debe': debe, 'haber': haber, 'saldo': saldo})
    saldos.sort(key=lambda x: x['saldo'], reverse=True)

    anticipos_abiertos = (
        Anticipo.query
        .options(joinedload(Anticipo.proveedor))
        .filter_by(estado='Abierto')
        .order_by(Anticipo.fecha.desc())
        .all()
    )
    anticipo_ids = [a.id for a in anticipos_abiertos]
    mov_agg = {
        row.anticipo_id: (D(row.kg), D(row.valor))
        for row in db.session.query(
            MovimientoTela.anticipo_id,
            db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0).label('kg'),
            db.func.coalesce(db.func.sum(MovimientoTela.subtotal_iva), 0).label('valor'),
        ).filter(MovimientoTela.anticipo_id.in_(anticipo_ids)).group_by(MovimientoTela.anticipo_id).all()
    } if anticipo_ids else {}
    resumen_anticipos = []
    for a in anticipos_abiertos:
        kg_entregados, valor_entregado = mov_agg.get(a.id, (ZERO, ZERO))
        kg_anticipo = D(a.cant_kg)
        monto_anticipo = D(a.monto)
        resumen_anticipos.append({
            'anticipo': a,
            'proveedor': a.proveedor,
            'monto': monto_anticipo,
            'kg_anticipo': kg_anticipo,
            'kg_entregados': kg_entregados,
            'kg_pendientes': kg_anticipo - kg_entregados,
            'valor_entregado': valor_entregado,
            'pendiente': monto_anticipo - valor_entregado,
        })

    total_anticipos_monto = sum((r['monto'] for r in resumen_anticipos), ZERO)
    total_anticipos_entregado = sum((r['valor_entregado'] for r in resumen_anticipos), ZERO)
    total_anticipos_pendiente = sum((r['pendiente'] for r in resumen_anticipos), ZERO)
    total_anticipos_kg = sum((r['kg_entregados'] for r in resumen_anticipos), ZERO)
    total_anticipos_kg_anticipo = sum((r['kg_anticipo'] for r in resumen_anticipos), ZERO)
    total_anticipos_kg_pendientes = sum((r['kg_pendientes'] for r in resumen_anticipos), ZERO)

    ultimos_movimientos = MovimientoTela.query.options(
        joinedload(MovimientoTela.proveedor)
    ).order_by(MovimientoTela.fecha.desc()).limit(10).all()

    total_kg = db.session.query(
        db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0)
    ).scalar()

    total_proveedores = Proveedor.query.filter_by(activo=True).count()

    return render_template('dashboard.html',
                           stock_tela=stock_tela,
                           saldos=saldos,
                           proveedores=proveedores,
                           ultimos_movimientos=ultimos_movimientos,
                           total_kg=total_kg,
                           total_proveedores=total_proveedores,
                           resumen_anticipos=resumen_anticipos,
                           total_anticipos_monto=total_anticipos_monto,
                           total_anticipos_entregado=total_anticipos_entregado,
                           total_anticipos_pendiente=total_anticipos_pendiente,
                           total_anticipos_kg=total_anticipos_kg,
                           total_anticipos_kg_anticipo=total_anticipos_kg_anticipo,
                           total_anticipos_kg_pendientes=total_anticipos_kg_pendientes)


if __name__ == '__main__':
    # FLASK_DEBUG=1 habilita debugger/reloader (solo desarrollo, nunca en red abierta).
    # FLASK_HOST default 127.0.0.1 para evitar exponer el debugger a la LAN por accidente.
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', '5000'))
    app.run(host=host, port=port, debug=debug)
