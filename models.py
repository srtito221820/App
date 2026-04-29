from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    nombre = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Proveedor(db.Model):
    __tablename__ = 'proveedores'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    cuit = db.Column(db.String(20))
    categoria = db.Column(db.String(100))
    condicion_pago_dias = db.Column(db.Integer, default=30)
    usa_cuentas_asignacion = db.Column(db.Boolean, default=False)
    # Retenciones Ganancias (RG 830)
    condicion_ganancias = db.Column(db.String(20), default='No Aplica')  # Inscripto, No Inscripto, Exento, No Aplica
    concepto_retencion_id = db.Column(db.Integer, db.ForeignKey('conceptos_retencion_ganancias.id'), nullable=True)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    movimientos = db.relationship('MovimientoTela', backref='proveedor', lazy='dynamic')
    cuenta_corriente = db.relationship('CuentaCorriente', backref='proveedor', lazy='dynamic')
    anticipos = db.relationship('Anticipo', backref='proveedor', lazy='dynamic')
    retenciones = db.relationship('RetencionGanancias', backref='proveedor', lazy='dynamic')
    concepto_retencion = db.relationship('ConceptoRetencionGanancias', foreign_keys=[concepto_retencion_id])

    def saldo_cuenta_corriente(self, cuenta=None):
        q = db.session.query(
            db.func.coalesce(db.func.sum(CuentaCorriente.debe), 0) -
            db.func.coalesce(db.func.sum(CuentaCorriente.haber), 0)
        ).filter(CuentaCorriente.proveedor_id == self.id)
        if cuenta:
            q = q.filter(CuentaCorriente.cuenta == cuenta)
        return q.scalar() or 0

    def __repr__(self):
        return f'<Proveedor {self.nombre}>'


