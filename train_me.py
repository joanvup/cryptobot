# train_me.py
import os
import pandas as pd
import logging
from core.ai_trainer import AITrainer
from strategy.ai_model import CryptoAIModel
from core.scanner import MarketScanner
from config.settings import settings

# Configuración de Logs Profesionales
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_adaptive_training():
    """
    Entrena el modelo basándose en la configuración del .env.
    Si USE_SCANNER es True, entrena con las monedas más volátiles del momento.
    Si es False, usa la WHITELIST fija.
    """
    scanner = MarketScanner()
    
    # 1. Obtener símbolos dinámicamente según el modo configurado
    # Reutilizamos la lógica exacta que usa el bot para operar
    selected_symbols_data = scanner.get_symbols_to_trade()
    symbols = [s['symbol'] for s in selected_symbols_data]

    if not symbols:
        logger.error("❌ No se encontraron símbolos para entrenar. Revisa los filtros de volumen.")
        return

    all_data = []
    logger.info(f"🧠 Iniciando entrenamiento ADAPTATIVO con {len(symbols)} activos.")

    # 2. Recolección de datos históricos para cada símbolo detectado
    for symbol in symbols:
        try:
            trainer = AITrainer(symbol=symbol)
            df = trainer.prepare_training_data()
            if df is not None and not df.empty:
                all_data.append(df)
                logger.info(f"✅ Datos de {symbol} integrados.")
            else:
                logger.warning(f"⚠️ {symbol} no devolvió datos suficientes.")
        except Exception as e:
            logger.error(f"Error procesando {symbol}: {e}")

    if not all_data:
        logger.error("❌ Dataset vacío. No se puede entrenar.")
        return

    # 3. Consolidación del Dataset Maestro
    master_df = pd.concat(all_data, ignore_index=True)
    master_csv = "data_training_adaptive.csv"
    master_df.to_csv(master_csv, index=False)
    
    logger.info(f"📊 Dataset Maestro consolidado: {len(master_df)} filas.")

    # 4. Entrenamiento del Modelo Global (XGBoost)
    ai_model = CryptoAIModel(model_path=settings.MODEL_PATH)
    # El método train interno guarda el .pkl automáticamente
    msg = ai_model.train(master_csv)
    
    logger.info(f"🏆 Resultado: {msg}")
    logger.info(f"📍 Modelo guardado en: {settings.MODEL_PATH}")

if __name__ == "__main__":
    # Asegurar que existe la carpeta de modelos
    model_dir = os.path.dirname(settings.MODEL_PATH)
    if model_dir and not os.path.exists(model_dir):
        os.makedirs(model_dir)
        
    run_adaptive_training()