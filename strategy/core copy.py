# strategy/core.py
import pandas as pd
import logging
from strategy.indicators import add_indicators
from strategy.ai_model import CryptoAIModel
from config.settings import settings

logger = logging.getLogger(__name__)

class HybridStrategy:
    def __init__(self):
        # Hiperparámetros desde configuración centralizada
        self.rsi_ob = settings.RSI_OVERBOUGHT
        self.rsi_os = settings.RSI_OVERSOLD
        self.vol_threshold = settings.VOL_RELATIVE_THRESHOLD
        self.ai_threshold = settings.AI_CONFIDENCE_THRESHOLD
        
        # Límite de comisión de financiación (Ej: 0.03)
        self.max_funding = getattr(settings, 'MAX_FUNDING_RATE', 0.03)
        
        # Modelo cargado desde la ruta configurada
        self.ai_model = CryptoAIModel(model_path=settings.MODEL_PATH)

    def analyze(self, df: pd.DataFrame, funding_rate: float = 0.0) -> dict:
        """
        Analiza el mercado integrando:
        1. Indicadores Técnicos (EMA/RSI/VOL)
        2. Filtro de Inteligencia Artificial (XGBoost)
        3. Filtro de Costos de Financiación (Funding Rate)
        """
        # 1. Preparación de datos
        df = add_indicators(df)
        if df.empty or len(df) < settings.EMA_SLOW:
            return {"signal": "NEUTRAL", "reason": "Data insuficiente", "indicators": {}}

        last_row = df.iloc[-1]
        
        # --- EXTRACCIÓN DE TELEMETRÍA (Para el Radar) ---
        ema_20 = float(last_row['ema_20'])
        ema_50 = float(last_row['ema_50'])
        rsi_val = float(last_row['rsi'])
        rel_vol = float(last_row['rel_volume'])
        
        indicators_data = {
            "rsi": rsi_val,
            "rel_vol": rel_vol,
            "trend": "UP" if ema_20 > ema_50 else "DOWN",
            "ema_diff": ((ema_20 / ema_50) - 1) * 100,
            "close": float(last_row['close']),
            "funding": funding_rate  # Telemetría para el Dashboard
        }

        signal = "NEUTRAL"
        tech_reason = ""

        # --- NIVEL 1: LÓGICA TÉCNICA (FILTRO BASE) ---
        is_long_tech = (ema_20 > ema_50 and 50 < rsi_val < self.rsi_ob and rel_vol > self.vol_threshold)
        is_short_tech = (ema_20 < ema_50 and self.rsi_os < rsi_val < 50 and rel_vol > self.vol_threshold)

        if is_long_tech:
            signal = "LONG"
            tech_reason = "Estructura Alcista + Momentum"
        elif is_short_tech:
            signal = "SHORT"
            tech_reason = "Estructura Bajista + Momentum"

        # --- NIVEL 2: FILTRO DE COSTOS (FUNDING RATE) ---
        if signal == "LONG" and funding_rate > self.max_funding:
            logger.warning(f"🚫 Señal LONG descartada: Funding Rate muy alto ({funding_rate*100:.4f}%)")
            return {
                "signal": "NEUTRAL",
                "reason": f"High Funding Cost ({funding_rate*100:.3f}%)",
                "indicators": indicators_data,
                "ai_confidence": 0.0,
                "close_price": indicators_data['close'],
                "atr": float(last_row['atr'])
            }
        
        if signal == "SHORT" and funding_rate < -self.max_funding:
            logger.warning(f"🚫 Señal SHORT descartada: Funding Rate muy negativo ({funding_rate*100:.4f}%)")
            return {
                "signal": "NEUTRAL",
                "reason": f"High Funding Cost ({funding_rate*100:.3f}%)",
                "indicators": indicators_data,
                "ai_confidence": 0.0,
                "close_price": indicators_data['close'],
                "atr": float(last_row['atr'])
            }

        # --- NIVEL 3: VALIDACIÓN CON IA ---
        ai_probability = 0.5
        if signal != "NEUTRAL":
            try:
                # La IA predice sobre la última fila de indicadores
                ai_probability = self.ai_model.predict_probability(df.tail(1))
                
                if ai_probability < self.ai_threshold:
                    return {
                        "signal": "NEUTRAL",
                        "reason": f"AI Filtered ({ai_probability:.2f})",
                        "indicators": indicators_data,
                        "ai_confidence": ai_probability,
                        "close_price": indicators_data['close'],
                        "atr": float(last_row['atr'])
                    }
                
                # SEÑAL CONFIRMADA POR TODOS LOS FILTROS
                return {
                    "signal": signal,
                    "reason": f"{tech_reason} | IA: {ai_probability:.2f}",
                    "indicators": indicators_data,
                    "ai_confidence": ai_probability,
                    "close_price": indicators_data['close'],
                    "atr": float(last_row['atr'])
                }
            except Exception as e:
                logger.warning(f"Falla Inferencia IA: {e}")
                return {
                    "signal": signal, 
                    "reason": f"{tech_reason} (No IA)", 
                    "indicators": indicators_data,
                    "ai_confidence": 0.5,
                    "close_price": indicators_data['close'],
                    "atr": float(last_row['atr'])
                }

        # Retorno por defecto (NEUTRAL)
        return {
            "signal": "NEUTRAL", 
            "reason": "Sin señal técnica", 
            "indicators": indicators_data,
            "ai_confidence": 0.5,
            "close_price": indicators_data['close'],
            "atr": float(last_row['atr'])
        }