# db/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from datetime import datetime
from db.database import Base

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    side = Column(String, nullable=False)
    entry_price = Column(Float, nullable=False)
    position_size = Column(Float, nullable=False)
    entry_time = Column(DateTime, default=datetime.utcnow)
    initial_stop_loss = Column(Float, nullable=False)
    current_stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=True)
    atr_at_entry = Column(Float, nullable=False)
    
    trailing_activated = Column(Boolean, default=False)
    trailing_phase = Column(Integer, default=0) 
    extreme_price = Column(Float, nullable=True) 
    
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    is_open = Column(Boolean, default=True)
    close_reason = Column(String, nullable=True)
    
    run_mode = Column(String(20), default="TESTNET") # NUEVO: Testnet, Mainnet o DryRun

class SystemLog(Base):
    __tablename__ = "system_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String(10), nullable=False)
    module = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)