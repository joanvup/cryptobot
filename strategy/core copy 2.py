# strategy/core.py
import pandas as pd
import logging
from strategy.indicators import add_indicators
from strategy.ai_model import CryptoAIModel
from config.settings import settings

logger = logging.getLogger(__name__)

class HybridStrategy:
    def __init__(self):
        self.rsi_ob = settings.RSI_OVERBOUGHT
        self.rsi_os = settings.RSI_OVERSOLD
        self.vol_threshold = settings.VOL_RELATIVE_THRESHOLD
        self.ai_threshold = settings.AI_CONFIDENCE_THRESHOLD
        self.max_funding = getattr(settings, 'MAX_FUNDING_RATE', 0.03)
        self.ai_model = CryptoAIModel(model_path=settings.MODEL_PATH)

    def analyze(self, df: pd.DataFrame, funding_rate: float = 0.0) -> dict:
        df = add_indicators(df)
        # Necesitamos al menos 2 velas (la cerrada y la que está en formación)
        if df.empty or len(df) < settings.EMA_SLOW + 2:
            return {"signal": "NEUTRAL", "reason": "Data insuficiente", "indicators": {}}

        # --- CORRECCIÓN CRÍTICA: EL SHIFT DE VELA ---
        closed_row = df.iloc[-2]  # Usamos la última vela CERRADA (100% volumen real)
        live_row = df.iloc[-1]    # Usamos la vela EN FORMACIÓN (Precio de ejecución real)
        
        ema_20 = float(closed_row['ema_20'])
        ema_50 = float(closed_row['ema_50'])
        rsi_val = float(closed_row['rsi'])
        rel_vol = float(closed_row['rel_volume'])
        
        indicators_data = {
            "rsi": rsi_val,
            "rel_vol": rel_vol,
            "trend": "UP" if ema_20 > ema_50 else "DOWN",
            "ema_diff": ((ema_20 / ema_50) - 1) * 100,
            "close": float(live_row['close']), # El dashboard mostrará el precio vivo
            "funding": funding_rate
        }

        # --- IA ACTIVA (Despierta con la vela cerrada) ---
        ai_probability = 0.5
        # Le damos un 20% de tolerancia al volumen para despertar a la IA y ver qué opina
        if rel_vol >= (self.vol_threshold * 0.8): 
            try:
                # Enviamos el DataFrame hasta la vela cerrada para la predicción
                ai_probability = float(self.ai_model.predict_probability(df.iloc[-2:-1]))
            except Exception as e:
                logger.warning(f"Falla IA: {e}")

        # --- LÓGICA DE SEÑALES (Basada en hechos consumados, no en formación) ---
        signal = "NEUTRAL"
        tech_reason = ""

        is_long_tech = (ema_20 > ema_50 and 50 < rsi_val < self.rsi_ob and rel_vol > self.vol_threshold)
        is_short_tech = (ema_20 < ema_50 and self.rsi_os < rsi_val < 50 and rel_vol > self.vol_threshold)

        if is_long_tech:
            signal = "LONG"
            tech_reason = "Estructura Alcista"
        elif is_short_tech:
            signal = "SHORT"
            tech_reason = "Estructura Bajista"

        # Filtro de Costos
        if signal == "LONG" and funding_rate > self.max_funding:
            signal = "NEUTRAL"
            tech_reason = f"High Funding ({funding_rate*100:.3f}%)"
        elif signal == "SHORT" and funding_rate < -self.max_funding:
            signal = "NEUTRAL"
            tech_reason = f"High Funding ({funding_rate*100:.3f}%)"

        # Filtro final de IA
        final_signal = signal
        final_reason = tech_reason if tech_reason else "Sin señal"
        
        if signal != "NEUTRAL" and ai_probability < self.ai_threshold:
            final_signal = "NEUTRAL"
            final_reason = f"AI Veto ({ai_probability:.2f})"

        return {
            "signal": final_signal,
            "reason": final_reason if final_signal == "NEUTRAL" else f"{tech_reason} | IA: {ai_probability:.2f}",
            "indicators": indicators_data,
            "ai_confidence": ai_probability,
            "close_price": indicators_data['close'],     # Precio de ejecución en vivo
            "atr": float(closed_row['atr'])              # ATR cerrado para SL estable
        }