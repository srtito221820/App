"""
Script para importar datos desde el Excel de Ingreso de Telas.
Uso: python importar_excel.py <ruta_al_archivo.xlsx>
"""
import sys
import pandas as pd
from app import app, db
from models import Proveedor, MovimientoTela


PROVEEDORES_INICIALES = [
    ('Ritex', '', 'Textiles', 45),
    ('Neoxcela', '', 'Textiles', 45),
    ('Texcom', '', 'Textiles', 45),
    ('Alan', '', 'Textiles', 45),
    ('Cladd', '', 'Textiles', 45),
    ('Autraltex', '', 'Textiles', 45),
    ('Enod', '', 'Textiles', 45),
    ('Hilados San Martin S.A.', '30-71111111-2', 'Textiles', 30),
    ('Quimicos del Sur SRL', '30-72222222-3', 'Insumos Quimicos', 15),
    ('Envases Industriales del Plata S.A.', '30-73333333-4', 'Packaging', 45),
    ('Tintoreria Federal S.A.', '30-74444444-5', 'Servicios', 20),
    ('Accesorios del Norte S.R.L.', '30-75555555-6', 'Avios', 25),
    ('ASCENSORES BATTAGLIA', '33-71591362-9', 'Servicios', 30),
    ('TRANS Jorge Antuna', '30-70958037-6', 'Servicios', 45),
    ('AY G TRUCKS SRL', '30-71537854-6', 'Servicios', 60),
    ('ACO ZIPPERS', '30-70741690-0', 'Avios', 45),
    ('AMESUD', '30-64810353-7', 'Textiles', 45),
    ('ARSLANIAN', '20-30495266-1', 'Avios', 45),
    ('LA CENTRAL PAPELERA', '30-53414560-4', 'Insumos Corte', 30),
    ('CUERDAS Y CORDONES', '30-70834468-7', 'Avios', 60),
    ('EMARSU S.A. JAZZ PERCHAS', '33-70800388-9', 'Avios', 90),
    ('EULE GRAPHICS', '30-71233525-0', 'Avios', 60),
    ('EUROCOR S.A.', '30-71232976-5', 'Insumos Expedicion', 60),
    ('GRAFICA SAN MARTIN', '20-22856932-2', 'Avios', 90),
    ('MARCELO BREMER - UNITEX TEJIDOS S.A.', '30-71460274-4', 'Textiles', 60),
    ('LABEL Y TAGS', '30-70817700-4', 'Avios', 45),
    ('LACUEST SRL', '33-71537088-9', 'Avios', 90),
    ('TEXCINT', '30-56893669-4', 'Elasticos', 60),
]


def importar_proveedores():
    print("Importando proveedores...")
    count = 0
    for nombre, cuit, categoria, dias in PROVEEDORES_INICIALES:
        existe = Proveedor.query.filter_by(nombre=nombre).first()
        if not existe:
            p = Proveedor(nombre=nombre, cuit=cuit, categoria=categoria, condicion_pago_dias=dias)
            db.session.add(p)
            count += 1
    db.session.commit()
    print(f"  {count} proveedores nuevos creados.")


