# strategy/indicators.py
import pandas as pd
import ta

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Añade indicadores técnicos al DataFrame de velas usando la librería 'ta'."""
    if df.empty or len(df) < 50:
        return df

    # Tendencia: Medias Móviles Exponenciales
    df['ema_20'] = ta.trend.ema_indicator(df['close'], window=20)
    df['ema_50'] = ta.trend.ema_indicator(df['close'], window=50)

    # Momentum: RSI
    df['rsi'] = ta.momentum.rsi(df['close'], window=14)

    # Volatilidad: Average True Range (ATR)
    df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)

    # Confirmación: Volumen Relativo (Volumen actual vs Media Móvil de Volumen de 20 periodos)
    df['vol_sma_20'] = df['volume'].rolling(window=20).mean()
    df['rel_volume'] = df['volume'] / df['vol_sma_20']

    # 1. Diferencia porcentual entre EMAs (Agnóstico al precio)
    df['ema_diff_pct'] = ((df['ema_20'] - df['ema_50']) / df['ema_50']) * 100

    # 2. Volatilidad porcentual (ATR como % del precio actual)
    df['atr_pct'] = (df['atr'] / df['close']) * 100

    # Limpiamos los valores NaN (nulos) que se generan en los primeros cálculos
    return df.dropna()