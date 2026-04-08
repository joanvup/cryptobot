# execution/trade_monitor.py
import time
import logging
from datetime import datetime
from db.database import SessionLocal
from db.models import Trade
from exchange.binance_client import BinanceFuturesClient
from execution.order_manager import OrderManager
from config.settings import settings

logger = logging.getLogger(__name__)

class TradeMonitor:
    def __init__(self):
        self.exchange = BinanceFuturesClient()
        self.order_manager = OrderManager()

    def check_open_positions(self):
        db = SessionLocal()
        try:
            # Solo monitoreamos trades que correspondan al modo actual
            open_trades = db.query(Trade).filter(Trade.is_open == True, Trade.run_mode == settings.RUN_MODE).all()
            if not open_trades: return

            tickers = self.exchange.client.futures_symbol_ticker()
            prices = {t['symbol']: float(t['price']) for t in tickers}

            for trade in open_trades:
                current_price = prices.get(trade.symbol)
                if current_price is None: continue

                # 1. En DRY_RUN Binance no sabe de la posición, saltamos este chequeo
                if settings.RUN_MODE != 'DRY_RUN':
                    if self._check_if_closed(trade.symbol):
                        self._close_in_db(db, trade, current_price, "HARD_STOP_OR_TP")
                        continue

                # 2. Gatillo Virtual (Sirve para Dry Run y Mainnet)
                virtual_sl_hit = False
                virtual_tp_hit = False

                if trade.side == 'LONG':
                    if current_price <= trade.current_stop_loss: virtual_sl_hit = True
                    if current_price >= trade.take_profit: virtual_tp_hit = True
                else:
                    if current_price >= trade.current_stop_loss: virtual_sl_hit = True
                    if current_price <= trade.take_profit: virtual_tp_hit = True

                if virtual_sl_hit or virtual_tp_hit:
                    reason = f"VIRTUAL_SL (Fase {trade.trailing_phase})" if virtual_sl_hit else "VIRTUAL_TP"
                    logger.warning(f"🎯[{trade.symbol}] Objetivo Virtual Alcanzado. Ejecutando cierre...")
                    
                    res = self.order_manager.close_position_market(trade.symbol, trade.side, trade.position_size)
                    
                    if res['status'] == 'success':
                        exit_p = res.get('exit_price', current_price)
                        self._close_in_db(db, trade, exit_p, reason)
                    continue

                # 3. Lógica MSTS
                if settings.TRAILING_STOP_ENABLED:
                    self._process_virtual_trailing(db, trade, current_price)
                    
        finally:
            db.close()

    def _check_if_closed(self, symbol):
        try:
            pos = self.exchange.client.futures_position_information(symbol=symbol)
            for p in pos:
                if p['symbol'] == symbol:
                    return float(p['positionAmt']) == 0
            return True
        except: return False

    def _process_virtual_trailing(self, db, trade, current_p):
        atr = trade.atr_at_entry
        updated = False

        if trade.side == 'LONG':
            if current_p > trade.extreme_price: trade.extreme_price = current_p
            max_profit_atr = (trade.extreme_price - trade.entry_price) / atr
        else:
            if current_p < trade.extreme_price: trade.extreme_price = current_p
            max_profit_atr = (trade.entry_price - trade.extreme_price) / atr

        new_phase = trade.trailing_phase
        if max_profit_atr >= settings.TS_PHASE3_ACTIVATION_ATR: new_phase = 3
        elif max_profit_atr >= settings.TS_PHASE2_ACTIVATION_ATR: new_phase = 2
        elif max_profit_atr >= settings.TS_PHASE1_ACTIVATION_ATR: new_phase = 1

        if new_phase > trade.trailing_phase:
            trade.trailing_phase = new_phase
            trade.trailing_activated = True
            logger.info(f"🚀 [{trade.symbol}] Virtual Trailing avanzó a FASE {new_phase}")
            updated = True

        target_sl = trade.current_stop_loss
        if trade.trailing_phase >= 1:
            if trade.side == 'LONG':
                if trade.trailing_phase == 1: target_sl = trade.entry_price
                elif trade.trailing_phase == 2: target_sl = trade.extreme_price - (atr * settings.TS_PHASE2_DISTANCE_ATR)
                elif trade.trailing_phase == 3: target_sl = trade.extreme_price - (atr * settings.TS_PHASE3_DISTANCE_ATR)
                if target_sl > trade.current_stop_loss:
                    trade.current_stop_loss = target_sl
                    updated = True
            elif trade.side == 'SHORT':
                if trade.trailing_phase == 1: target_sl = trade.entry_price
                elif trade.trailing_phase == 2: target_sl = trade.extreme_price + (atr * settings.TS_PHASE2_DISTANCE_ATR)
                elif trade.trailing_phase == 3: target_sl = trade.extreme_price + (atr * settings.TS_PHASE3_DISTANCE_ATR)
                if target_sl < trade.current_stop_loss:
                    trade.current_stop_loss = target_sl
                    updated = True

        if updated:
            db.commit()
            logger.info(f"🛡️[{trade.symbol}] SL Virtual Asegurado en {trade.current_stop_loss:.4f}")

    def _close_in_db(self, db, trade, exit_p, reason):
        trade.is_open = False
        trade.exit_price = exit_p
        trade.exit_time = datetime.utcnow()
        trade.close_reason = reason
        mult = 1 if trade.side == 'LONG' else -1
        
        # Descontar comisiones simuladas en Dry Run (0.08% total)
        pnl = (exit_p - trade.entry_price) * trade.position_size * mult
        if settings.RUN_MODE == 'DRY_RUN':
            fee = (trade.entry_price * trade.position_size * 0.0008)
            pnl -= fee
            
        trade.pnl = pnl
        db.commit()
        logger.info(f"🏁 TRADE CERRADO ({settings.RUN_MODE}): {trade.symbol} | Razón: {reason} | PNL: {trade.pnl:.2f} USDT")

    def run_forever(self):
        logger.info(f"📡 Monitor Virtual MSTS iniciado ({settings.MONITOR_INTERVAL_SECONDS}s)")
        while True:
            try: self.check_open_positions()
            except Exception as e: logger.error(f"Falla monitor: {e}")
            time.sleep(settings.MONITOR_INTERVAL_SECONDS)