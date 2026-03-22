from dataclasses import dataclass, field
from typing import Dict, List, Optional

from qengine.enums import asset_classes


@dataclass
class Instrument:
    symbol: str
    asset_class: str
    pip_size: float
    contract_size: float
    min_lot: float
    lot_step: float
    base_currency: str
    quote_currency: str
    margin_rate: float
    trading_hours: str
    swap_long: float = 0.0
    swap_short: float = 0.0


class InstrumentRegistry:
    def __init__(self):
        self._instruments: Dict[str, Instrument] = {}
        self._load_defaults()

    def register(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument

    def get(self, symbol: str) -> Optional[Instrument]:
        return self._instruments.get(symbol)

    def get_asset_class(self, symbol: str) -> str:
        inst = self._instruments.get(symbol)
        if inst:
            return inst.asset_class
        return self._infer_asset_class(symbol)

    def get_pip_size(self, symbol: str) -> float:
        inst = self._instruments.get(symbol)
        if inst:
            return inst.pip_size
        return self._infer_pip_size(symbol)

    def get_contract_size(self, symbol: str) -> float:
        inst = self._instruments.get(symbol)
        if inst:
            return inst.contract_size
        return 100_000.0

    def list_by_asset_class(self, asset_class: str) -> List[str]:
        return [s for s, i in self._instruments.items() if i.asset_class == asset_class]

    def _infer_asset_class(self, symbol: str) -> str:
        base = symbol.split('-')[0] if '-' in symbol else symbol
        if base in FOREX_BASES:
            return asset_classes.FOREX
        if base in COMMODITY_BASES:
            return asset_classes.COMMODITY
        if base in INDEX_BASES:
            return asset_classes.INDEX
        return asset_classes.FOREX

    def _infer_pip_size(self, symbol: str) -> float:
        quote = symbol.split('-')[1] if '-' in symbol else 'USD'
        if quote in ('JPY', 'HUF'):
            return 0.01
        return 0.0001

    def _load_defaults(self) -> None:
        for symbol, info in DEFAULT_INSTRUMENTS.items():
            parts = symbol.split('-')
            self.register(Instrument(
                symbol=symbol,
                asset_class=info['asset_class'],
                pip_size=info['pip_size'],
                contract_size=info['contract_size'],
                min_lot=info.get('min_lot', 0.01),
                lot_step=info.get('lot_step', 0.01),
                base_currency=parts[0],
                quote_currency=parts[1],
                margin_rate=info.get('margin_rate', 0.0333),
                trading_hours=info.get('trading_hours', 'forex'),
                swap_long=info.get('swap_long', 0.0),
                swap_short=info.get('swap_short', 0.0),
            ))


FOREX_BASES = {
    'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY',
    'SEK', 'NOK', 'DKK', 'SGD', 'HKD', 'TRY', 'ZAR', 'MXN',
    'PLN', 'HUF', 'CZK',
}

COMMODITY_BASES = {
    'XAU', 'XAG', 'XPT', 'XPD',
    'BCO', 'WTI', 'NATGAS', 'WTICO',
    'CORN', 'WHEAT', 'SOYBN', 'SUGAR', 'COTTON',
    'COPPER', 'XCU',
}

INDEX_BASES = {
    'US30', 'SPX500', 'NAS100', 'US2000',
    'UK100', 'DE30', 'FR40', 'EU50', 'JP225', 'AU200',
    'HK50', 'CN50',
}

DEFAULT_INSTRUMENTS = {
    # Major forex pairs
    'EUR-USD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'GBP-USD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'USD-JPY': {'asset_class': 'forex', 'pip_size': 0.01, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'USD-CHF': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'AUD-USD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'NZD-USD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'USD-CAD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    # Cross pairs
    'EUR-GBP': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'EUR-JPY': {'asset_class': 'forex', 'pip_size': 0.01, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'GBP-JPY': {'asset_class': 'forex', 'pip_size': 0.01, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'EUR-CHF': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'AUD-JPY': {'asset_class': 'forex', 'pip_size': 0.01, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'NZD-JPY': {'asset_class': 'forex', 'pip_size': 0.01, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'CAD-JPY': {'asset_class': 'forex', 'pip_size': 0.01, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'CHF-JPY': {'asset_class': 'forex', 'pip_size': 0.01, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'EUR-AUD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'GBP-AUD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'EUR-CAD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'GBP-CAD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'GBP-CHF': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'AUD-CAD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'AUD-CHF': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'AUD-NZD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'NZD-CAD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    'NZD-CHF': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.0333, 'trading_hours': 'forex'},
    # Exotic pairs
    'USD-TRY': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    'USD-ZAR': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    'USD-MXN': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    'USD-SEK': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    'USD-NOK': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    'USD-SGD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    'USD-HKD': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    'EUR-TRY': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    'EUR-NOK': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    'EUR-SEK': {'asset_class': 'forex', 'pip_size': 0.0001, 'contract_size': 100_000, 'margin_rate': 0.05, 'trading_hours': 'forex'},
    # Commodities
    'XAU-USD': {'asset_class': 'commodity', 'pip_size': 0.01, 'contract_size': 100, 'margin_rate': 0.05, 'trading_hours': 'commodity_metals'},
    'XAG-USD': {'asset_class': 'commodity', 'pip_size': 0.001, 'contract_size': 5000, 'margin_rate': 0.10, 'trading_hours': 'commodity_metals'},
    'XPT-USD': {'asset_class': 'commodity', 'pip_size': 0.01, 'contract_size': 1, 'margin_rate': 0.10, 'trading_hours': 'commodity_metals'},
    'XPD-USD': {'asset_class': 'commodity', 'pip_size': 0.01, 'contract_size': 1, 'margin_rate': 0.10, 'trading_hours': 'commodity_metals'},
    'BCO-USD': {'asset_class': 'commodity', 'pip_size': 0.01, 'contract_size': 1000, 'margin_rate': 0.10, 'trading_hours': 'commodity_energy'},
    'WTI-USD': {'asset_class': 'commodity', 'pip_size': 0.01, 'contract_size': 1000, 'margin_rate': 0.10, 'trading_hours': 'commodity_energy'},
    'NATGAS-USD': {'asset_class': 'commodity', 'pip_size': 0.001, 'contract_size': 10000, 'margin_rate': 0.10, 'trading_hours': 'commodity_energy'},
    'COPPER-USD': {'asset_class': 'commodity', 'pip_size': 0.0001, 'contract_size': 25000, 'margin_rate': 0.10, 'trading_hours': 'commodity_metals'},
    # Indices
    'US30-USD': {'asset_class': 'index', 'pip_size': 1.0, 'contract_size': 1, 'margin_rate': 0.05, 'trading_hours': 'index_us'},
    'SPX500-USD': {'asset_class': 'index', 'pip_size': 0.1, 'contract_size': 1, 'margin_rate': 0.05, 'trading_hours': 'index_us'},
    'NAS100-USD': {'asset_class': 'index', 'pip_size': 0.1, 'contract_size': 1, 'margin_rate': 0.05, 'trading_hours': 'index_us'},
    'UK100-GBP': {'asset_class': 'index', 'pip_size': 0.1, 'contract_size': 1, 'margin_rate': 0.05, 'trading_hours': 'index_eu'},
    'DE30-EUR': {'asset_class': 'index', 'pip_size': 0.1, 'contract_size': 1, 'margin_rate': 0.05, 'trading_hours': 'index_eu'},
    'JP225-JPY': {'asset_class': 'index', 'pip_size': 1.0, 'contract_size': 1, 'margin_rate': 0.05, 'trading_hours': 'index_asia'},
}


instrument_registry = InstrumentRegistry()