class MovimientoTela(db.Model):
    __tablename__ = 'movimientos_tela'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    cuenta = db.Column(db.String(20))  # JUMAF, JUMASA
    remito_factura = db.Column(db.String(50))
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=False)
    cuenta_pedido = db.Column(db.String(50))
    tipo_tela = db.Column(db.String(50), index=True)
    descripcion = db.Column(db.String(200))
    color = db.Column(db.String(100))
    cod_art = db.Column(db.String(20))
    cod_color = db.Column(db.String(20))
    cant_kg = db.Column(db.Numeric(12, 3), default=0)
    piezas = db.Column(db.Integer, default=0)
    partida = db.Column(db.String(50))
    precio_sin_iva = db.Column(db.Numeric(14, 2), default=0)
    precio_con_iva = db.Column(db.Numeric(14, 2), default=0)
    subtotal = db.Column(db.Numeric(14, 2), default=0)
    percp_iva = db.Column(db.Numeric(14, 2), default=0)
    percp_iibb = db.Column(db.Numeric(14, 2), default=0)
    subtotal_iva = db.Column(db.Numeric(14, 2), default=0)
    dif_kg = db.Column(db.Numeric(12, 3), default=0)
    movimiento = db.Column(db.String(20), default='Ingreso', index=True)  # Ingreso, Devolucion, Reposicion, Consumo
    estado = db.Column(db.String(30))  # Pendiente de retiro, Retirado, Pendiente NC, NC Aplicada
    observaciones = db.Column(db.Text)
    temporada = db.Column(db.String(50))
    op = db.Column(db.String(50))
    anticipo_id = db.Column(db.Integer, db.ForeignKey('anticipos.id'), nullable=True, index=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=True, index=True)
    cuenta_asignacion_id = db.Column(db.Integer, db.ForeignKey('cuentas_asignacion.id'), nullable=True, index=True)
    partida_id = db.Column(db.Integer, db.ForeignKey('partidas.id'), nullable=True, index=True)
    maestro_tela_id = db.Column(db.Integer, db.ForeignKey('maestro_telas.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    partida_rel = db.relationship('Partida', foreign_keys=[partida_id])
    maestro_tela_rel = db.relationship('MaestroTela', foreign_keys=[maestro_tela_id])

    __table_args__ = (
        # Listar movimientos de un proveedor por fecha desc (filtro mas comun).
        db.Index('ix_mov_proveedor_fecha', 'proveedor_id', 'fecha'),
        # Buscar movimientos por remito (cascade en panel.py al eliminar factura).
        db.Index('ix_mov_proveedor_remito', 'proveedor_id', 'remito_factura'),
    )

    def __repr__(self):
        return f'<Movimiento {self.fecha} {self.tipo_tela} {self.cant_kg}kg>'


class Anticipo(db.Model):
    __tablename__ = 'anticipos'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=False, index=True)
    numero_factura = db.Column(db.String(50), index=True)
    monto = db.Column(db.Numeric(14, 2), default=0)         # Bruto (neto + IVA + percepciones si las hubiera)
    neto = db.Column(db.Numeric(14, 2), default=0)          # Base imponible (sin IVA). Sirve para retenciones RG 830.
    iva_alicuota = db.Column(db.Numeric(8, 4), default=21)  # % IVA aplicado al armar la factura
    cant_kg = db.Column(db.Numeric(12, 3), default=0)  # Kg comprometidos en el anticipo
    descripcion = db.Column(db.Text)
    estado = db.Column(db.String(20), default='Abierto', index=True)  # Abierto, Cerrado
    created_at = db.Column(db.DateTime, default=datetime.now)

    movimientos = db.relationship('MovimientoTela', backref='anticipo', lazy='dynamic')
    pedidos = db.relationship('Pedido', backref='anticipo', lazy='dynamic', order_by='Pedido.fecha')
    cuentas_asignacion = db.relationship('CuentaAsignacion', backref='anticipo', lazy='dynamic',
                                          cascade='all, delete-orphan')

    # Caches por instancia (opt-in). Si Anticipo._precompute_bulk(...) los
    # rellena, los metodos los usan en vez de hacer SUM uno por uno.
    _cache_kg_entregados = None
    _cache_valor_entregado = None
    _cache_kg_pedidos = None
    _cache_valor_pedidos = None

    @classmethod
    def precompute_totales(cls, anticipos):
        """Precarga totales agregados en memoria para una lista de anticipos.

        Evita N+1 cuando se renderiza un listado que llama a
        total_kg_entregados()/total_valor_entregado() por cada fila.
        """
        ids = [a.id for a in anticipos if a.id]
        if not ids:
            return
        # Entregas (movimientos de tela)
        mov_rows = db.session.query(
            MovimientoTela.anticipo_id,
            db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0),
            db.func.coalesce(db.func.sum(MovimientoTela.subtotal_iva), 0),
        ).filter(MovimientoTela.anticipo_id.in_(ids)).group_by(MovimientoTela.anticipo_id).all()
        mov_map = {aid: (kg, val) for aid, kg, val in mov_rows}
        # Pedidos
        ped_rows = db.session.query(
            Pedido.anticipo_id,
            db.func.coalesce(db.func.sum(PedidoDetalle.cant_kg), 0),
            db.func.coalesce(db.func.sum(PedidoDetalle.subtotal), 0),
        ).join(PedidoDetalle, PedidoDetalle.pedido_id == Pedido.id) \
         .filter(Pedido.anticipo_id.in_(ids)).group_by(Pedido.anticipo_id).all()
        ped_map = {aid: (kg, val) for aid, kg, val in ped_rows}
        for a in anticipos:
            kg_e, val_e = mov_map.get(a.id, (0, 0))
            kg_p, val_p = ped_map.get(a.id, (0, 0))
            a._cache_kg_entregados = kg_e
            a._cache_valor_entregado = val_e
            a._cache_kg_pedidos = kg_p
            a._cache_valor_pedidos = val_p

    def total_kg_pedidos(self):
        if self._cache_kg_pedidos is not None:
            return self._cache_kg_pedidos
        return db.session.query(
            db.func.coalesce(db.func.sum(PedidoDetalle.cant_kg), 0)
        ).join(Pedido).filter(Pedido.anticipo_id == self.id).scalar() or 0

    def total_valor_pedidos(self):
        if self._cache_valor_pedidos is not None:
            return self._cache_valor_pedidos
        return db.session.query(
            db.func.coalesce(db.func.sum(PedidoDetalle.subtotal), 0)
        ).join(Pedido).filter(Pedido.anticipo_id == self.id).scalar() or 0

    def total_kg_entregados(self):
        if self._cache_kg_entregados is not None:
            return self._cache_kg_entregados
        return db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0)
        ).filter(MovimientoTela.anticipo_id == self.id).scalar() or 0

    def total_valor_entregado(self):
        if self._cache_valor_entregado is not None:
            return self._cache_valor_entregado
        return db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.subtotal_iva), 0)
        ).filter(MovimientoTela.anticipo_id == self.id).scalar() or 0

    def saldo_pendiente(self):
        return (self.monto or 0) - self.total_valor_entregado()

    def kg_pendientes(self):
        return (self.cant_kg or 0) - self.total_kg_entregados()

    def __repr__(self):
        return f'<Anticipo {self.numero} - {self.proveedor.nombre}>'


