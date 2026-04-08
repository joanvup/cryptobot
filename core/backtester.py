# core/backtester.py
import pandas as pd
import logging
from strategy.core import HybridStrategy
from execution.risk_manager import RiskManager
from config.settings import settings

logger = logging.getLogger(__name__)

class Backtester:
    def __init__(self, csv_path: str):
        self.df = pd.read_csv(csv_path)
        self.strategy = HybridStrategy()
        self.rm = RiskManager()
        self.balance = 1000.0 # Balance inicial simulado (USDT)
        self.equity_curve = [self.balance]
        self.trades_history = []

    def run(self):
        logger.info(f"--- Iniciando Backtest sobre {len(self.df)} velas ---")
        
        # Necesitamos al menos 50 velas para los indicadores
        for i in range(settings.EMA_SLOW, len(self.df)):
            window = self.df.iloc[:i+1] # Simula el paso del tiempo
            analysis = self.strategy.analyze(window)
            
            if analysis['signal'] != 'NEUTRAL':
                self.simulate_trade(analysis, i)

        self.print_results()
        return self.equity_curve

    def simulate_trade(self, analysis, current_index):
        side = analysis['signal']
        entry_price = analysis['close_price']
        atr = analysis['atr']
        
        # 1. Calcular parámetros como si fuera real
        risk = self.rm.calculate_trade_parameters(self.balance, entry_price, atr, side)
        if not risk: return

        # 2. Buscar salida en las siguientes velas
        future_data = self.df.iloc[current_index+1 : current_index + 20] # Máximo 20 velas de espera
        
        for _, row in future_data.iterrows():
            # ¿Toca SL?
            if (side == 'LONG' and row['low'] <= risk['stop_loss']) or \
               (side == 'SHORT' and row['high'] >= risk['stop_loss']):
                pnl = - (self.balance * (settings.RISK_PER_TRADE_PERCENT / 100))
                self.close_sim_trade(pnl, "STOP_LOSS")
                break
            
            # ¿Toca TP?
            if (side == 'LONG' and row['high'] >= risk['take_profit']) or \
               (side == 'SHORT' and row['low'] <= risk['take_profit']):
                # PNL basado en el ratio riesgo:beneficio (ATR_TP / ATR_SL)
                ratio = settings.ATR_TP_MULTIPLIER / settings.ATR_SL_MULTIPLIER
                pnl = (self.balance * (settings.RISK_PER_TRADE_PERCENT / 100)) * ratio
                self.close_sim_trade(pnl, "TAKE_PROFIT")
                break

    def close_sim_trade(self, pnl, reason):
        self.balance += pnl
        self.equity_curve.append(self.balance)
        self.trades_history.append(pnl)

    def print_results(self):
        win_trades = [t for t in self.trades_history if t > 0]
        loss_trades = [t for t in self.trades_history if t <= 0]
        
        winrate = (len(win_trades) / len(self.trades_history) * 100) if self.trades_history else 0
        profit_factor = abs(sum(win_trades) / sum(loss_trades)) if loss_trades else 100
        
        print("\n" + "="*30)
        print(f"RESULTADOS DEL BACKTEST")
        print(f"Balance Final: {self.balance:.2f} USDT")
        print(f"Trades Totales: {len(self.trades_history)}")
        print(f"Winrate: {winrate:.2f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Max Equity: {max(self.equity_curve):.2f}")
        print("="*30 + "\n")