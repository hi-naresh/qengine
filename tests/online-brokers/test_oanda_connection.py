"""
OANDA Broker Connection Tests

Tests real connectivity to the OANDA API using credentials from algo-bot/.env.
These tests hit the live OANDA practice API - they require valid credentials
and network access.

Run with: pytest tests/test_oanda_connection.py -v
"""
import os
import pytest
import requests
from dotenv import load_dotenv

# Load credentials from algo-bot .env
ENV_PATH = os.path.join(os.path.dirname(__file__), '../..', '..', 'algo-bot', '.env')
load_dotenv(ENV_PATH)

OANDA_API_KEY = os.environ.get('OANDA_API_KEY', '')
OANDA_ACCOUNT_ID = os.environ.get('OANDA_ACCOUNT_ID', '')

# Use practice API since account ID format (101-004-*) indicates practice account
BASE_URL = 'https://api-fxpractice.oanda.com/v3'

skip_no_credentials = pytest.mark.skipif(
    not OANDA_API_KEY or not OANDA_ACCOUNT_ID,
    reason='OANDA_API_KEY or OANDA_ACCOUNT_ID not set in .env'
)


def _headers():
    return {
        'Authorization': f'Bearer {OANDA_API_KEY}',
        'Content-Type': 'application/json',
    }


# ── Authentication & Account ──

@skip_no_credentials
def test_oanda_api_key_is_loaded():
    """Verify credentials are loaded from .env."""
    assert len(OANDA_API_KEY) > 10, 'API key looks too short'
    assert '-' in OANDA_ACCOUNT_ID, 'Account ID should contain dashes (e.g. 101-004-...)'


@skip_no_credentials
def test_oanda_authentication():
    """Test that the API key authenticates successfully."""
    resp = requests.get(f'{BASE_URL}/accounts', headers=_headers(), timeout=15)
    assert resp.status_code == 200, f'Auth failed: {resp.status_code} {resp.text}'
    data = resp.json()
    assert 'accounts' in data
    assert len(data['accounts']) > 0


@skip_no_credentials
def test_oanda_account_id_valid():
    """Verify our account ID exists in the account list."""
    resp = requests.get(f'{BASE_URL}/accounts', headers=_headers(), timeout=15)
    assert resp.status_code == 200
    account_ids = [a['id'] for a in resp.json()['accounts']]
    assert OANDA_ACCOUNT_ID in account_ids, (
        f'Account {OANDA_ACCOUNT_ID} not found. Available: {account_ids}'
    )


@skip_no_credentials
def test_oanda_account_summary():
    """Fetch account summary and verify key fields."""
    resp = requests.get(
        f'{BASE_URL}/accounts/{OANDA_ACCOUNT_ID}/summary',
        headers=_headers(), timeout=15,
    )
    assert resp.status_code == 200, f'Failed: {resp.status_code} {resp.text}'
    acct = resp.json().get('account', {})
    assert 'balance' in acct
    assert 'currency' in acct
    assert 'NAV' in acct
    assert 'marginUsed' in acct
    assert float(acct['balance']) >= 0
    print(f"  Balance: {acct['balance']} {acct['currency']}")
    print(f"  NAV: {acct['NAV']}")
    print(f"  Open trades: {acct.get('openTradeCount', 0)}")


# ── Instruments ──

@skip_no_credentials
def test_oanda_fetch_instruments():
    """Fetch tradeable instruments from the account."""
    resp = requests.get(
        f'{BASE_URL}/accounts/{OANDA_ACCOUNT_ID}/instruments',
        headers=_headers(), timeout=15,
    )
    assert resp.status_code == 200
    instruments = resp.json().get('instruments', [])
    assert len(instruments) > 0, 'No instruments returned'

    names = [i['name'] for i in instruments]
    assert 'EUR_USD' in names, f'EUR_USD not in instruments'
    assert 'GBP_USD' in names, f'GBP_USD not in instruments'
    print(f"  Total instruments: {len(instruments)}")


@skip_no_credentials
def test_oanda_instrument_details():
    """Verify instrument metadata contains required fields."""
    resp = requests.get(
        f'{BASE_URL}/accounts/{OANDA_ACCOUNT_ID}/instruments',
        headers=_headers(),
        params={'instruments': 'EUR_USD'},
        timeout=15,
    )
    assert resp.status_code == 200
    instruments = resp.json().get('instruments', [])
    assert len(instruments) == 1
    eur_usd = instruments[0]
    assert eur_usd['name'] == 'EUR_USD'
    assert 'displayPrecision' in eur_usd
    assert 'minimumTradeSize' in eur_usd
    assert eur_usd['type'] == 'CURRENCY'
    print(f"  EUR_USD precision: {eur_usd['displayPrecision']}")
    print(f"  EUR_USD min trade size: {eur_usd['minimumTradeSize']}")


# ── Pricing ──

@skip_no_credentials
def test_oanda_get_pricing():
    """Fetch current prices for a few instruments."""
    resp = requests.get(
        f'{BASE_URL}/accounts/{OANDA_ACCOUNT_ID}/pricing',
        headers=_headers(),
        params={'instruments': 'EUR_USD,GBP_USD,USD_JPY'},
        timeout=15,
    )
    assert resp.status_code == 200
    prices = resp.json().get('prices', [])
    assert len(prices) >= 1, 'No prices returned'

    for p in prices:
        assert 'instrument' in p
        assert 'bids' in p or 'asks' in p
        if p.get('bids') and p.get('asks'):
            bid = float(p['bids'][0]['price'])
            ask = float(p['asks'][0]['price'])
            assert ask >= bid, f"Ask {ask} < Bid {bid} for {p['instrument']}"
            print(f"  {p['instrument']}: bid={bid}, ask={ask}, spread={ask - bid:.5f}")