class CuentaAsignacion(db.Model):
    __tablename__ = 'cuentas_asignacion'
    id = db.Column(db.Integer, primary_key=True)
    anticipo_id = db.Column(db.Integer, db.ForeignKey('anticipos.id'), nullable=False, index=True)
    numero = db.Column(db.String(50), nullable=False)
    tipo_tela = db.Column(db.String(50))
    cant_kg = db.Column(db.Numeric(12, 3), default=0)
    monto = db.Column(db.Numeric(14, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    movimientos = db.relationship('MovimientoTela', backref='cuenta_asignacion', lazy='dynamic')

    _cache_kg_entregados = None
    _cache_valor_entregado = None

    @classmethod
    def precompute_totales(cls, cuentas):
        """Precarga totales agregados en memoria para una lista de cuentas."""
        ids = [c.id for c in cuentas if c.id]
        if not ids:
            return
        rows = db.session.query(
            MovimientoTela.cuenta_asignacion_id,
            db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0),
            db.func.coalesce(db.func.sum(MovimientoTela.subtotal_iva), 0),
        ).filter(MovimientoTela.cuenta_asignacion_id.in_(ids)) \
         .group_by(MovimientoTela.cuenta_asignacion_id).all()
        m = {cid: (kg, val) for cid, kg, val in rows}
        for c in cuentas:
            kg, val = m.get(c.id, (0, 0))
            c._cache_kg_entregados = kg
            c._cache_valor_entregado = val

    def kg_entregados(self):
        if self._cache_kg_entregados is not None:
            return self._cache_kg_entregados
        return db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0)
        ).filter(MovimientoTela.cuenta_asignacion_id == self.id).scalar() or 0

    def valor_entregado(self):
        if self._cache_valor_entregado is not None:
            return self._cache_valor_entregado
        return db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.subtotal_iva), 0)
        ).filter(MovimientoTela.cuenta_asignacion_id == self.id).scalar() or 0

    def kg_pendientes(self):
        return (self.cant_kg or 0) - self.kg_entregados()

    def saldo_pendiente(self):
        return (self.monto or 0) - self.valor_entregado()

    def __repr__(self):
        return f'<CuentaAsignacion {self.numero} - {self.tipo_tela}>'


class CuentaCorriente(db.Model):
    __tablename__ = 'cuenta_corriente'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=False)
    tipo = db.Column(db.String(30), index=True)  # Factura, Pago, Adelanto, Nota de Credito, Nota de Debito, Retencion Ganancias
    numero_comprobante = db.Column(db.String(50))
    descripcion = db.Column(db.Text)
    cuenta = db.Column(db.String(20))  # JUMAF, JUMASA
    debe = db.Column(db.Numeric(14, 2), default=0)
    haber = db.Column(db.Numeric(14, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    aplicaciones = db.relationship('PagoFactura', backref='factura', lazy='dynamic',
                                    foreign_keys='PagoFactura.cc_factura_id')

    __table_args__ = (
        # Listar CC de un proveedor en orden cronologico (panel.py).
        db.Index('ix_cc_proveedor_fecha', 'proveedor_id', 'fecha'),
        # Detectar duplicados de comprobante por proveedor (validacion de panel_operacion).
        db.Index('ix_cc_proveedor_comprobante', 'proveedor_id', 'numero_comprobante'),
    )

    def es_pagable(self):
        """Facturas y notas de debito pueden pagarse."""
        return self.tipo in ('Factura', 'Nota de Debito')

    def es_credito(self):
        """Notas de credito: saldo a favor del proveedor que se puede aplicar a un pago."""
        return self.tipo == 'Nota de Credito'

    def es_aplicable(self):
        """Comprobantes que se incluyen al armar un pago (a sumar o restar)."""
        return self.es_pagable() or self.es_credito()

    def monto_aplicado(self):
        """Suma de pagos aplicados a esta factura."""
        return db.session.query(
            db.func.coalesce(db.func.sum(PagoFactura.monto_aplicado), 0)
        ).filter(PagoFactura.cc_factura_id == self.id).scalar() or 0

    def saldo_pendiente(self):
        """Saldo pendiente. En facturas/ND es debe - aplicado; en NC es haber - aplicado."""
        if self.es_pagable():
            return (self.debe or 0) - self.monto_aplicado()
        if self.es_credito():
            return (self.haber or 0) - self.monto_aplicado()
        return 0

    def estado_pago(self):
        if not self.es_aplicable():
            return '—'
        saldo = self.saldo_pendiente()
        if saldo <= 0.01:
            return 'Aplicada' if self.es_credito() else 'Pagada'
        if self.monto_aplicado() > 0.01:
            return 'Parcial'
        return 'Pendiente'

    def __repr__(self):
        return f'<CC {self.fecha} {self.tipo} D:{self.debe} H:{self.haber}>'


class Pago(db.Model):
    """Cabecera de un pago a proveedor. Agrupa aplicaciones a facturas + retenciones."""
    __tablename__ = 'pagos'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30), index=True)  # OP-00001
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=False, index=True)
    agente_codigo = db.Column(db.String(20), default='JUMAF', index=True)  # JUMAF / JUMASA
    agente_cuit = db.Column(db.String(20))
    agente_nombre = db.Column(db.String(100))
    medio_pago = db.Column(db.String(50))  # Efectivo, Transferencia, Cheque, etc.
    referencia = db.Column(db.String(100))  # Nro cheque, CBU, etc.
    monto_bruto = db.Column(db.Numeric(14, 2), default=0)  # Total aplicado a facturas
    total_retenciones = db.Column(db.Numeric(14, 2), default=0)
    monto_neto = db.Column(db.Numeric(14, 2), default=0)  # Lo que efectivamente se entrega al proveedor
    observaciones = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    proveedor = db.relationship('Proveedor', backref='pagos')
    aplicaciones = db.relationship('PagoFactura', backref='pago', lazy='dynamic',
                                   cascade='all, delete-orphan')
    retenciones = db.relationship('RetencionGanancias', backref='pago', lazy='dynamic')

    def __repr__(self):
        return f'<Pago {self.numero} ${self.monto_bruto}>'