def importar_movimientos(archivo_excel):
    print(f"Leyendo archivo: {archivo_excel}")
    df = pd.read_excel(archivo_excel, sheet_name='INGRESOS', header=0)

    # Mapear nombres de columnas
    col_map = {
        'FECHA': 'fecha',
        'Cta.': 'cuenta',
        'REMITO/ FACT': 'remito_factura',
        'Proveedor': 'proveedor_nombre',
        'Cta/Pedido': 'cuenta_pedido',
        'TIPO TELA': 'tipo_tela',
        'Descripcion': 'descripcion',
        'COLOR': 'color',
        'Cod Art': 'cod_art',
        'Cod color': 'cod_color',
        'CANT EN KG': 'cant_kg',
        'Piezas': 'piezas',
        'Partida': 'partida',
        'PRECIO SIN IVA': 'precio_sin_iva',
        'C/IVA': 'precio_con_iva',
        'SUBTOTAL': 'subtotal',
        'Percp. IVA': 'percp_iva',
        'Percp. IIBB': 'percp_iibb',
        'SUBTotal / IVA': 'subtotal_iva',
        'Dif Kg': 'dif_kg',
        'Movimiento': 'movimiento',
        'Estado': 'estado',
        'Obs': 'observaciones',
        'Temporada': 'temporada',
        'OP.': 'op',
    }

    df = df.rename(columns=col_map)

    # Cache de proveedores
    proveedores_cache = {}
    for p in Proveedor.query.all():
        proveedores_cache[p.nombre.lower()] = p.id

    count = 0
    errores = 0

    for _, row in df.iterrows():
        try:
            prov_nombre = str(row.get('proveedor_nombre', '')).strip()
            if not prov_nombre or prov_nombre == 'nan':
                continue

            prov_id = proveedores_cache.get(prov_nombre.lower())
            if not prov_id:
                # Crear proveedor si no existe
                nuevo = Proveedor(nombre=prov_nombre, categoria='Textiles', condicion_pago_dias=45)
                db.session.add(nuevo)
                db.session.flush()
                proveedores_cache[prov_nombre.lower()] = nuevo.id
                prov_id = nuevo.id

            fecha = pd.to_datetime(row.get('fecha'))
            if pd.isna(fecha):
                continue

            m = MovimientoTela(
                fecha=fecha.date(),
                cuenta=str(row.get('cuenta', '') or '').strip(),
                remito_factura=str(row.get('remito_factura', '') or '').strip(),
                proveedor_id=prov_id,
                cuenta_pedido=str(row.get('cuenta_pedido', '') or '').strip() if not pd.isna(row.get('cuenta_pedido')) else '',
                tipo_tela=str(row.get('tipo_tela', '') or '').strip(),
                descripcion=str(row.get('descripcion', '') or '').strip(),
                color=str(row.get('color', '') or '').strip(),
                cod_art=str(row.get('cod_art', '') or '').strip(),
                cod_color=str(row.get('cod_color', '') or '').strip(),
                cant_kg=float(row.get('cant_kg', 0) or 0) if not pd.isna(row.get('cant_kg')) else 0,
                piezas=int(float(row.get('piezas', 0) or 0)) if not pd.isna(row.get('piezas')) else 0,
                partida=str(row.get('partida', '') or '').strip() if not pd.isna(row.get('partida')) else '',
                precio_sin_iva=float(row.get('precio_sin_iva', 0) or 0) if not pd.isna(row.get('precio_sin_iva')) else 0,
                precio_con_iva=float(row.get('precio_con_iva', 0) or 0) if not pd.isna(row.get('precio_con_iva')) else 0,
                subtotal=float(row.get('subtotal', 0) or 0) if not pd.isna(row.get('subtotal')) else 0,
                percp_iva=float(row.get('percp_iva', 0) or 0) if not pd.isna(row.get('percp_iva')) else 0,
                percp_iibb=float(row.get('percp_iibb', 0) or 0) if not pd.isna(row.get('percp_iibb')) else 0,
                subtotal_iva=float(row.get('subtotal_iva', 0) or 0) if not pd.isna(row.get('subtotal_iva')) else 0,
                dif_kg=float(row.get('dif_kg', 0) or 0) if not pd.isna(row.get('dif_kg')) else 0,
                movimiento=str(row.get('movimiento', 'Ingreso') or 'Ingreso').strip(),
                estado=str(row.get('estado', '') or '').strip() if not pd.isna(row.get('estado')) else '',
                observaciones=str(row.get('observaciones', '') or '').strip() if not pd.isna(row.get('observaciones')) else '',
                temporada=str(row.get('temporada', '') or '').strip() if not pd.isna(row.get('temporada')) else '',
                op=str(row.get('op', '') or '').strip() if not pd.isna(row.get('op')) else '',
            )
            db.session.add(m)
            count += 1

            if count % 100 == 0:
                db.session.commit()
                print(f"  {count} movimientos importados...")

        except Exception as e:
            errores += 1
            print(f"  Error en fila: {e}")

    db.session.commit()
    print(f"Importacion completada: {count} movimientos, {errores} errores.")


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        importar_proveedores()

        if len(sys.argv) > 1:
            importar_movimientos(sys.argv[1])
        else:
            print("Para importar movimientos, usar: python importar_excel.py <archivo.xlsx>")
            print("Solo se importaron proveedores.")
