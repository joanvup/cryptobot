# core/scanner.py
from exchange.binance_client import BinanceFuturesClient
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class MarketScanner:
    def __init__(self):
        self.exchange = BinanceFuturesClient()

    def get_symbols_to_trade(self):
        """
        Punto de entrada principal para obtener los símbolos a analizar.
        Alterna entre escaneo dinámico y lista blanca fija.
        """
        tickers = self.exchange.get_24h_tickers()
        if not tickers:
            logger.error("No se pudieron obtener tickers de Binance.")
            return []

        if settings.USE_SCANNER:
            logger.info(f"🔍 [MODO SCANNER] Buscando las {settings.SCAN_TOP_N} con mayor volatilidad.")
            return self._scan_by_volatility(tickers)
        else:
            logger.info(f"📋 [MODO WHITELIST] Filtrando activos configurados: {settings.WHITELIST}")
            return self._filter_by_whitelist(tickers)

    def _scan_by_volatility(self, tickers):
        """Filtra y ordena por volumen y cambio porcentual absoluto."""
        valid_pairs = []
        for t in tickers:
            symbol = t['symbol']
            # Filtro base: Solo USDT-M y evitar contratos con fecha (contienen _)
            if symbol.endswith('USDT') and '_' not in symbol:
                volume = float(t['quoteVolume'])
                # Filtro de liquidez mínima según settings
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
        """Devuelve solo los datos de los símbolos presentes en la Whitelist."""
        whitelist = settings.WHITELIST_LIST
        selected_pairs = []
        
        for t in tickers:
            symbol = t['symbol']
            if symbol in whitelist:
                selected_pairs.append({
                    'symbol': symbol,
                    'abs_change': abs(float(t['priceChangePercent'])),
                    'last_price': float(t['lastPrice']),
                    'volume': float(t['quoteVolume'])
                })
        
        return selected_pairs