class PagoFactura(db.Model):
    """Aplicacion de un pago a una factura especifica."""
    __tablename__ = 'pago_factura'
    id = db.Column(db.Integer, primary_key=True)
    pago_id = db.Column(db.Integer, db.ForeignKey('pagos.id'), nullable=False, index=True)
    cc_factura_id = db.Column(db.Integer, db.ForeignKey('cuenta_corriente.id'), nullable=False, index=True)
    monto_aplicado = db.Column(db.Numeric(14, 2), default=0)

    def __repr__(self):
        return f'<PagoFactura pago={self.pago_id} cc={self.cc_factura_id} ${self.monto_aplicado}>'


class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)  # Pedido #1, #2, etc.
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    anticipo_id = db.Column(db.Integer, db.ForeignKey('anticipos.id'), nullable=False, index=True)
    observaciones = db.Column(db.Text)
    estado = db.Column(db.String(20), default='Pendiente', index=True)  # Pendiente, Parcial, Completo
    created_at = db.Column(db.DateTime, default=datetime.now)

    detalles = db.relationship('PedidoDetalle', backref='pedido', lazy='dynamic',
                               cascade='all, delete-orphan')
    movimientos = db.relationship('MovimientoTela', backref='pedido', lazy='dynamic')

    def total_kg(self):
        return db.session.query(
            db.func.coalesce(db.func.sum(PedidoDetalle.cant_kg), 0)
        ).filter(PedidoDetalle.pedido_id == self.id).scalar() or 0

    def total_valor(self):
        return db.session.query(
            db.func.coalesce(db.func.sum(PedidoDetalle.subtotal), 0)
        ).filter(PedidoDetalle.pedido_id == self.id).scalar() or 0

    def kg_entregados(self):
        return db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0)
        ).filter(MovimientoTela.pedido_id == self.id).scalar() or 0

    def valor_entregado(self):
        return db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.subtotal_iva), 0)
        ).filter(MovimientoTela.pedido_id == self.id).scalar() or 0

    def kg_pendientes(self):
        return self.total_kg() - self.kg_entregados()

    def valor_pendiente(self):
        return self.total_valor() - self.valor_entregado()

    def actualizar_estado(self):
        """Actualiza el estado del pedido segun las entregas realizadas."""
        kg_ped = self.total_kg()
        kg_ent = self.kg_entregados()
        if kg_ped <= 0:
            return
        if kg_ent <= 0:
            self.estado = 'Pendiente'
        elif kg_ent >= kg_ped:
            self.estado = 'Completo'
        else:
            self.estado = 'Parcial'

    def __repr__(self):
        return f'<Pedido {self.numero}>'


class PedidoDetalle(db.Model):
    __tablename__ = 'pedido_detalles'
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False, index=True)
    tipo_tela = db.Column(db.String(50))
    color = db.Column(db.String(100))
    cod_art = db.Column(db.String(20))
    cod_color = db.Column(db.String(20))
    cant_kg = db.Column(db.Numeric(12, 3), default=0)
    precio_unitario = db.Column(db.Numeric(14, 2), default=0)  # Precio por kg
    subtotal = db.Column(db.Numeric(14, 2), default=0)

    def kg_entregados(self):
        """Kg entregados de esta linea especifica (mismo pedido, tipo_tela y color)."""
        return db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0)
        ).filter(
            MovimientoTela.pedido_id == self.pedido_id,
            MovimientoTela.tipo_tela == self.tipo_tela,
            MovimientoTela.color == self.color
        ).scalar() or 0

    def kg_pendientes(self):
        return (self.cant_kg or 0) - self.kg_entregados()

    def __repr__(self):
        return f'<PedidoDetalle {self.tipo_tela} {self.color} {self.cant_kg}kg>'


