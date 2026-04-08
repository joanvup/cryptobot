# execution/risk_manager.py
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self):
        self.risk_per_trade_pct = settings.RISK_PER_TRADE_PERCENT / 100.0
        self.atr_sl_multiplier = settings.ATR_SL_MULTIPLIER
        self.atr_tp_multiplier = settings.ATR_TP_MULTIPLIER
        self.leverage = settings.DEFAULT_LEVERAGE

    def calculate_trade_parameters(self, balance_usdt: float, current_price: float, atr: float, side: str, available_balance: float = None) -> dict:
        """Calcula parámetros de trade con protecciones para precios bajos y margen."""
        
        if available_balance is None:
            available_balance = balance_usdt

        # 1. Monto a arriesgar (USD)
        risk_amount_usdt = balance_usdt * self.risk_per_trade_pct

        # 2. Calcular SL y TP
        sl_dist = atr * self.atr_sl_multiplier
        tp_dist = atr * self.atr_tp_multiplier

        if side == "LONG":
            stop_loss = current_price - sl_dist
            take_profit = current_price + tp_dist
        else: # SHORT
            stop_loss = current_price + sl_dist
            take_profit = current_price - tp_dist

        # --- PROTECCIÓN ANTI-ERROR 4006 (Precios Negativos) ---
        # Si el TP o SL caen por debajo de cero (común en SHORTs de monedas baratas)
        # los limitamos al 10% del precio actual para mantener la orden válida.
        min_allowed_price = current_price * 0.1 
        if stop_loss <= 0: stop_loss = min_allowed_price
        if take_profit <= 0: take_profit = min_allowed_price

        # 3. Posicionamiento (Position Sizing)
        actual_sl_dist = abs(current_price - stop_loss)
        if actual_sl_dist <= 0: return {}

        position_size = risk_amount_usdt / actual_sl_dist
        current_notional = position_size * current_price

        # 4. Capa de seguridad de Margen (Anti-Error 2019)
        buying_power = available_balance * self.leverage
        max_notional_allowed = buying_power * 0.85 

        if current_notional > max_notional_allowed:
            logger.warning(f"⚠️ Posición ajustada por falta de margen libre. (Req: ${current_notional:.2f}, Max: ${max_notional_allowed:.2f})")
            position_size = max_notional_allowed / current_price
            current_notional = max_notional_allowed

        # 5. Validación final de valor nominal (Binance mínimo ~5-10 USDT)
        if current_notional < 5:
            logger.error(f"❌ Posición en {side} descartada: Valor nominal (${current_notional:.2f}) muy bajo.")
            return {}

        return {
            "risk_amount_usdt": round(risk_amount_usdt, 2),
            "position_size_qty": position_size, 
            "notional_value_usdt": round(current_notional, 2),
            "stop_loss": round(stop_loss, 6), # Aumentamos precisión para monedas baratas
            "take_profit": round(take_profit, 6)
        }