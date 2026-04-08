# core/logger.py
import logging
import sys
from db.database import SessionLocal
from db.models import SystemLog

class DatabaseLogHandler(logging.Handler):
    def emit(self, record):
        # Filtramos para que SQLAlchemy no intente loguearse a sí mismo (recursión)
        if record.name.startswith('sqlalchemy') or record.name.startswith('uvicorn'):
            return

        db = SessionLocal()
        try:
            log_entry = SystemLog(
                level=record.levelname,
                module=record.name,
                message=self.format(record)
            )
            db.add(log_entry)
            db.commit()
        except Exception:
            pass
        finally:
            db.close()

def setup_logger():
    """Configuración profesional de logging sin duplicados."""
    logger = logging.getLogger()
    
    # Si el logger ya tiene handlers, no añadimos más (evita duplicados)
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Database Handler
    db_handler = DatabaseLogHandler()
    db_handler.setFormatter(formatter)
    logger.addHandler(db_handler)
    
    # Silenciar logs específicos de librerías ruidosas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("binance").setLevel(logging.ERROR)
    
    return logger