class ConceptoRetencionGanancias(db.Model):
    __tablename__ = 'conceptos_retencion_ganancias'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.Integer, nullable=False, unique=True)  # Codigo regimen AFIP
    concepto = db.Column(db.String(200), nullable=False)
    mni_inscripto = db.Column(db.Numeric(14, 2), default=0)
    alicuota_inscripto = db.Column(db.Numeric(8, 4), default=0)
    tipo_inscripto = db.Column(db.String(20), default='Fija')  # Fija, Escala
    alicuota_no_inscripto = db.Column(db.Numeric(8, 4), default=0)
    tipo_no_inscripto = db.Column(db.String(20), default='Fija')
    min_retencion_inscripto = db.Column(db.Numeric(14, 2), default=0)
    min_retencion_no_inscripto = db.Column(db.Numeric(14, 2), default=0)
    escala_aplicable = db.Column(db.String(20), default='—')  # General, Especifica, —
    activo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Concepto {self.codigo} {self.concepto}>'


class EscalaGanancias(db.Model):
    __tablename__ = 'escalas_ganancias'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # General, Especifica
    desde = db.Column(db.Numeric(14, 2), default=0)
    hasta = db.Column(db.Numeric(14, 2), default=0)
    monto_fijo = db.Column(db.Numeric(14, 2), default=0)
    alicuota_marginal = db.Column(db.Numeric(8, 4), default=0)
    excedente_sobre = db.Column(db.Numeric(14, 2), default=0)

    def __repr__(self):
        return f'<Escala {self.tipo} {self.desde}-{self.hasta}>'


class RetencionGanancias(db.Model):
    __tablename__ = 'retenciones_ganancias'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    mes_anio = db.Column(db.String(7), index=True)  # YYYY-MM
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=False, index=True)
    concepto_id = db.Column(db.Integer, db.ForeignKey('conceptos_retencion_ganancias.id'), nullable=False, index=True)
    condicion = db.Column(db.String(20))  # Inscripto, No Inscripto
    agente_cuit = db.Column(db.String(20), index=True)  # CUIT del agente retencion (JUMAF/JUMASA)
    agente_nombre = db.Column(db.String(100))
    numero_comprobante = db.Column(db.String(50))
    monto_sujeto = db.Column(db.Numeric(14, 2), default=0)        # Importe del comprobante (bruto c/IVA) para SICORE
    base_imponible = db.Column(db.Numeric(14, 2), default=0)      # Neto gravado del pago (base RG 830 sin IVA)
    base_acumulada = db.Column(db.Numeric(14, 2), default=0)
    mni_aplicado = db.Column(db.Numeric(14, 2), default=0)
    base_sujeta = db.Column(db.Numeric(14, 2), default=0)
    impuesto_teorico = db.Column(db.Numeric(14, 2), default=0)
    retenido_previo = db.Column(db.Numeric(14, 2), default=0)
    retencion = db.Column(db.Numeric(14, 2), default=0)
    monto_neto = db.Column(db.Numeric(14, 2), default=0)
    alicuota_aplicada = db.Column(db.String(30))  # '6%' o 'Escala General' etc.
    cc_pago_id = db.Column(db.Integer, db.ForeignKey('cuenta_corriente.id'), nullable=True, index=True)
    cc_retencion_id = db.Column(db.Integer, db.ForeignKey('cuenta_corriente.id'), nullable=True, index=True)
    pago_id = db.Column(db.Integer, db.ForeignKey('pagos.id'), nullable=True, index=True)
    observaciones = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    concepto = db.relationship('ConceptoRetencionGanancias')
    cc_pago = db.relationship('CuentaCorriente', foreign_keys=[cc_pago_id])
    cc_retencion = db.relationship('CuentaCorriente', foreign_keys=[cc_retencion_id])

    __table_args__ = (
        # Acumulado mensual por proveedor + concepto (RG 830 art. 26).
        db.Index('ix_ret_acum_mensual', 'proveedor_id', 'concepto_id', 'mes_anio'),
    )

    def __repr__(self):
        return f'<Retencion {self.fecha} ${self.retencion}>'


class Auditoria(db.Model):
    __tablename__ = 'auditoria'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    accion = db.Column(db.String(20), index=True)  # Crear, Editar, Eliminar
    entidad = db.Column(db.String(50), index=True)  # MovimientoTela, CuentaCorriente, Anticipo, Pedido, Proveedor
    entidad_id = db.Column(db.Integer)
    detalle = db.Column(db.Text)

    usuario = db.relationship('Usuario', backref='auditorias')

    def __repr__(self):
        return f'<Auditoria {self.accion} {self.entidad} #{self.entidad_id}>'


