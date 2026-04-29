"""Helpers para aritmetica de dinero / cantidades con Decimal.

Reemplaza el uso historico de float para columnas monetarias y de cantidad,
evitando errores de redondeo binario que se acumulan en facturacion y
retenciones (RG 830).

Convencion de precision:
  - Importes ($)        -> 2 decimales (q2)
  - Kg                  -> 3 decimales (q3)
  - Alicuotas/%         -> 4 decimales (q4)

Redondeo: ROUND_HALF_UP (estandar contable AR).
"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

ZERO = Decimal('0')
_Q2 = Decimal('0.01')
_Q3 = Decimal('0.001')
_Q4 = Decimal('0.0001')


def D(value):
    """Convierte cualquier entrada (str, int, float, Decimal, None, '') a Decimal.

    - None / '' -> Decimal('0')
    - float     -> via str() para evitar ruido binario (Decimal(0.1) != Decimal('0.1'))
    - str       -> acepta coma decimal estilo argentino y separador de miles
    """
    if value is None or value == '':
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    s = str(value).strip()
    if not s:
        return ZERO
    if ',' in s and '.' in s:
        # "1.234,56" -> "1234.56"
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return Decimal(s)
    except InvalidOperation:
        return ZERO


def q2(value):
    """Cuantiza a 2 decimales (importes en $)."""
    return D(value).quantize(_Q2, rounding=ROUND_HALF_UP)


def q3(value):
    """Cuantiza a 3 decimales (Kg)."""
    return D(value).quantize(_Q3, rounding=ROUND_HALF_UP)


def q4(value):
    """Cuantiza a 4 decimales (alicuotas, porcentajes)."""
    return D(value).quantize(_Q4, rounding=ROUND_HALF_UP)


def parse_money(value, default=ZERO):
    """Parser para inputs de formularios. Garantiza Decimal con 2 decimales.

    Uso: monto = parse_money(request.form.get('monto'))
    """
    if value is None or value == '':
        return default
    return q2(value)


def parse_kg(value, default=ZERO):
    """Parser de Kg (3 decimales)."""
    if value is None or value == '':
        return default
    return q3(value)
