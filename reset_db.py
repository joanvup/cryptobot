# reset_db.py
import logging
from db.database import engine, Base
# Es OBLIGATORIO importar los modelos para que SQLAlchemy sepa qué tablas existen
from db.models import Trade, SystemLog 

# Configuración básica de logs para la consola
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DB_Manager")

def reset_database():
    logger.warning("⚠️ INICIANDO RESETEO COMPLETO DE BASE DE DATOS...")
    
    try:
        # 1. Borrar todas las tablas
        logger.info("Borrando tablas existentes (trades, system_logs)...")
        Base.metadata.drop_all(bind=engine)
        logger.info("Tablas eliminadas con éxito.")

        # 2. Recrear todas las tablas con los esquemas actualizados
        logger.info("Creando tablas nuevas desde cero...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tablas creadas con éxito. La base de datos está completamente limpia.")
        
    except Exception as e:
        logger.error(f"❌ Error crítico durante el reseteo: {e}")

if __name__ == "__main__":
    print("="*50)
    print(" PELIGRO: ESTA ACCIÓN BORRARÁ TODO EL HISTORIAL DE TRADES Y LOGS")
    print("="*50)
    
    # Pequeña medida de seguridad para evitar accidentes si lo ejecutas por error
    confirm = input("¿Estás 100% seguro de formatear la base de datos? (y/n): ")
    
    if confirm.lower() == 'y':
        reset_database()
    else:
        print("Operación cancelada. Tus datos están a salvo.")