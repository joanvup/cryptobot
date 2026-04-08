# core/ai_trainer.py
import pandas as pd
from exchange.binance_client import BinanceFuturesClient
from strategy.indicators import add_indicators
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class AITrainer:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.client = BinanceFuturesClient()
        self.limit = settings.TRAINING_LIMIT_KLINES
        self.interval = settings.DEFAULT_TIMEFRAME

    def prepare_training_data(self):
        logger.info(f"Recolectando {self.limit} velas ({self.interval}) para {self.symbol}...")
        
        df = self.client.get_historical_klines(
            symbol=self.symbol, 
            interval=self.interval, 
            limit=self.limit
        )
        
        if df.empty:
            return None

        df = add_indicators(df)

        # Etiquetado basado en ATR para mayor robustez técnica
        horizon = 12
        labels = []
        for i in range(len(df) - horizon):
            entry_price = df['close'].iloc[i]
            atr = df['atr'].iloc[i]
            
            # SL y TP dinámicos basados en la volatilidad de ese momento
            sl_price = entry_price - (atr * settings.ATR_SL_MULTIPLIER)
            tp_price = entry_price + (atr * settings.ATR_TP_MULTIPLIER)
            
            future_data = df.iloc[i+1 : i+1+horizon]
            win = False
            for _, row in future_data.iterrows():
                if row['low'] <= sl_price: break # Toca SL primero
                if row['high'] >= tp_price: 
                    win = True
                    break
            labels.append(1 if win else 0)

        df_final = df.iloc[:len(labels)].copy()
        df_final['target'] = labels
        
        filename = f"data_training_{self.symbol}.csv"
        df_final.to_csv(filename, index=False)
        return df_final