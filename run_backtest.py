# run_backtest.py
import pandas as pd
import numpy as np
import logging
import os
from strategy.indicators import add_indicators
from strategy.ai_model import CryptoAIModel
from execution.risk_manager import RiskManager
from config.settings import settings

# Configuración de Logs Profesionales
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

class HighSpeedBacktester:
    def __init__(self):
        # 1. Cargar Datos (Agnóstico al par)
        # Busca el CSV generado por el entrenamiento adaptativo
        self.csv_path = "data_training_adaptive.csv"
        if not os.path.exists(self.csv_path):
            logger.error(f"❌ Error: No se encontró {self.csv_path}. Ejecuta 'train_me.py' primero.")
            exit()

        self.df = pd.read_csv(self.csv_path)
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
        
        # 2. Inicializar Componentes Reales (Cero Hardcoding)
        self.ai_model = CryptoAIModel(model_path=settings.MODEL_PATH)
        self.rm = RiskManager()
        
        # 3. Estado de la Simulación
        self.initial_balance = 1000.0
        self.balance = self.initial_balance
        self.trades = []
        self.equity_curve = [self.initial_balance]

    def run(self):
        logger.info(f"🚀 Iniciando Backtest sobre {len(self.df)} velas...")
        
        # OPTIMIZACIÓN: Pre-calculamos todos los indicadores una sola vez (Vectorizado)
        logger.info("📊 Calculando indicadores técnicos...")
        self.df = add_indicators(self.df)
        
        # Filtramos filas con NaNs (donde las EMAs aún no tienen datos)
        valid_start = settings.EMA_SLOW + 1
        
        logger.info(f"🔍 Escaneando señales con IA (Confidence > {settings.AI_CONFIDENCE_THRESHOLD})...")
        
        for i in range(valid_start, len(self.df) - 1):
            row = self.df.iloc[i]
            
            # --- LÓGICA DE SEÑAL (Espejo de strategy/core.py) ---
            signal = "NEUTRAL"
            
            # Condición Técnica LONG
            if (row['ema_20'] > row['ema_50'] and 
                50 < row['rsi'] < settings.RSI_OVERBOUGHT and 
                row['rel_volume'] > settings.VOL_RELATIVE_THRESHOLD):
                signal = "LONG"
            
            # Condición Técnica SHORT
            elif (row['ema_20'] < row['ema_50'] and 
                  settings.RSI_OVERSOLD < row['rsi'] < 50 and 
                  row['rel_volume'] > settings.VOL_RELATIVE_THRESHOLD):
                signal = "SHORT"

            # --- FILTRO DE IA ---
            if signal != "NEUTRAL":
                # La IA recibe la fila actual para predecir
                # Convertimos la fila en un DataFrame de 1 fila para el modelo
                prob = self.ai_model.predict_probability(self.df.iloc[i:i+1])
                
                if prob >= settings.AI_CONFIDENCE_THRESHOLD:
                    self._simulate_execution(signal, i, prob)

        self._generate_report()

    def _simulate_execution(self, side, idx, ai_prob):
        row = self.df.iloc[idx]
        entry_price = row['close']
        atr = row['atr']
        
        # Usamos el RiskManager real para calcular SL, TP y Tamaño de Posición
        risk = self.rm.calculate_trade_parameters(self.balance, entry_price, atr, side)
        if not risk: return

        sl = risk['stop_loss']
        tp = risk['take_profit']
        
        # --- SIMULACIÓN DE SALIDA (Look-ahead) ---
        # Miramos las siguientes 24 velas (horizonte de tiempo)
        future_data = self.df.iloc[idx + 1 : idx + 25]
        
        result = None
        exit_price = 0
        
        for _, f_row in future_data.iterrows():
            if side == "LONG":
                if f_row['low'] <= sl: # Tocó Stop Loss
                    result = "LOSS"
                    exit_price = sl
                    break
                if f_row['high'] >= tp: # Tocó Take Profit
                    result = "WIN"
                    exit_price = tp
                    break
            else: # SHORT
                if f_row['high'] >= sl: # Tocó Stop Loss
                    result = "LOSS"
                    exit_price = sl
                    break
                if f_row['low'] <= tp: # Tocó Take Profit
                    result = "WIN"
                    exit_price = tp
                    break

        if result:
            # Cálculo de PNL Neto (incluyendo comisiones de 0.04% Taker)
            # El riesgo en USD es lo que calculó el RiskManager
            risk_usd = self.balance * (settings.RISK_PER_TRADE_PERCENT / 100)
            
            # Si es WIN, el profit es el ratio (ATR_TP / ATR_SL)
            ratio = settings.ATR_TP_MULTIPLIER / settings.ATR_SL_MULTIPLIER
            pnl_usd = (risk_usd * ratio) if result == "WIN" else -risk_usd
            
            # Restar comisiones (Entrada + Salida) sobre el valor nocional
            fee = (risk['notional_value_usdt'] * 0.0004 * 2)
            pnl_usd -= fee

            self.balance += pnl_usd
            self.equity_curve.append(self.balance)
            
            self.trades.append({
                "timestamp": row['timestamp'],
                "side": side,
                "result": result,
                "pnl": pnl_usd,
                "prob": ai_prob
            })

    def _generate_report(self):
        if not self.trades:
            logger.warning("🏁 Backtest finalizado: No se ejecutaron trades. Revisa tus filtros.")
            return

        tdf = pd.DataFrame(self.trades)
        wins = len(tdf[tdf['pnl'] > 0])
        losses = len(tdf[tdf['pnl'] <= 0])
        total = len(tdf)
        
        winrate = (wins / total) * 100
        gross_profit = tdf[tdf['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(tdf[tdf['pnl'] <= 0]['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else 10.0
        
        # Drawdown
        eq_series = pd.Series(self.equity_curve)
        drawdown = (eq_series.cummax() - eq_series) / eq_series.cummax()
        max_dd = drawdown.max() * 100

        print("\n" + "═"*45)
        print(" 📊 INFORME DE RENDIMIENTO ESTRATEGIA HÍBRIDA")
        print(" ═"*45)
        print(f" 💰 Balance Inicial:   {self.initial_balance} USDT")
        print(f" 💵 Balance Final:     {self.balance:.2f} USDT")
        print(f" 📈 Retorno Total:     {((self.balance/self.initial_balance)-1)*100:.2f}%")
        print(f" ⚖️  Profit Factor:     {profit_factor:.2f}")
        print(f" 🎯 Winrate:           {winrate:.2f}% ({wins}W / {losses}L)")
        print(f" 📉 Max Drawdown:      {max_dd:.2f}%")
        print(f" 📂 Total Operaciones: {total}")
        print(" ═"*45 + "\n")

if __name__ == "__main__":
    tester = HighSpeedBacktester()
    tester.run()