# ── Historical Candles ──

@skip_no_credentials
def test_oanda_fetch_candles():
    """Fetch recent historical candles for EUR_USD."""
    resp = requests.get(
        f'{BASE_URL}/instruments/EUR_USD/candles',
        headers=_headers(),
        params={
            'granularity': 'H1',
            'count': 10,
            'price': 'M',
        },
        timeout=15,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 'candles' in data
    candles = data['candles']
    assert len(candles) > 0, 'No candles returned'

    for c in candles:
        assert 'time' in c
        assert 'mid' in c
        mid = c['mid']
        assert all(k in mid for k in ('o', 'h', 'l', 'c'))
        assert float(mid['h']) >= float(mid['l'])

    print(f"  Fetched {len(candles)} H1 candles")
    last = candles[-1]
    print(f"  Latest: O={last['mid']['o']} H={last['mid']['h']} L={last['mid']['l']} C={last['mid']['c']}")


@skip_no_credentials
def test_oanda_fetch_candles_multiple_granularities():
    """Verify candle fetching works for different timeframes."""
    for granularity in ['M1', 'M5', 'M15', 'H1', 'H4', 'D']:
        resp = requests.get(
            f'{BASE_URL}/instruments/EUR_USD/candles',
            headers=_headers(),
            params={'granularity': granularity, 'count': 5, 'price': 'M'},
            timeout=15,
        )
        assert resp.status_code == 200, f'Failed for {granularity}: {resp.status_code}'
        candles = resp.json().get('candles', [])
        assert len(candles) > 0, f'No candles for granularity {granularity}'


# ── Orders & Positions (read-only) ──

@skip_no_credentials
def test_oanda_pending_orders():
    """Fetch pending orders (should succeed even if empty)."""
    resp = requests.get(
        f'{BASE_URL}/accounts/{OANDA_ACCOUNT_ID}/pendingOrders',
        headers=_headers(), timeout=15,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 'orders' in data
    print(f"  Pending orders: {len(data['orders'])}")


@skip_no_credentials
def test_oanda_open_positions():
    """Fetch open positions (should succeed even if empty)."""
    resp = requests.get(
        f'{BASE_URL}/accounts/{OANDA_ACCOUNT_ID}/openPositions',
        headers=_headers(), timeout=15,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 'positions' in data
    print(f"  Open positions: {len(data['positions'])}")


@skip_no_credentials
def test_oanda_trade_history():
    """Fetch recent trade history."""
    resp = requests.get(
        f'{BASE_URL}/accounts/{OANDA_ACCOUNT_ID}/trades',
        headers=_headers(),
        params={'state': 'ALL', 'count': 5},
        timeout=15,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 'trades' in data
    print(f"  Recent trades: {len(data['trades'])}")


# ── Driver Integration ──

@skip_no_credentials
def test_oanda_driver_connection():
    """Test OandaMain driver loads credentials and can fetch candles."""
    os.environ['OANDA_API_KEY'] = OANDA_API_KEY
    os.environ['OANDA_ACCOUNT_ID'] = OANDA_ACCOUNT_ID

    from qengine.modes.import_candles_mode.drivers.OANDA.OandaMain import OandaMain
    driver = OandaMain(name='OANDA', practice=True)

    assert driver.api_key == OANDA_API_KEY
    assert driver.account_id == OANDA_ACCOUNT_ID
    assert 'practice' in driver.base_url


@skip_no_credentials
def test_oanda_driver_get_available_symbols():
    """Test that the driver can fetch available symbols."""
    os.environ['OANDA_API_KEY'] = OANDA_API_KEY
    os.environ['OANDA_ACCOUNT_ID'] = OANDA_ACCOUNT_ID

    from qengine.modes.import_candles_mode.drivers.OANDA.OandaMain import OandaMain
    driver = OandaMain(name='OANDA', practice=True)

    symbols = driver.get_available_symbols()
    assert len(symbols) > 0
    assert 'EUR-USD' in symbols
    print(f"  Available symbols: {len(symbols)}")


@skip_no_credentials
def test_oanda_account_summary_fields():
    """Test account summary returns all expected fields with correct types."""
    resp = requests.get(
        f'{BASE_URL}/accounts/{OANDA_ACCOUNT_ID}/summary',
        headers=_headers(), timeout=15,
    )
    assert resp.status_code == 200
    acct = resp.json().get('account', {})

    required_fields = ['balance', 'unrealizedPL', 'marginUsed', 'marginAvailable', 'NAV', 'openTradeCount', 'currency']
    for field in required_fields:
        assert field in acct, f'Missing field: {field}'

    assert float(acct['balance']) >= 0
    assert float(acct['NAV']) >= 0
    assert acct['currency'] in ('USD', 'GBP', 'EUR', 'JPY', 'AUD', 'CAD', 'CHF')
    print(f"  Account: {acct['currency']} balance={acct['balance']}, NAV={acct['NAV']}")


# ── Error Handling ──

def test_oanda_invalid_api_key():
    """Verify OANDA rejects an invalid API key."""
    resp = requests.get(
        f'{BASE_URL}/accounts',
        headers={'Authorization': 'Bearer INVALID_KEY_12345', 'Content-Type': 'application/json'},
        timeout=15,
    )
    assert resp.status_code in (401, 403), f'Expected 401/403, got {resp.status_code}'


def test_oanda_api_reachable():
    """Basic connectivity check - OANDA API should respond."""
    resp = requests.get(f'{BASE_URL}/accounts', timeout=15)
    # Without auth header, should get 401, not a connection error
    assert resp.status_code in (400, 401, 403)
