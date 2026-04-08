# execution/order_manager.py
from exchange.binance_client import BinanceFuturesClient
from db.database import SessionLocal
from db.models import Trade
from config.settings import settings
import logging
import time

logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self):
        self.exchange = BinanceFuturesClient()
        self.client = self.exchange.client

    def _get_precision(self, value):
        str_val = str(float(value)).rstrip('0')
        return len(str_val.split('.')[1]) if '.' in str_val else 0

    def get_symbol_rules(self, symbol: str):
        try:
            info = self.client.futures_exchange_info()
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    q_filter = next(f for f in s['filters'] if f['filterType'] == 'LOT_SIZE')
                    p_filter = next(f for f in s['filters'] if f['filterType'] == 'PRICE_FILTER')
                    return {"qty_precision": self._get_precision(q_filter['stepSize']), "price_precision": self._get_precision(p_filter['tickSize'])}
            return {"qty_precision": 3, "price_precision": 2}
        except: return {"qty_precision": 3, "price_precision": 2}

    def execute_trade(self, symbol: str, side: str, quantity: float, stop_loss_est: float, take_profit_est: float, atr: float):
        rules = self.get_symbol_rules(symbol)
        qty_str = "{:0.{}f}".format(quantity, rules['qty_precision'])
        binance_side = 'BUY' if side == 'LONG' else 'SELL'
        opposite_side = 'SELL' if side == 'LONG' else 'BUY'
        
        # --- MODO DRY RUN (BYPASS) ---
        if settings.RUN_MODE == 'DRY_RUN':
            logger.info(f"👻[DRY RUN] Simulando ejecución de MARKET {side} en {symbol}...")
            current_p = float(self.client.futures_symbol_ticker(symbol=symbol)['price'])
            
            # Simulamos Slippage del 0.05%
            slippage = current_p * 0.0005
            entry_p = current_p + slippage if side == 'LONG' else current_p - slippage

            sl_dist = atr * settings.ATR_SL_MULTIPLIER
            tp_dist = atr * settings.ATR_TP_MULTIPLIER
            real_sl = entry_p - sl_dist if side == 'LONG' else entry_p + sl_dist
            real_tp = entry_p + tp_dist if side == 'LONG' else entry_p - tp_dist
            
            sl_str = "{:0.{}f}".format(real_sl, rules['price_precision'])
            tp_str = "{:0.{}f}".format(real_tp, rules['price_precision'])
            
            self._save_trade_to_db(symbol, side, None, qty_str, sl_str, tp_str, atr, simulated_entry=entry_p)
            return {"status": "success"}

        # --- MODO REAL (MAINNET/TESTNET) ---
        try:
            try: self.client.futures_cancel_all_open_orders(symbol=symbol); time.sleep(0.5)
            except: pass

            self.client.futures_change_leverage(symbol=symbol, leverage=settings.DEFAULT_LEVERAGE)
            
            logger.info(f"⚡ Enviando orden MARKET {side} en {symbol}...")
            entry_order = self.client.futures_create_order(symbol=symbol, side=binance_side, type='MARKET', quantity=qty_str)

            entry_p = float(entry_order.get('avgPrice', 0))
            if entry_p == 0: entry_p = float(entry_order.get('price', 0))
            if entry_p == 0:
                time.sleep(0.5)
                pos_info = self.client.futures_position_information(symbol=symbol)
                for p in pos_info:
                    if p['symbol'] == symbol:
                        entry_p = float(p['entryPrice'])
                        break
            current_p = float(self.client.futures_symbol_ticker(symbol=symbol)['price'])
            if entry_p == 0: entry_p = current_p

            sl_dist = atr * settings.ATR_SL_MULTIPLIER
            tp_dist = atr * settings.ATR_TP_MULTIPLIER
            buffer = current_p * 0.002 
            
            if side == 'LONG':
                real_sl = entry_p - sl_dist
                real_tp = entry_p + tp_dist
                if real_sl >= current_p: real_sl = current_p - buffer
            else:
                real_sl = entry_p + sl_dist
                real_tp = entry_p - tp_dist
                if real_sl <= current_p: real_sl = current_p + buffer

            tick_size = 1 / (10 ** rules['price_precision'])
            if real_sl <= tick_size: real_sl = tick_size * 2
            if real_tp <= tick_size: real_tp = tick_size * 2

            sl_str = "{:0.{}f}".format(real_sl, rules['price_precision'])
            tp_str = "{:0.{}f}".format(real_tp, rules['price_precision'])

            try:
                self.client.futures_create_order(symbol=symbol, side=opposite_side, type='STOP_MARKET', stopPrice=sl_str, closePosition='true')
                self.client.futures_create_order(symbol=symbol, side=opposite_side, type='TAKE_PROFIT_MARKET', stopPrice=tp_str, closePosition='true')
            except Exception as sl_tp_error:
                logger.error(f"🚨 Falla Hard Stops en {symbol}. ABORTANDO...")
                self.client.futures_create_order(symbol=symbol, side=opposite_side, type='MARKET', quantity=qty_str)
                return {"status": "error", "message": f"Rollback ejecutado: {sl_tp_error}"}

            self._save_trade_to_db(symbol, side, entry_order, qty_str, sl_str, tp_str, atr)
            return {"status": "success"}
        except Exception as e:
            logger.error(f"❌ Error crítico en ejecución {symbol}: {e}")
            return {"status": "error", "message": str(e)}

    def update_tracking_orders(self, symbol: str, side: str, new_sl_price: float, tp_price: float):
        if settings.RUN_MODE == 'DRY_RUN': return True # Bypass
        
        rules = self.get_symbol_rules(symbol)
        tick_size = 1 / (10 ** rules['price_precision'])
        if new_sl_price <= tick_size: new_sl_price = tick_size * 2
        if tp_price <= tick_size: tp_price = tick_size * 2
        sl_str = "{:0.{}f}".format(new_sl_price, rules['price_precision'])
        tp_str = "{:0.{}f}".format(tp_price, rules['price_precision'])
        opposite_side = 'SELL' if side == 'LONG' else 'BUY'
        
        try:
            self.client.futures_cancel_all_open_orders(symbol=symbol)
            time.sleep(1.0) 
            self.client.futures_create_order(symbol=symbol, side=opposite_side, type='STOP_MARKET', stopPrice=sl_str, closePosition='true')
            self.client.futures_create_order(symbol=symbol, side=opposite_side, type='TAKE_PROFIT_MARKET', stopPrice=tp_str, closePosition='true')
            return True
        except Exception as e:
            if "-4130" not in str(e): logger.error(f"Error actualizando órdenes {symbol}: {e}")
            return False

    def close_position_market(self, symbol: str, side: str, quantity: float):
        if settings.RUN_MODE == 'DRY_RUN':
            logger.info(f"👻 [DRY RUN] Simulando cierre de {symbol}...")
            current_p = float(self.client.futures_symbol_ticker(symbol=symbol)['price'])
            slippage = current_p * 0.0005
            exit_p = current_p - slippage if side == 'LONG' else current_p + slippage
            return {"status": "success", "exit_price": exit_p}

        rules = self.get_symbol_rules(symbol)
        qty_str = "{:0.{}f}".format(quantity, rules['qty_precision'])
        opposite_side = 'SELL' if side == 'LONG' else 'BUY'
        try:
            logger.info(f"⚡ Disparando Cierre MARKET para {symbol}...")
            close_order = self.client.futures_create_order(symbol=symbol, side=opposite_side, type='MARKET', quantity=qty_str, reduceOnly='true')
            try: self.client.futures_cancel_all_open_orders(symbol=symbol)
            except: pass
            exit_p = float(close_order.get('avgPrice', 0))
            if exit_p == 0: exit_p = float(close_order.get('price', 0))
            return {"status": "success", "exit_price": exit_p}
        except Exception as e:
            logger.error(f"❌ Error al cerrar posición {symbol}: {e}")
            return {"status": "error", "message": str(e)}

    def _save_trade_to_db(self, symbol, side, order, qty, sl, tp, atr, simulated_entry=None):
        db = SessionLocal()
        try:
            if settings.RUN_MODE == 'DRY_RUN' and simulated_entry:
                entry_p = simulated_entry
            else:
                entry_p = float(order.get('avgPrice', 0))
                if entry_p == 0: entry_p = float(order.get('price', 0))
                if entry_p == 0:
                    time.sleep(0.5)
                    pos_info = self.client.futures_position_information(symbol=symbol)
                    for p in pos_info:
                        if p['symbol'] == symbol:
                            entry_p = float(p['entryPrice'])
                            break
                current_p = float(self.client.futures_symbol_ticker(symbol=symbol)['price'])
                if entry_p == 0: entry_p = current_p

            new_trade = Trade(
                symbol=symbol, side=side, entry_price=entry_p,
                position_size=float(qty), initial_stop_loss=float(sl),
                current_stop_loss=float(sl), take_profit=float(tp),
                atr_at_entry=float(atr), is_open=True, extreme_price=entry_p,
                run_mode=settings.RUN_MODE # NUEVO: Guardamos el entorno en el que se hizo el trade
            )
            db.add(new_trade)
            db.commit()
            logger.info(f"📋 Trade registrado ({settings.RUN_MODE}). Precio: {entry_p} | Qty: {qty}")
        except Exception as e:
            logger.error(f"Error persistiendo trade: {e}")
        finally:
            db.close()