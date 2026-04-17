# core/scanner.py
from exchange.binance_client import BinanceFuturesClient
from core.cmc_client import CMCClient
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class MarketScanner:
    def __init__(self):
        self.exchange = BinanceFuturesClient()
        self.cmc = CMCClient()
        self._cached_whitelist = None # RAM Cache para la API de CMC

    def get_symbols_to_trade(self):
        """Punto de entrada principal para decidir qué activos analizar."""
        tickers = self.exchange.get_24h_tickers()
        if not tickers: 
            return[]

        if settings.USE_SCANNER:
            logger.info(f"🔍 [MODO SCANNER] Buscando el Top {settings.SCAN_TOP_N} por volatilidad extrema...")
            return self._scan_by_volatility(tickers)
        else:
            # LOG DINÁMICO: Nos dice qué sistema está usando realmente
            if settings.USE_DYNAMIC_CMC_WHITELIST:
                logger.info("🌐 [MODO CMC DYNAMIC] Analizando el Top Global de CoinMarketCap...")
            else:
                logger.info(f"📋[MODO WHITELIST ESTÁTICA] Filtrando activos: {settings.WHITELIST}")
            
            return self._filter_by_whitelist(tickers)

    def _scan_by_volatility(self, tickers):
        """Busca monedas con explosión de volumen y movimiento de precio."""
        valid_pairs =[]
        for t in tickers:
            symbol = t['symbol']
            if symbol.endswith('USDT') and '_' not in symbol:
                volume = float(t['quoteVolume'])
                if volume >= settings.MIN_VOLUME_24H:
                    valid_pairs.append({
                        'symbol': symbol,
                        'abs_change': abs(float(t['priceChangePercent'])),
                        'last_price': float(t['lastPrice']),
                        'volume': volume
                    })

        # Ordenar por el movimiento más fuerte (volatilidad)
        sorted_pairs = sorted(valid_pairs, key=lambda x: x['abs_change'], reverse=True)
        return sorted_pairs[:settings.SCAN_TOP_N]

    def _filter_by_whitelist(self, tickers):
        """Filtra los tickers de Binance usando CMC o la lista estática local."""
        
        # 1. Decidir de dónde sacar la lista objetivo
        if settings.USE_DYNAMIC_CMC_WHITELIST:
            if not self._cached_whitelist:
                # Se conecta a CoinMarketCap 1 sola vez al iniciar el bot
                self._cached_whitelist = self.cmc.get_dynamic_whitelist(top_n=settings.SCAN_TOP_N)
            target_list = self._cached_whitelist
        else:
            target_list = settings.WHITELIST_LIST

        # 2. Cruzar la lista con los datos en vivo de Binance
        selected_pairs =[]
        for t in tickers:
            symbol = t['symbol']
            if symbol in target_list:
                selected_pairs.append({
                    'symbol': symbol,
                    'abs_change': abs(float(t['priceChangePercent'])),
                    'last_price': float(t['lastPrice']),
                    'volume': float(t['quoteVolume'])
                })
                
        return selected_pairs