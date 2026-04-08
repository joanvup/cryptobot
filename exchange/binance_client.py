# exchange/binance_client.py
import time
import logging
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config.settings import settings

logger = logging.getLogger(__name__)

class BinanceFuturesClient:
    """
    Implementación Singleton que gestiona la conexión según el RUN_MODE.
    Asegura que las firmas criptográficas vayan a la red correcta y sin corrupción.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BinanceFuturesClient, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        logger.info(f"🔌 Inicializando Conexión Singleton en Modo: {settings.RUN_MODE}")
        
        # 1. Asignación Estricta de Credenciales y Entorno
        if settings.RUN_MODE in ["MAINNET", "DRY_RUN"]:
            api_key = settings.BINANCE_MAINNET_API_KEY
            api_secret = settings.BINANCE_MAINNET_API_SECRET
            use_testnet = False
            logger.info("🟢 Conectando a Binance MAINNET (Datos Reales)")
        else:
            api_key = settings.BINANCE_TESTNET_API_KEY
            api_secret = settings.BINANCE_TESTNET_API_SECRET
            use_testnet = True
            logger.info("🧪 Conectando a Binance TESTNET (Dinero Falso)")

        # Validación de seguridad
        if not api_key or not api_secret:
            logger.error(f"❌ FALTAN LLAVES API PARA EL MODO {settings.RUN_MODE}. Verifica tu archivo .env.")
            raise ValueError("API Keys missing")

        # 2. Inicialización del Cliente
        self.client = Client(api_key=api_key, api_secret=api_secret, testnet=use_testnet)
        
        # ¡CORRECCIÓN CRÍTICA! Se eliminó la inyección global de 'recvWindow' 
        # que corrompía la firma criptográfica (Error -1022) en peticiones de Trading.
        
        self.MAX_BINANCE_LIMIT = 1500 
        
        # 3. Sincronización Inicial de Reloj
        self._sync_server_time()

    def _sync_server_time(self):
        """Calcula el offset del reloj local respecto al servidor de Binance FUTURES."""
        try:
            server_time = self.client.futures_time()
            local_time = int(time.time() * 1000)
            
            # BinanceClient usará este offset automáticamente antes de firmar las peticiones
            self.client.timestamp_offset = server_time['serverTime'] - local_time
            logger.info(f"⏰ Reloj sincronizado con Futuros. Offset: {self.client.timestamp_offset}ms")
        except Exception as e:
            logger.error(f"Error sincronizando reloj: {e}")

    def get_usdt_balance(self) -> dict:
        """Devuelve la Billetera Virtual (Dry Run) o la Billetera Real (Mainnet/Testnet)."""
        # --- BILLETERA FANTASMA (DRY RUN) ---
        if settings.RUN_MODE == "DRY_RUN":
            from db.database import SessionLocal
            from db.models import Trade
            db = SessionLocal()
            try:
                closed_trades = db.query(Trade).filter(Trade.is_open == False, Trade.run_mode == "DRY_RUN").all()
                realized_pnl = sum(t.pnl for t in closed_trades if t.pnl)
                current_wallet = settings.DRY_RUN_BALANCE + realized_pnl
                
                open_trades = db.query(Trade).filter(Trade.is_open == True, Trade.run_mode == "DRY_RUN").all()
                margin_used = sum((t.entry_price * t.position_size) / settings.DEFAULT_LEVERAGE for t in open_trades)
                
                return {
                    "wallet_balance": current_wallet,
                    "total_balance": current_wallet,
                    "unrealized_pnl": 0.0,
                    "available": current_wallet - margin_used
                }
            except Exception as e:
                logger.error(f"Error en Billetera Virtual: {e}")
                return {"wallet_balance": settings.DRY_RUN_BALANCE, "total_balance": settings.DRY_RUN_BALANCE, "unrealized_pnl": 0, "available": settings.DRY_RUN_BALANCE}
            finally:
                db.close()

        # --- BALANCE REAL (TESTNET O MAINNET) ---
        try:
            account = self.client.futures_account()
            usdt_asset = next((item for item in account.get('assets', []) if item['asset'] == 'USDT'), {})
            return {
                "wallet_balance": float(usdt_asset.get('walletBalance', 0)),
                "total_balance": float(usdt_asset.get('marginBalance', 0)),
                "unrealized_pnl": float(usdt_asset.get('unrealizedProfit', 0)),
                "available": float(usdt_asset.get('availableBalance', 0))
            }
        except BinanceAPIException as e:
            if e.code in[-1021, -1022]: 
                self._sync_server_time()
            logger.error(f"Error balance: {e}")
            return {"wallet_balance": 0, "total_balance": 0, "unrealized_pnl": 0, "available": 0}

    def get_funding_rate(self, symbol: str) -> float:
        try:
            info = self.client.futures_mark_price(symbol=symbol)
            return float(info.get('lastFundingRate', 0.0))
        except Exception: 
            return 0.0

    def get_24h_tickers(self) -> list:
        try: return self.client.futures_ticker()
        except: return[]

    def get_historical_klines(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        all_klines =[]
        last_timestamp = None
        remaining_limit = limit
        try:
            while remaining_limit > 0:
                current_fetch_limit = min(remaining_limit, self.MAX_BINANCE_LIMIT)
                klines = self.client.futures_klines(symbol=symbol, interval=interval, limit=current_fetch_limit, endTime=last_timestamp)
                if not klines: break
                all_klines = klines + all_klines
                last_timestamp = klines[0][0] - 1
                remaining_limit -= len(klines)
                if remaining_limit > 0: time.sleep(0.1)

            df = pd.DataFrame(all_klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
        except: 
            return pd.DataFrame()