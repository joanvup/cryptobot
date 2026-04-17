# main.py
import threading
import time
import datetime
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from config.settings import settings
from db.database import engine, Base, get_db
from db.models import Trade, SystemLog
from core.orchestrator import BotOrchestrator
from execution.trade_monitor import TradeMonitor
from core.logger import setup_logger
from exchange.binance_client import BinanceFuturesClient
# Importamos la lógica de entrenamiento
from train_me import run_adaptive_training

# 1. Logger Profesional y Base de Datos
logger = setup_logger()
Base.metadata.create_all(bind=engine)

# 2. INSTANCIA COMPARTIDA (Keep-Alive)
shared_client = BinanceFuturesClient()
last_radar_scan = []

# --- PROCESOS EN SEGUNDO PLANO ---

def run_trade_monitor():
    """Vigila posiciones y gestiona Trailing Stop."""
    monitor = TradeMonitor()
    monitor.exchange = shared_client # Inyectamos cliente compartido
    monitor.run_forever()

def run_radar_updates():
    """Actualiza el Radar IA con telemetría cada X segundos e inyecta el Funding Rate."""
    global last_radar_scan
    orchestrator = BotOrchestrator()
    orchestrator.client = shared_client
    
    logger.info(f"📡 Radar IA Telemetry iniciado ({settings.RADAR_INTERVAL_SECONDS}s)")
    
    while True:
        try:
            symbols_to_scan = orchestrator.scanner.get_symbols_to_trade()
            current_radar = []

            for s in symbols_to_scan:
                symbol = s['symbol']
                
                # --- NUEVA INYECCIÓN DE FUNDING ---
                funding = shared_client.get_funding_rate(symbol)
                
                # Pedir klines usando la sesión compartida
                df = shared_client.get_historical_klines(symbol, interval=settings.DEFAULT_TIMEFRAME)
                
                # Analizar pasando el Funding Rate real para telemetría y filtrado
                analysis = orchestrator.strategy.analyze(df, funding_rate=funding)
                
                current_radar.append({
                    "symbol": symbol,
                    "price": s['last_price'],
                    "signal": analysis['signal'],
                    "tech_signal": analysis.get('tech_signal', 'NEUTRAL'),
                    "confidence": analysis.get('ai_confidence', 0.5) * 100,
                    "indicators": analysis.get('indicators', {}),
                    "change": s.get('abs_change', 0)
                })
            
            last_radar_scan = current_radar
        except Exception as e:
            logger.error(f"Error en Radar Thread: {e}")
            time.sleep(10)
        
        time.sleep(settings.RADAR_INTERVAL_SECONDS)

def run_trading_cycles():
    """Ciclo de ejecución de órdenes reales inyectando lógica de Funding."""
    orchestrator = BotOrchestrator()
    orchestrator.client = shared_client
    logger.info(f"🚀 Trader Core iniciado (Ciclos: {settings.CYCLE_INTERVAL_SECONDS}s)")
    
    while settings.AUTO_TRADING:
        try:
            # El orquestador ahora internamente consultará el funding rate para filtrar trades
            orchestrator.run_single_cycle()
        except Exception as e:
            logger.error(f"Falla en Ciclo Trader: {e}")
        time.sleep(settings.CYCLE_INTERVAL_SECONDS)

def run_auto_trainer():
    """Hilo de MLOps: Reentrena el modelo automáticamente en el día/hora configurado."""
    if not settings.AUTO_RETRAIN_ENABLED:
        return

    dias =["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_str = dias[settings.AUTO_RETRAIN_DAY] if 0 <= settings.AUTO_RETRAIN_DAY <= 6 else "Desconocido"
    logger.info(f"🤖 Auto-Trainer MLOps Activo. Sincronizado para: {dia_str} a las {settings.AUTO_RETRAIN_HOUR}:00")
    
    last_train_date = None

    while True:
        try:
            now = datetime.datetime.now()
            # Validamos si es el día y la hora correctos
            if now.weekday() == settings.AUTO_RETRAIN_DAY and now.hour == settings.AUTO_RETRAIN_HOUR:
                # Verificamos que no se haya entrenado ya hoy
                if last_train_date != now.date():
                    logger.warning("⚙️ [MLOps] Iniciando Reentrenamiento Automático de la IA...")
                    run_adaptive_training()
                    last_train_date = now.date()
                    logger.info("✅ [MLOps] Reentrenamiento Finalizado. La IA ha sido actualizada.")
        except Exception as e:
            logger.error(f"❌ Error en Auto-Trainer: {e}")
        
        # Duerme 1 hora antes de volver a mirar el reloj (3600 segundos)
        time.sleep(3600)

# 3. Lifespan de FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    t_monitor = threading.Thread(target=run_trade_monitor, name="Monitor", daemon=True)
    t_radar = threading.Thread(target=run_radar_updates, name="Radar", daemon=True)
    t_trading = threading.Thread(target=run_trading_cycles, name="Trader", daemon=True)
    t_trainer = threading.Thread(target=run_auto_trainer, name="AutoTrainer", daemon=True)
    
    t_monitor.start()
    t_radar.start()
    t_trainer.start()
    
    if settings.AUTO_TRADING:
        t_trading.start()
    
    yield
    logger.info("Kernel Quantum Shuting Down...")

app = FastAPI(title="AI Quant Terminal v3.0", lifespan=lifespan)

# --- RUTAS DE API ---

@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/balance")
def get_balance():
    try:
        balance_data = shared_client.get_usdt_balance()
        return balance_data
    except Exception as e:
        logger.error(f"Balance API Error: {e}")
        return {"total_balance": 0, "unrealized_pnl": 0}

@app.get("/api/trades")
def get_trades(db: Session = Depends(get_db)):
    return {"trades": db.query(Trade).order_by(Trade.entry_time.desc()).limit(50).all()}

@app.get("/api/logs")
def get_logs(db: Session = Depends(get_db)):
    return {"logs": db.query(SystemLog).order_by(SystemLog.timestamp.desc()).limit(20).all()}

@app.get("/api/radar")
def get_radar():
    return {"radar": last_radar_scan}

@app.get("/api/bot-settings")
def get_bot_settings():
    return {
        "run_mode": settings.RUN_MODE, # NUEVO
        "max_trades": settings.MAX_OPEN_TRADES,
        "be_r": settings.TS_PHASE1_ACTIVATION_ATR,
        "ts1_r": settings.TS_PHASE2_ACTIVATION_ATR,
        "ts2_r": settings.TS_PHASE3_ACTIVATION_ATR,
        "tp_r": settings.ATR_TP_MULTIPLIER,
        "risk_pct": settings.RISK_PER_TRADE_PERCENT
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8008, reload=False, access_log=False)