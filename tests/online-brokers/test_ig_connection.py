"""
IG Markets Broker Connection Tests

Tests real connectivity to the IG Markets API using credentials from algo-bot/.env.
These tests hit the IG demo API - they require valid credentials and network access.

Run with: pytest tests/test_ig_connection.py -v
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

# Load credentials from algo-bot .env
ENV_PATH = os.path.join(os.path.dirname(__file__), '../..', '..', 'algo-bot', '.env')
load_dotenv(ENV_PATH)

IG_API_KEY = os.environ.get('IG_API_KEY', '')
IG_USERNAME = os.environ.get('IG_USERNAME', '')
IG_PASSWORD = os.environ.get('IG_PASSWORD', '')

# Use demo API for testing
BASE_URL = 'https://demo-api.ig.com/gateway/deal'

skip_no_credentials = pytest.mark.skipif(
    not IG_API_KEY or not IG_USERNAME or not IG_PASSWORD,
    reason='IG_API_KEY, IG_USERNAME, or IG_PASSWORD not set in .env'
)


@pytest.fixture(scope='module')
def ig_session():
    """Authenticate once and share CST + security token across tests."""
    resp = requests.post(
        f'{BASE_URL}/session',
        headers={
            'X-IG-API-KEY': IG_API_KEY,
            'Content-Type': 'application/json',
            'Version': '2',
        },
        json={
            'identifier': IG_USERNAME,
            'password': IG_PASSWORD,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        pytest.skip(f'IG authentication failed: {resp.status_code} {resp.text}')

    return {
        'cst': resp.headers.get('CST', ''),
        'security_token': resp.headers.get('X-SECURITY-TOKEN', ''),
    }


def _headers(ig_session):
    return {
        'X-IG-API-KEY': IG_API_KEY,
        'CST': ig_session['cst'],
        'X-SECURITY-TOKEN': ig_session['security_token'],
        'Content-Type': 'application/json',
    }


# ── Credentials ──

@skip_no_credentials
def test_ig_credentials_loaded():
    """Verify IG credentials are loaded from .env."""
    assert len(IG_API_KEY) > 10, 'API key looks too short'
    assert len(IG_USERNAME) > 0, 'Username is empty'
    assert len(IG_PASSWORD) > 0, 'Password is empty'


# ── Authentication ──

@skip_no_credentials
def test_ig_authentication():
    """Test that IG credentials authenticate successfully."""
    resp = requests.post(
        f'{BASE_URL}/session',
        headers={
            'X-IG-API-KEY': IG_API_KEY,
            'Content-Type': 'application/json',
            'Version': '2',
        },
        json={
            'identifier': IG_USERNAME,
            'password': IG_PASSWORD,
        },
        timeout=15,
    )
    assert resp.status_code == 200, f'Auth failed: {resp.status_code} {resp.text}'
    assert resp.headers.get('CST'), 'CST token missing from response'
    assert resp.headers.get('X-SECURITY-TOKEN'), 'X-SECURITY-TOKEN missing from response'
    print(f"  CST token received: {resp.headers['CST'][:20]}...")


# ── Accounts ──

@skip_no_credentials
def test_ig_accounts(ig_session):
    """Fetch account list and verify key fields."""
    resp = requests.get(
        f'{BASE_URL}/accounts',
        headers=_headers(ig_session),
        timeout=15,
    )
    assert resp.status_code == 200, f'Failed: {resp.status_code} {resp.text}'
    data = resp.json()
    assert 'accounts' in data
    assert len(data['accounts']) > 0

    acct = data['accounts'][0]
    assert 'accountId' in acct
    assert 'accountName' in acct
    assert 'balance' in acct
    balance = acct['balance']
    assert 'balance' in balance
    assert 'available' in balance
    print(f"  Account: {acct['accountId']} ({acct['accountName']})")
    print(f"  Balance: {balance['balance']} {acct.get('currency', 'N/A')}")
    print(f"  Available: {balance['available']}")
    print(f"  P&L: {balance.get('profitLoss', 0)}")


# ── Markets / Instruments ──

@skip_no_credentials
def test_ig_search_markets(ig_session):
    """Search IG Markets for forex instruments."""
    resp = requests.get(
        f'{BASE_URL}/markets',
        headers=_headers(ig_session),
        params={'searchTerm': 'EUR USD'},
        timeout=15,
    )
    assert resp.status_code == 200, f'Failed: {resp.status_code} {resp.text}'
    data = resp.json()
    assert 'markets' in data
    assert len(data['markets']) > 0
    print(f"  Found {len(data['markets'])} markets for 'EUR USD'")
    for m in data['markets'][:5]:
        print(f"    {m.get('epic', 'N/A')}: {m.get('instrumentName', 'N/A')}")


@skip_no_credentials
def test_ig_market_details(ig_session):
    """Fetch details for EUR/USD epic."""
    epic = 'CS.D.EURUSD.CFD.IP'
    resp = requests.get(
        f'{BASE_URL}/markets/{epic}',
        headers=_headers(ig_session),
        timeout=15,
    )
    assert resp.status_code == 200, f'Failed for {epic}: {resp.status_code} {resp.text}'
    data = resp.json()
    assert 'instrument' in data
    assert 'snapshot' in data

    instrument = data['instrument']
    assert instrument.get('epic') == epic
    assert 'EUR' in instrument.get('name', '')

    snapshot = data['snapshot']
    assert 'bid' in snapshot
    assert 'offer' in snapshot
    print(f"  {instrument.get('name')}: bid={snapshot['bid']}, offer={snapshot['offer']}")
    print(f"  Market status: {snapshot.get('marketStatus', 'N/A')}")


@skip_no_credentials
def test_ig_multiple_epics(ig_session):
    """Verify multiple common epics are accessible."""
    epics = [
        'CS.D.EURUSD.CFD.IP',
        'CS.D.GBPUSD.CFD.IP',
        'CS.D.USDJPY.CFD.IP',
    ]
    for epic in epics:
        resp = requests.get(
            f'{BASE_URL}/markets/{epic}',
            headers=_headers(ig_session),
            timeout=15,
        )
        assert resp.status_code == 200, f'Failed for {epic}: {resp.status_code}'
        snapshot = resp.json().get('snapshot', {})
        bid = snapshot.get('bid', 0)
        offer = snapshot.get('offer', 0)
        print(f"  {epic}: bid={bid}, offer={offer}")


# ── Pricing / Historical Candles ──

@skip_no_credentials
def test_ig_fetch_prices(ig_session):
    """Fetch recent historical prices for EUR/USD."""
    epic = 'CS.D.EURUSD.CFD.IP'
    resp = requests.get(
        f'{BASE_URL}/prices/{epic}/HOUR/10',
        headers={**_headers(ig_session), 'Version': '2'},
        timeout=15,
    )
    assert resp.status_code == 200, f'Failed: {resp.status_code} {resp.text}'
    data = resp.json()
    assert 'prices' in data
    prices = data['prices']
    assert len(prices) > 0, 'No prices returned'

    for p in prices[:3]:
        close = p.get('closePrice', {})
        bid = close.get('bid', 0)
        ask = close.get('ask', 0)
        print(f"  {p.get('snapshotTime', 'N/A')}: bid={bid}, ask={ask}")


@skip_no_credentials
def test_ig_fetch_prices_multiple_resolutions(ig_session):
    """Verify price fetching works for different resolutions."""
    epic = 'CS.D.EURUSD.CFD.IP'
    for resolution in ['MINUTE', 'MINUTE_5', 'MINUTE_15', 'HOUR', 'HOUR_4', 'DAY']:
        time.sleep(1)  # IG rate limit: ~10 req/sec on demo
        resp = requests.get(
            f'{BASE_URL}/prices/{epic}/{resolution}/5',
            headers={**_headers(ig_session), 'Version': '2'},
            timeout=15,
        )
        if resp.status_code == 403 and 'exceeded-api-key-allowance' in resp.text:
            pytest.skip('IG rate limit exceeded - try again later')
        assert resp.status_code == 200, f'Failed for {resolution}: {resp.status_code}'
        prices = resp.json().get('prices', [])
        assert len(prices) > 0, f'No prices for resolution {resolution}'


# ── Positions & Orders (read-only) ──

@skip_no_credentials
def test_ig_open_positions(ig_session):
    """Fetch open positions (should succeed even if empty)."""
    resp = requests.get(
        f'{BASE_URL}/positions',
        headers={**_headers(ig_session), 'Version': '2'},
        timeout=15,
    )
    assert resp.status_code == 200, f'Failed: {resp.status_code} {resp.text}'
    data = resp.json()
    assert 'positions' in data
    print(f"  Open positions: {len(data['positions'])}")


@skip_no_credentials
def test_ig_working_orders(ig_session):
    """Fetch working/pending orders (should succeed even if empty)."""
    resp = requests.get(
        f'{BASE_URL}/workingorders',
        headers={**_headers(ig_session), 'Version': '2'},
        timeout=15,
    )
    assert resp.status_code == 200, f'Failed: {resp.status_code} {resp.text}'
    data = resp.json()
    assert 'workingOrders' in data
    print(f"  Working orders: {len(data['workingOrders'])}")


@skip_no_credentials
def test_ig_activity_history(ig_session):
    """Fetch recent account activity."""
    import arrow
    time.sleep(1)
    # IG expects DD-MM-YYYY format for activity history
    to_date = arrow.utcnow().format('DD-MM-YYYY')
    from_date = arrow.utcnow().shift(days=-30).format('DD-MM-YYYY')
    resp = requests.get(
        f'{BASE_URL}/history/activity/{from_date}/{to_date}',
        headers={**_headers(ig_session), 'Version': '1'},
        timeout=15,
    )
    if resp.status_code == 403 and 'exceeded-api-key-allowance' in resp.text:
        pytest.skip('IG rate limit exceeded - try again later')
    assert resp.status_code == 200, f'Failed: {resp.status_code} {resp.text}'
    data = resp.json()
    assert 'activities' in data
    print(f"  Activities (last 30 days): {len(data['activities'])}")


# ── Watchlists ──

@skip_no_credentials
def test_ig_watchlists(ig_session):
    """Fetch available watchlists."""
    time.sleep(1)
    resp = requests.get(
        f'{BASE_URL}/watchlists',
        headers=_headers(ig_session),
        timeout=15,
    )
    if resp.status_code == 403 and 'exceeded-api-key-allowance' in resp.text:
        pytest.skip('IG rate limit exceeded - try again later')
    assert resp.status_code == 200, f'Failed: {resp.status_code} {resp.text}'
    data = resp.json()
    assert 'watchlists' in data
    print(f"  Watchlists: {len(data['watchlists'])}")
    for w in data['watchlists'][:5]:
        print(f"    {w.get('name', 'N/A')} (id={w.get('id', 'N/A')})")


# ── Error Handling ──

def test_ig_invalid_api_key():
    """Verify IG rejects invalid credentials."""
    resp = requests.post(
        f'{BASE_URL}/session',
        headers={
            'X-IG-API-KEY': 'INVALID_KEY_12345',
            'Content-Type': 'application/json',
            'Version': '2',
        },
        json={
            'identifier': 'invalid_user',
            'password': 'invalid_pass',
        },
        timeout=15,
    )
    assert resp.status_code in (401, 403, 400), f'Expected auth error, got {resp.status_code}'


def test_ig_api_reachable():
    """Basic connectivity check - IG demo API should respond."""
    resp = requests.get(f'{BASE_URL}/session', timeout=15)
    # Without proper auth, should get an error status, not a connection error
    assert resp.status_code in (400, 401, 403, 405)
