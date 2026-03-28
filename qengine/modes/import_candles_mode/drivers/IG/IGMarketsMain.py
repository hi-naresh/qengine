import time
import requests
import arrow
from typing import Union, List, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import qengine.helpers as jh
from qengine.modes.import_candles_mode.drivers.interface import CandleExchange
from .ig_utils import symbol_to_epic, timeframe_to_resolution, get_api_url


class IGMarketsMain(CandleExchange):
    """
    IG Markets REST API historical price driver.
    API: GET /prices/{epic}/{resolution}/{startDate}/{endDate}
    Requires: API key + account credentials + CST/X-SECURITY-TOKEN auth
    Rate limit: ~10 req/sec, max 10000 historical data points per week
    """

    def __init__(
            self,
            name: str,
            demo: bool = False,
            backup_exchange_class=None,
    ) -> None:
        super().__init__(
            name=name,
            count=1000,
            rate_limit_per_second=10,
            backup_exchange_class=backup_exchange_class,
        )

        self.demo = demo
        self.base_url = get_api_url(demo)
        self.api_key = self._load_api_key()
        self._cst = None
        self._security_token = None
        self._epic_map = {}

        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _load_api_key(self) -> str:
        import os
        key = os.environ.get('IG_API_KEY', '')
        if not key:
            from qengine.services.env import ENV_VALUES
            key = ENV_VALUES.get('IG_API_KEY', '')
        if not key:
            key = self._load_from_db('api_key')
        return key

    def _load_from_db(self, field: str) -> str:
        """Load broker credential from DB settings (set via UI)."""
        try:
            from qengine.controllers.settings_controller import _get_settings_from_db, ADMIN_SETTINGS_ID
            settings = _get_settings_from_db(ADMIN_SETTINGS_ID)
            brokers = settings.get('brokers', {})
            for broker_id in ('IG Markets', 'IG Markets Demo'):
                conf = brokers.get(broker_id, {})
                if field == 'username':
                    val = conf.get('additional_fields', {}).get('ig_username', '')
                elif field == 'password':
                    val = conf.get('additional_fields', {}).get('ig_password', '') or conf.get('api_secret', '')
                else:
                    val = conf.get(field, '')
                if val:
                    return val
        except Exception:
            pass
        return ''

    def _authenticate(self) -> None:
        """Authenticate with IG Markets to get CST and X-SECURITY-TOKEN."""
        if self._cst and self._security_token:
            return

        import os
        from qengine.services.env import ENV_VALUES
        identifier = os.environ.get('IG_IDENTIFIER', ENV_VALUES.get('IG_IDENTIFIER', ''))
        password = os.environ.get('IG_PASSWORD', ENV_VALUES.get('IG_PASSWORD', ''))
        if not identifier:
            identifier = os.environ.get('IG_USERNAME', ENV_VALUES.get('IG_USERNAME', ''))
        if not identifier:
            identifier = self._load_from_db('username')
        if not password:
            password = self._load_from_db('password')

        response = self.session.post(
            f'{self.base_url}/session',
            headers={
                'X-IG-API-KEY': self.api_key,
                'Content-Type': 'application/json',
                'Accept': 'application/json; charset=UTF-8',
                'VERSION': '2',
            },
            json={
                'identifier': identifier,
                'password': password,
            },
            timeout=30,
        )

        self.validate_response(response)

        self._cst = response.headers.get('CST')
        self._security_token = response.headers.get('X-SECURITY-TOKEN')

    def _headers(self) -> dict:
        self._authenticate()
        return {
            'X-IG-API-KEY': self.api_key,
            'CST': self._cst or '',
            'X-SECURITY-TOKEN': self._security_token or '',
            'Content-Type': 'application/json',
            'Accept': 'application/json; charset=UTF-8',
            'VERSION': '2',
        }

    def _make_request(self, url: str, params: dict = None) -> requests.Response:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, headers=self._headers(), params=params, timeout=30)
                # If unauthorized, re-authenticate
                if response.status_code == 401:
                    self._cst = None
                    self._security_token = None
                    if attempt < max_retries - 1:
                        continue
                return response
            except (requests.exceptions.ConnectionError, OSError) as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(2 * (attempt + 1))
        raise Exception(f'Failed to make request after {max_retries} attempts')

    def _validate_credentials(self):
        if not self.api_key:
            raise ConnectionError(
                'IG Markets API key is not configured. '
                'Set IG_API_KEY in your .env file or environment variables.'
            )

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[List[Dict[str, Any]], None]:
        self._validate_credentials()
        epic = symbol_to_epic(symbol, self._epic_map)
        resolution = timeframe_to_resolution(timeframe)

        start_date = arrow.get(start_timestamp / 1000).format('YYYY-MM-DDTHH:mm:ss')
        # Calculate end based on count and timeframe
        minutes_per_candle = jh.timeframe_to_one_minutes(timeframe)
        end_timestamp = start_timestamp + (self.count - 1) * 60000 * minutes_per_candle
        end_date = arrow.get(end_timestamp / 1000).format('YYYY-MM-DDTHH:mm:ss')

        response = self._make_request(
            f'{self.base_url}/prices/{epic}/{resolution}/{start_date}/{end_date}',
            params={'pageSize': self.count},
        )

        self.validate_response(response)

        data = response.json()
        candles = []
        for price in data.get('prices', []):
            snapshot_time = price.get('snapshotTime', price.get('snapshotTimeUTC', ''))
            try:
                ts = arrow.get(snapshot_time).int_timestamp * 1000
            except Exception:
                continue

            ohlc = price.get('closePrice', {})
            open_price = price.get('openPrice', {})
            high_price = price.get('highPrice', {})
            low_price = price.get('lowPrice', {})

            # IG provides bid/ask; we use mid
            def mid(price_obj):
                bid = price_obj.get('bid', 0) or 0
                ask = price_obj.get('ask', 0) or 0
                if bid and ask:
                    return (float(bid) + float(ask)) / 2
                return float(bid or ask or 0)

            candles.append({
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': ts,
                'open': mid(open_price),
                'close': mid(ohlc),
                'high': mid(high_price),
                'low': mid(low_price),
                'volume': int(price.get('lastTradedVolume', 0)),
            })

        return candles

    def get_starting_time(self, symbol: str) -> int:
        """IG Markets typically has data from ~2010 for most instruments."""
        self._validate_credentials()
        return arrow.get('2010-01-04').int_timestamp * 1000

    def get_available_symbols(self) -> list:
        """Search IG Markets instrument directory for available symbols."""
        response = self._make_request(
            f'{self.base_url}/markets',
            params={'searchTerm': 'FX'},
        )

        if response.status_code != 200:
            return list(self._epic_map.keys())

        data = response.json()
        symbols = []
        for market in data.get('markets', []):
            epic = market.get('epic', '')
            display_name = market.get('instrumentName', '')
            symbols.append(display_name)

        return symbols

    def __del__(self):
        if hasattr(self, 'session'):
            self.session.close()