# ═══════════════════════════════════════════════════════════════════════════
# FASE 1 - Maestro de Telas (catalogo normalizado por proveedor)
# ═══════════════════════════════════════════════════════════════════════════
class MaestroTela(db.Model):
    __tablename__ = 'maestro_telas'
    id = db.Column(db.Integer, primary_key=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    tipo_tela = db.Column(db.String(50), nullable=False)   # FRISA, JERSEY, MORLEY, RUSTICO, DEPORTIVO, RIBB
    cod_art = db.Column(db.String(30))
    color = db.Column(db.String(100), nullable=False)
    cod_color = db.Column(db.String(30))
    descripcion = db.Column(db.String(200))
    cuenta_piezas = db.Column(db.Boolean, default=True)    # False para Morley/RIBB (no se cuentan en piezas)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    proveedor = db.relationship('Proveedor', foreign_keys=[proveedor_id])

    __table_args__ = (
        db.UniqueConstraint('proveedor_id', 'tipo_tela', 'cod_art', 'color', 'cod_color',
                            name='uq_maestro_tela'),
    )

    def __repr__(self):
        return f'<MaestroTela {self.tipo_tela}/{self.color} [{self.cod_art}]>'


# ═══════════════════════════════════════════════════════════════════════════
# FASE 3 - Partidas (lotes del proveedor)
# ═══════════════════════════════════════════════════════════════════════════
class Partida(db.Model):
    __tablename__ = 'partidas'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)   # Nº de partida del proveedor
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=False, index=True)
    tipo_tela = db.Column(db.String(50))
    color = db.Column(db.String(100))
    cod_art = db.Column(db.String(30))
    cod_color = db.Column(db.String(30))
    piezas_totales = db.Column(db.Integer, default=0)   # Total piezas del lote segun proveedor
    kg_totales = db.Column(db.Numeric(12, 3), default=0)         # Total kg del lote (opcional)
    observaciones = db.Column(db.Text)
    fecha_alta = db.Column(db.Date, default=date.today)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    proveedor = db.relationship('Proveedor', foreign_keys=[proveedor_id])

    __table_args__ = (
        db.UniqueConstraint('proveedor_id', 'numero', name='uq_partida_proveedor_numero'),
    )

    def piezas_consumidas(self):
        """Piezas consumidas (solo movimientos de Consumo, valor absoluto)."""
        v = db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.piezas), 0)
        ).filter(
            MovimientoTela.partida_id == self.id,
            MovimientoTela.movimiento == 'Consumo',
        ).scalar() or 0
        return abs(v)

    def kg_consumidos(self):
        """Kg consumidos (solo movimientos de Consumo, valor absoluto)."""
        v = db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0)
        ).filter(
            MovimientoTela.partida_id == self.id,
            MovimientoTela.movimiento == 'Consumo',
        ).scalar() or 0
        return abs(v)

    def kg_movidos(self):
        """Kg netos vinculados a la partida (ingresos + consumos/devoluciones con signo)."""
        return db.session.query(
            db.func.coalesce(db.func.sum(MovimientoTela.cant_kg), 0)
        ).filter(MovimientoTela.partida_id == self.id).scalar() or 0

    def piezas_saldo(self):
        return (self.piezas_totales or 0) - self.piezas_consumidas()

    def kg_saldo(self):
        return (self.kg_totales or 0) - self.kg_consumidos()

    def control_ok(self):
        """OK si no queda saldo de piezas (o si la partida no se cuenta por piezas)."""
        if (self.piezas_totales or 0) == 0:
            return True
        return self.piezas_saldo() <= 0

    def esta_agotada(self):
        """True si la partida ya no tiene saldo disponible (pzas y kg)."""
        tiene_pzas = (self.piezas_totales or 0) > 0
        tiene_kg = (self.kg_totales or 0) > 0
        if not tiene_pzas and not tiene_kg:
            return False  # sin tracking, nunca se considera agotada
        pzas_ok = (not tiene_pzas) or self.piezas_saldo() <= 0
        kg_ok = (not tiene_kg) or self.kg_saldo() <= 0.001
        return pzas_ok and kg_ok

    def __repr__(self):
        return f'<Partida {self.numero} {self.tipo_tela}/{self.color}>'


