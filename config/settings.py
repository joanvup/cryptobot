# config/settings.py
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    RUN_MODE: str = "TESTNET"
    DRY_RUN_BALANCE: float = 1000.0

    BINANCE_TESTNET_API_KEY: str = ""
    BINANCE_TESTNET_API_SECRET: str = ""
    BINANCE_MAINNET_API_KEY: str = ""
    BINANCE_MAINNET_API_SECRET: str = ""
    
    DATABASE_URL: str

    DEFAULT_TIMEFRAME: str = "15m"
    DEFAULT_LEVERAGE: int = 5
    SCAN_TOP_N: int = 10
    MIN_VOLUME_24H: float = 50000000.0
    AUTO_TRADING: bool = True
    CYCLE_INTERVAL_SECONDS: int = 300
    RADAR_INTERVAL_SECONDS: int = 30
    MONITOR_INTERVAL_SECONDS: int = 5 

    USE_SCANNER: bool = False
    WHITELIST: str = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,LINKUSDT,LTCUSDT,DOTUSDT"

    RISK_PER_TRADE_PERCENT: float = 1.0
    MAX_OPEN_TRADES: int = 4
    ATR_SL_MULTIPLIER: float = 1.2
    ATR_TP_MULTIPLIER: float = 3.0

    TRAILING_STOP_ENABLED: bool = True
    TS_PHASE1_ACTIVATION_ATR: float = 1.0
    TS_PHASE2_ACTIVATION_ATR: float = 1.5
    TS_PHASE2_DISTANCE_ATR: float = 1.0
    TS_PHASE3_ACTIVATION_ATR: float = 2.0
    TS_PHASE3_DISTANCE_ATR: float = 0.8

    RSI_PERIOD: int = 14
    RSI_OVERBOUGHT: float = 90.0
    RSI_OVERSOLD: float = 10.0
    EMA_FAST: int = 20
    EMA_SLOW: int = 50
    VOL_RELATIVE_THRESHOLD: float = 0.1
    AI_CONFIDENCE_THRESHOLD: float = 0.30
    MODEL_PATH: str = "models/xgboost_model.pkl"
    TRAINING_LIMIT_KLINES: int = 50000

    @property
    def WHITELIST_LIST(self) -> List[str]:
        if not self.WHITELIST: return []
        return[s.strip() for s in self.WHITELIST.split(",") if s.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()