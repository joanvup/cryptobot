# core/cmc_client.py
import requests
import logging
from config.settings import settings
from exchange.binance_client import BinanceFuturesClient

logger = logging.getLogger(__name__)

class CMCClient:
    def __init__(self):
        self.api_key = settings.CMC_API_KEY
        self.url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
        self.binance_client = BinanceFuturesClient()

    def get_dynamic_whitelist(self, top_n: int = 10) -> list:
        if not self.api_key:
            logger.error("❌ CMC_API_KEY no configurada. Usando Whitelist estática del .env")
            return settings.WHITELIST_LIST

        headers = {
            'Accepts': 'application/json',
            'X-CMC_PRO_API_KEY': self.api_key,
        }
        # Pedimos el top 50 para tener margen después de filtrar las basuras
        params = {'start': '1', 'limit': '50', 'convert': 'USD'}

        try:
            logger.info("🌐 Conectando con CoinMarketCap para obtener Top Global...")
            response = requests.get(self.url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # 1. Filtros de purificación (Stablecoins y Wrapped tokens)
            invalid_bases =['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'WBTC', 'STETH', 'WETH']
            
            # 2. Cruce de datos con Binance Futures
            # Le preguntamos a Binance cuáles monedas existen realmente en su mercado de futuros hoy
            exchange_info = self.binance_client.client.futures_exchange_info()
            valid_binance_symbols = [s['symbol'] for s in exchange_info['symbols'] if s['status'] == 'TRADING']

            dynamic_list = []
            for coin in data.get('data', []):
                sym = coin['symbol']
                
                # Si es stablecoin, saltar
                if sym in invalid_bases:
                    continue
                
                # Formatear al estándar de Binance (ej: BTC -> BTCUSDT)
                binance_symbol = f"{sym}USDT"
                
                # Validar que Binance la permita operar en Futuros
                if binance_symbol in valid_binance_symbols:
                    dynamic_list.append(binance_symbol)
                    
                # Detenerse cuando tengamos exactamente las N solicitadas
                if len(dynamic_list) >= top_n:
                    break

            logger.info(f"💎 Dynamic Blue-Chip Whitelist Generada: {dynamic_list}")
            return dynamic_list

        except Exception as e:
            logger.error(f"❌ Error conectando a CoinMarketCap: {e}. Usando fallback local.")
            return settings.WHITELIST_LIST