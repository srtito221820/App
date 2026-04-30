import os
import sys
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

def main():
    # Cargar variables de entorno del archivo .env si existe
    load_dotenv()

    print("=== Herramienta de Migración de Datos (SQLite a MySQL) ===")
    
    # 1. Definir URIs de origen y destino
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    default_sqlite = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'inventory.db')}"
    
    sqlite_uri = os.getenv('SQLITE_URL', default_sqlite)
    mysql_uri = os.getenv('DATABASE_URL')
    
    if not mysql_uri:
        print("ERROR: No se encontró DATABASE_URL en tus variables de entorno.")
        print("Asegúrate de definirla en el archivo .env o en el sistema.")
        print("Ejemplo: DATABASE_URL=mysql+pymysql://usuario:contrasena@localhost/inventory")
        sys.exit(1)
        
    print(f"[-] Origen (SQLite):  {sqlite_uri}")
    print(f"[-] Destino (MySQL):  {mysql_uri}")
    print("\nIMPORTANTE:")
    print("Antes de ejecutar este script, asegúrate de haber inicializado")
    print("las tablas en MySQL ejecutando: flask db upgrade")
    print("Esto asegura que todas las tablas y columnas existan correctamente.\n")
    
    confirm = input("¿Estás seguro de comenzar a copiar los datos? (s/N): ")
    if confirm.lower() != 's':
        print("Migración cancelada.")
        sys.exit(0)

    try:
        sqlite_engine = create_engine(sqlite_uri)
        mysql_engine = create_engine(mysql_uri)
        
        meta = MetaData()
        print("\n[+] Reflejando esquema de base de datos origen...")
        meta.reflect(bind=sqlite_engine)
        
        SqliteSession = sessionmaker(bind=sqlite_engine)
        MysqlSession = sessionmaker(bind=mysql_engine)
        
        sqlite_session = SqliteSession()
        mysql_session = MysqlSession()
        
        # Desactivamos restricciones de clave foránea temporalmente en la sesión de destino
        # para evitar problemas si las tablas se insertan con dependencias mutuas.
        mysql_session.execute(mysql_engine.text('SET FOREIGN_KEY_CHECKS=0;'))
        
        for table in meta.sorted_tables:
            print(f"  -> Procesando tabla '{table.name}'...", end=" ")
            
            # Saltamos la tabla de migraciones para no interferir con alembic en el destino
            if table.name == 'alembic_version':
                print("Saltada (versión interna).")
                continue
                
            # Limpiamos la tabla destino por si tiene datos viejos (opcional, pero recomendado)
            mysql_session.execute(mysql_engine.text(f'TRUNCATE TABLE `{table.name}`;'))
            
            # Leemos desde SQLite
            records = sqlite_session.execute(table.select()).mappings().all()
            
            if records:
                # Insertamos en MySQL
                mysql_session.execute(table.insert(), [dict(r) for r in records])
                print(f"Copiados {len(records)} registros.")
            else:
                print("Sin datos.")
                
        # Reactivamos Foreign Keys
        mysql_session.execute(mysql_engine.text('SET FOREIGN_KEY_CHECKS=1;'))
        mysql_session.commit()
        
        print("\n[✔] ¡Migración de datos completada exitosamente!")
        
    except Exception as e:
        print(f"\n[X] Ocurrió un error durante la migración: {e}")
        if 'mysql_session' in locals():
            mysql_session.rollback()
        sys.exit(1)
    finally:
        if 'sqlite_session' in locals(): sqlite_session.close()
        if 'mysql_session' in locals(): mysql_session.close()

if __name__ == '__main__':
    main()
