# core/orchestrator.py
from core.scanner import MarketScanner
from strategy.core import HybridStrategy
from execution.risk_manager import RiskManager
from execution.order_manager import OrderManager
from exchange.binance_client import BinanceFuturesClient
from db.database import SessionLocal
from db.models import Trade
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class BotOrchestrator:
    def __init__(self):
        self.scanner = MarketScanner()
        self.strategy = HybridStrategy()
        self.risk_manager = RiskManager()
        self.order_manager = OrderManager()
        self.client = BinanceFuturesClient()

    def _get_open_trades_info(self):
        """Consulta la DB para ver cuántos trades hay y qué símbolos están ocupados."""
        db = SessionLocal()
        try:
            open_trades = db.query(Trade.symbol).filter(Trade.is_open == True).all()
            symbols =[t.symbol for t in open_trades]
            return len(symbols), symbols
        finally:
            db.close()

    def run_single_cycle(self):
        """Ejecuta un ciclo completo de trading inyectando lógica de Funding Rate."""
        logger.info("--- Iniciando Ciclo de Trading Automático ---")
        
        # 1. Control de Riesgo Global
        open_count, active_symbols = self._get_open_trades_info()
        if open_count >= settings.MAX_OPEN_TRADES:
            logger.info(f"Límite de trades alcanzado ({open_count}/{settings.MAX_OPEN_TRADES}). Saltando ciclo.")
            return {"status": "Skipped"}

        symbols_to_analyze = self.scanner.get_symbols_to_trade()
        if not symbols_to_analyze:
            return {"status": "No_Symbols"}

        for coin in symbols_to_analyze:
            symbol = coin['symbol']
            
            # --- FILTRO 1: IGNORAR MONEDAS YA ACTIVAS ---
            if symbol in active_symbols:
                continue

            logger.info(f"Analizando oportunidad en {symbol}...")

            df = self.client.get_historical_klines(symbol, interval=settings.DEFAULT_TIMEFRAME)
            if df.empty: 
                continue

            # Inyectamos el funding rate
            funding = self.client.get_funding_rate(symbol)
            analysis = self.strategy.analyze(df, funding_rate=funding)
            
            if analysis['signal'] != 'NEUTRAL':
                logger.info(f"¡Señal Detectada! {analysis['signal']} en {symbol}. Motivo: {analysis['reason']}")
                
                balance_data = self.client.get_usdt_balance()
                equity = balance_data.get('total_balance', 0)
                available = balance_data.get('available', 0)
                
                if equity <= 0:
                    logger.error("Balance insuficiente o inválido. Abortando.")
                    continue

                risk_data = self.risk_manager.calculate_trade_parameters(
                    balance_usdt=equity,
                    current_price=analysis['close_price'],
                    atr=analysis['atr'],
                    side=analysis['signal'],
                    available_balance=available 
                )
                
                if risk_data:
                    logger.info(f"Enviando orden de {analysis['signal']} para {symbol}...")
                    
                    # --- CORRECCIÓN: Nombres de los argumentos actualizados ---
                    result = self.order_manager.execute_trade(
                        symbol=symbol,
                        side=analysis['signal'],
                        quantity=risk_data['position_size_qty'],
                        stop_loss_est=risk_data['stop_loss'],     # Corregido aquí
                        take_profit_est=risk_data['take_profit'], # Corregido aquí
                        atr=analysis['atr']
                    )
                    
                    if result.get("status") == "success":
                        active_symbols.append(symbol)
                        logger.info(f"✅ Ejecución exitosa en {symbol}")
                        return {"status": "Trade_Executed", "symbol": symbol}
                    else:
                        logger.error(f"❌ Error en OrderManager para {symbol}: {result.get('message')}")
        
        logger.info("Ciclo terminado: No se encontraron señales válidas.")
        return {"status": "No_Signal"}