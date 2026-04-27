"""
Script para inicializar la base de datos
"""
from database.db_session import init_db, engine
from database.models import Base

def create_all_tables():
    """Crea todas las tablas en la base de datos"""
    print("🔧 Creando tablas...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas creadas exitosamente")
    
    # Mostrar tablas creadas
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\n📋 Tablas en la base de datos: {tables}")

if __name__ == "__main__":
    create_all_tables()
