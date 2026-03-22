import time
import requests
import arrow
from typing import Union, List, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import qengine.helpers as jh
from qengine.modes.import_candles_mode.drivers.interface import CandleExchange
from .oanda_utils import symbol_to_instrument, timeframe_to_granularity, get_api_url, GRANULARITY_SECONDS, CANDLES_PER_MINUTE


class OandaMain(CandleExchange):
    """
    OANDA v20 REST API historical candle driver.
    API: GET /v3/instruments/{instrument}/candles
    Rate limit: ~30 req/sec
    Max candles per request: 5000
    Historical depth: Several years (since ~2005 for majors)
    """

    def __init__(
            self,
            name: str,
            practice: bool = False,
            backup_exchange_class=None,
    ) -> None:
        super().__init__(
            name=name,
            count=5000,
            rate_limit_per_second=20,
            backup_exchange_class=backup_exchange_class,
        )

        self.practice = practice
        self.base_url = get_api_url(practice)
        self.api_key = self._load_api_key()
        self.account_id = self._load_account_id()
        self._endpoint_verified = False

        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _load_api_key(self) -> str:
        import os
        key = os.environ.get('OANDA_API_KEY', '')
        if not key:
            from qengine.services.env import ENV_VALUES
            key = ENV_VALUES.get('OANDA_API_KEY', '')
        return key

    def _load_account_id(self) -> str:
        import os
        aid = os.environ.get('OANDA_ACCOUNT_ID', '')
        if not aid:
            from qengine.services.env import ENV_VALUES
            aid = ENV_VALUES.get('OANDA_ACCOUNT_ID', '')
        return aid

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def _verify_endpoint(self) -> None:
        """Auto-detect correct endpoint (practice vs live) on first request."""
        if self._endpoint_verified:
            return
        try:
            r = self.session.get(
                f'{self.base_url}/v3/accounts/{self.account_id}',
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                self._endpoint_verified = True
                return
        except Exception:
            pass

        # Try the other endpoint
        alt_url = get_api_url(not self.practice)
        try:
            r = self.session.get(
                f'{alt_url}/v3/accounts/{self.account_id}',
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                self.base_url = alt_url
                self.practice = not self.practice
                self._endpoint_verified = True
                return
        except Exception:
            pass

        # Neither worked — proceed with original, will fail with clear error
        self._endpoint_verified = True

    def _make_request(self, url: str, params: dict = None) -> requests.Response:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, headers=self._headers(), params=params, timeout=30)
                return response
            except (requests.exceptions.ConnectionError, OSError) as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(2 * (attempt + 1))
        raise Exception(f'Failed to make request after {max_retries} attempts')

    def _validate_credentials(self):
        if not self.api_key:
            raise ConnectionError(
                'OANDA API key is not configured. '
                'Set OANDA_API_KEY in your .env file or environment variables.'
            )
        if not self.account_id:
            raise ConnectionError(
                'OANDA Account ID is not configured. '
                'Set OANDA_ACCOUNT_ID in your .env file or environment variables.'
            )

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[List[Dict[str, Any]], None]:
        self._validate_credentials()
        self._verify_endpoint()
        instrument = symbol_to_instrument(symbol)

        # Check if we should fetch at a finer granularity and aggregate
        fetch_granularity = getattr(self, '_import_granularity', None) or timeframe
        oanda_granularity = timeframe_to_granularity(fetch_granularity)
        is_sub_minute = fetch_granularity in CANDLES_PER_MINUTE and CANDLES_PER_MINUTE.get(fetch_granularity, 1) > 1

        # OANDA uses RFC3339 timestamps or unix seconds
        from_time = arrow.get(start_timestamp / 1000).isoformat()

        params = {
            'from': from_time,
            'granularity': oanda_granularity,
            'count': self.count,
            'price': 'M',  # midpoint candles
        }

        response = self._make_request(
            f'{self.base_url}/v3/instruments/{instrument}/candles',
            params=params,
        )

        self.validate_response(response)

        data = response.json()
        raw_candles = []
        for c in data.get('candles', []):
            if c.get('complete', True):
                raw_candles.append({
                    'timestamp': arrow.get(c['time']).int_timestamp * 1000,
                    'open': float(c['mid']['o']),
                    'close': float(c['mid']['c']),
                    'high': float(c['mid']['h']),
                    'low': float(c['mid']['l']),
                    'volume': int(c.get('volume', 0)),
                })

        if not raw_candles:
            return []

        # If sub-minute, aggregate to 1m candles
        if is_sub_minute:
            candles = self._aggregate_to_1m(raw_candles, symbol)
        else:
            candles = [{
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': c['timestamp'],
                'open': c['open'],
                'close': c['close'],
                'high': c['high'],
                'low': c['low'],
                'volume': c['volume'],
            } for c in raw_candles]

        return candles

    def _aggregate_to_1m(self, raw_candles: list, symbol: str) -> list:
        """Aggregate sub-minute candles into 1-minute candles."""
        buckets = {}
        for c in raw_candles:
            # Floor timestamp to the start of the minute
            minute_ts = (c['timestamp'] // 60000) * 60000
            if minute_ts not in buckets:
                buckets[minute_ts] = {
                    'open': c['open'],
                    'high': c['high'],
                    'low': c['low'],
                    'close': c['close'],
                    'volume': c['volume'],
                }
            else:
                b = buckets[minute_ts]
                b['high'] = max(b['high'], c['high'])
                b['low'] = min(b['low'], c['low'])
                b['close'] = c['close']
                b['volume'] += c['volume']

        candles = []
        for ts in sorted(buckets.keys()):
            b = buckets[ts]
            candles.append({
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': '1m',
                'timestamp': ts,
                'open': b['open'],
                'close': b['close'],
                'high': b['high'],
                'low': b['low'],
                'volume': b['volume'],
            })
        return candles

    def get_starting_time(self, symbol: str) -> int:
        """Fetch earliest available candle for the instrument."""
        self._validate_credentials()
        self._verify_endpoint()
        instrument = symbol_to_instrument(symbol)

        params = {
            'granularity': 'W',
            'count': 5000,
            'price': 'M',
        }

        response = self._make_request(
            f'{self.base_url}/v3/instruments/{instrument}/candles',
            params=params,
        )

        self.validate_response(response)

        data = response.json()
        candles_data = data.get('candles', [])
        if len(candles_data) > 1:
            return arrow.get(candles_data[1]['time']).int_timestamp * 1000

        # Fallback: most OANDA pairs have data since 2005
        return arrow.get('2005-01-03').int_timestamp * 1000

    def get_available_symbols(self) -> list:
        """Fetch all tradeable instruments from OANDA account."""
        if not self.account_id:
            return []

        self._verify_endpoint()
        response = self._make_request(
            f'{self.base_url}/v3/accounts/{self.account_id}/instruments',
        )

        self.validate_response(response)

        data = response.json()
        instruments = data.get('instruments', [])
        return [inst['name'].replace('_', '-') for inst in instruments]

    def __del__(self):
        if hasattr(self, 'session'):
            self.session.close()