# ═══════════════════════════════════════════════════════════════════════════
# FASE 4 - Notas de Credito (asociacion diferida con devoluciones)
# ═══════════════════════════════════════════════════════════════════════════
class NotaCredito(db.Model):
    __tablename__ = 'notas_credito'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=False, index=True)
    cuenta = db.Column(db.String(20))   # JUMAF / JUMASA
    monto_total = db.Column(db.Numeric(14, 2), default=0)        # Neto s/IVA que efectivamente acreditan
    iva = db.Column(db.Numeric(14, 2), default=0)
    monto_con_iva = db.Column(db.Numeric(14, 2), default=0)      # Total c/IVA que impacta en CC
    observaciones = db.Column(db.Text)
    cc_id = db.Column(db.Integer, db.ForeignKey('cuenta_corriente.id'), nullable=True, index=True)  # asiento en CC creado al vincular
    created_at = db.Column(db.DateTime, default=datetime.now)

    proveedor = db.relationship('Proveedor', foreign_keys=[proveedor_id])
    items = db.relationship('NotaCreditoItem', backref='nota_credito',
                            lazy='dynamic', cascade='all, delete-orphan')
    cc_asiento = db.relationship('CuentaCorriente', foreign_keys=[cc_id])

    def total_kg_aceptados(self):
        return db.session.query(
            db.func.coalesce(db.func.sum(NotaCreditoItem.kg_aceptados), 0)
        ).filter(NotaCreditoItem.nc_id == self.id).scalar() or 0

    def total_kg_reclamados(self):
        """Suma de kg devueltos (valor absoluto) en los movimientos vinculados."""
        return db.session.query(
            db.func.coalesce(db.func.sum(db.func.abs(MovimientoTela.cant_kg)), 0)
        ).join(NotaCreditoItem, NotaCreditoItem.movimiento_id == MovimientoTela.id) \
         .filter(NotaCreditoItem.nc_id == self.id).scalar() or 0

    def __repr__(self):
        return f'<NotaCredito {self.numero} {self.fecha}>'


class NotaCreditoItem(db.Model):
    __tablename__ = 'notas_credito_items'
    id = db.Column(db.Integer, primary_key=True)
    nc_id = db.Column(db.Integer, db.ForeignKey('notas_credito.id'), nullable=False, index=True)
    movimiento_id = db.Column(db.Integer, db.ForeignKey('movimientos_tela.id'), nullable=False, index=True)
    kg_aceptados = db.Column(db.Numeric(12, 3), default=0)       # kg que el proveedor realmente acepto
    monto_aceptado = db.Column(db.Numeric(14, 2), default=0)     # $ s/IVA que corresponden a esos kg
    observaciones = db.Column(db.Text)

    movimiento = db.relationship('MovimientoTela', foreign_keys=[movimiento_id])

    def kg_reclamados(self):
        return abs(self.movimiento.cant_kg or 0) if self.movimiento else 0

    def kg_diferencia(self):
        """kg reclamados - kg aceptados (positivo = perdida)."""
        return self.kg_reclamados() - (self.kg_aceptados or 0)

    def __repr__(self):
        return f'<NCItem nc={self.nc_id} mov={self.movimiento_id} kg_ac={self.kg_aceptados}>'


# ═══════════════════════════════════════════════════════════════════════════
# Facturas de Compras (proveedores No Tela) - gastos, servicios, comisiones
# ═══════════════════════════════════════════════════════════════════════════

CATEGORIAS_COMPRA = [
    'AVIOS',
    'COMISIONES',
    'EMBALAJE',
    'HONORARIOS',
    'FLETE',
    'PROMOCION Y PUBLICIDAD',
    'SEGURO',
    'LEASING',
    'AMORTIZACION',
    'MULTA',
    'Telefonos',
    'PATENTE',
    'Muebles y Utiles/Rodados',
    'Combustible',
    'Mov. Viaticos y Peajes',
    'AGUA',
    'ELECTRICIDAD',
    'ALQUILERES',
    'REPUESTOS Y REPARACIONES',
    'ABONO INTERNET',
    'MANTENIMIENTO',
    'REFRIGERIO',
    'Maquinas y Herramientas',
    'INSUMOS COMPUTACION',
    'LIBRERÍA',
    'CORREO Y ENCOMIENDAS',
    'Gastos Comerciales',
    'Gastos Bancarios',
    'Gastos Varios',
    'COSTO Produccion',
]

TIPOS_COMPROBANTE_COMPRA = ['A', 'B', 'C', 'M', 'E', 'Otro']

# Clase de documento (independiente de la letra A/B/C):
# - Factura: deuda al proveedor (debe en CC).
# - NotaDebito: deuda adicional (debe en CC). Pagable como factura.
# - NotaCredito: credito a favor (haber en CC). Reduce saldo del proveedor.
TIPOS_DOCUMENTO_COMPRA = ['Factura', 'NotaDebito', 'NotaCredito']

TIPO_DOCUMENTO_LABELS = {
    'Factura': 'Factura',
    'NotaDebito': 'Nota de Débito',
    'NotaCredito': 'Nota de Crédito',
}


