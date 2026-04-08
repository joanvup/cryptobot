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

    # Limpiamos los valores NaN (nulos) que se generan en los primeros cálculos
    return df.dropna()