class FacturaCompra(db.Model):
    """Cabecera de factura de compras (no tela): servicios, gastos, comisiones, etc.

    Tambien se usa para Notas de Credito y Notas de Debito de proveedores no-tela.
    El campo `tipo_documento` decide el sentido del asiento en CC.
    """
    __tablename__ = 'facturas_compra'
    id = db.Column(db.Integer, primary_key=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    tipo_documento = db.Column(db.String(20), default='Factura', index=True)  # Factura, NotaDebito, NotaCredito
    tipo_comprobante = db.Column(db.String(10), default='A')  # A, B, C, M, E, Otro
    punto_venta = db.Column(db.String(10))
    numero = db.Column(db.String(20))
    cuenta = db.Column(db.String(20))  # JUMAF, JUMASA

    # Totales desglosados (calculados a partir de los items + percepciones de cabecera)
    neto_gravado = db.Column(db.Numeric(14, 2), default=0)      # Base imponible sujeta a retenciones
    neto_no_gravado = db.Column(db.Numeric(14, 2), default=0)
    iva_total = db.Column(db.Numeric(14, 2), default=0)         # Suma de ivas por linea
    imp_internos_total = db.Column(db.Numeric(14, 2), default=0)
    percep_iva = db.Column(db.Numeric(14, 2), default=0)        # Percepcion IVA (cabecera)
    percep_iibb = db.Column(db.Numeric(14, 2), default=0)       # Percepcion IIBB (cabecera)
    otros_impuestos = db.Column(db.Numeric(14, 2), default=0)   # Otros tributos
    total = db.Column(db.Numeric(14, 2), default=0)             # Total comprobante

    observaciones = db.Column(db.Text)
    cc_id = db.Column(db.Integer, db.ForeignKey('cuenta_corriente.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    proveedor = db.relationship('Proveedor', foreign_keys=[proveedor_id])
    cc_asiento = db.relationship('CuentaCorriente', foreign_keys=[cc_id])
    items = db.relationship('FacturaCompraItem', backref='factura',
                            lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('proveedor_id', 'tipo_documento', 'tipo_comprobante',
                            'punto_venta', 'numero',
                            name='uq_factura_compra_doc_proveedor_numero'),
    )

    def es_nota_credito(self):
        return self.tipo_documento == 'NotaCredito'

    def es_nota_debito(self):
        return self.tipo_documento == 'NotaDebito'

    def tipo_cc(self):
        """Tipo a usar en CuentaCorriente segun el documento."""
        if self.es_nota_credito():
            return 'Nota de Credito'
        if self.es_nota_debito():
            return 'Nota de Debito'
        return 'Factura'

    def tipo_documento_label(self):
        return TIPO_DOCUMENTO_LABELS.get(self.tipo_documento or 'Factura', 'Factura')

    def prefijo_documento(self):
        """Prefijo corto para identificar el documento (NC, ND o vacio)."""
        if self.es_nota_credito():
            return 'NC'
        if self.es_nota_debito():
            return 'ND'
        return ''

    def numero_completo(self):
        pv = (self.punto_venta or '').strip().zfill(5) if self.punto_venta else ''
        nro = (self.numero or '').strip().zfill(8) if self.numero else ''
        if pv and nro:
            base = f'{self.tipo_comprobante} {pv}-{nro}'
        else:
            base = f'{self.tipo_comprobante} {self.numero or ""}'
        prefijo = self.prefijo_documento()
        return f'{prefijo} {base}'.strip() if prefijo else base

    def categorias_resumen(self):
        """Lista de categorias unicas presentes en los items."""
        cats = set()
        for it in self.items:
            if it.categoria:
                cats.add(it.categoria)
        return sorted(cats)

    def __repr__(self):
        return f'<FacturaCompra {self.numero_completo()} ${self.total}>'


class FacturaCompraItem(db.Model):
    """Detalle de factura de compras: una linea por item/servicio, con categoria contable."""
    __tablename__ = 'facturas_compra_items'
    id = db.Column(db.Integer, primary_key=True)
    factura_id = db.Column(db.Integer, db.ForeignKey('facturas_compra.id'), nullable=False, index=True)
    descripcion = db.Column(db.String(300), nullable=False)
    cantidad = db.Column(db.Numeric(12, 3), default=1)
    costo_unitario = db.Column(db.Numeric(14, 2), default=0)
    subtotal_neto = db.Column(db.Numeric(14, 2), default=0)     # cantidad * costo_unitario
    iva_alicuota = db.Column(db.Numeric(8, 4), default=21)     # 0, 10.5, 21, 27
    iva_monto = db.Column(db.Numeric(14, 2), default=0)         # subtotal_neto * iva_alicuota/100
    imp_internos = db.Column(db.Numeric(14, 2), default=0)
    categoria = db.Column(db.String(60), nullable=False)
    observaciones = db.Column(db.Text)

    def total_linea(self):
        return (self.subtotal_neto or 0) + (self.iva_monto or 0) + (self.imp_internos or 0)

    def __repr__(self):
        return f'<FacturaCompraItem {self.categoria} {self.descripcion[:30]} ${self.subtotal_neto}>'
