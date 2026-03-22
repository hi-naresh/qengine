"""
Interactive Brokers (IBKR) Connection Tests

Tests connectivity to IBKR TWS/IB Gateway using credentials from algo-bot/.env.
IBKR requires a running TWS or IB Gateway instance (no REST API).

Tests are split into:
- Configuration tests (always run, no TWS needed)
- Connection tests (require running TWS/IB Gateway)

Run with: pytest tests/test_ibkr_connection.py -v
"""
import os
import socket
import pytest
from dotenv import load_dotenv

# Load credentials from algo-bot .env
ENV_PATH = os.path.join(os.path.dirname(__file__), '../..', '..', 'algo-bot', '.env')
load_dotenv(ENV_PATH)

IBKR_ACCOUNT_ID = os.environ.get('IBKR_ACCOUNT_ID', '')
IBKR_HOST = os.environ.get('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.environ.get('IBKR_PORT', '7497'))


def _is_tws_running(host: str = None, port: int = None) -> bool:
    """Check if TWS/IB Gateway is listening on the configured port."""
    h = host or IBKR_HOST
    p = port or IBKR_PORT
    try:
        with socket.create_connection((h, p), timeout=3):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def _has_ib_insync() -> bool:
    try:
        import ib_insync
        return True
    except ImportError:
        return False


skip_no_credentials = pytest.mark.skipif(
    not IBKR_ACCOUNT_ID,
    reason='IBKR_ACCOUNT_ID not set in .env'
)

skip_no_tws = pytest.mark.skipif(
    not _is_tws_running(),
    reason=f'TWS/IB Gateway not running at {IBKR_HOST}:{IBKR_PORT}'
)

skip_no_ib_insync = pytest.mark.skipif(
    not _has_ib_insync(),
    reason='ib_insync not installed (pip install ib_insync)'
)


# ── Configuration Tests (no TWS required) ──

def test_ibkr_credentials_loaded():
    """Verify IBKR credentials are loaded from .env."""
    assert len(IBKR_ACCOUNT_ID) > 0, 'IBKR_ACCOUNT_ID is empty'
    assert len(IBKR_HOST) > 0, 'IBKR_HOST is empty'
    assert IBKR_PORT > 0, 'IBKR_PORT must be positive'
    print(f"  Account: {IBKR_ACCOUNT_ID}")
    print(f"  Host: {IBKR_HOST}:{IBKR_PORT}")


def test_ibkr_host_format():
    """Verify host is a valid IP or hostname."""
    parts = IBKR_HOST.split('.')
    # Either IP (4 parts) or hostname
    is_ip = len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
    is_hostname = all(c.isalnum() or c in '.-' for c in IBKR_HOST)
    assert is_ip or is_hostname, f'Invalid host format: {IBKR_HOST}'


def test_ibkr_port_range():
    """Verify port is in valid range. Common ports: 7496 (live), 7497 (paper), 4001/4002 (Gateway)."""
    assert 1 <= IBKR_PORT <= 65535, f'Port out of range: {IBKR_PORT}'
    known_ports = {7496: 'TWS Live', 7497: 'TWS Paper', 4001: 'Gateway Live', 4002: 'Gateway Paper'}
    if IBKR_PORT in known_ports:
        print(f"  Port {IBKR_PORT} -> {known_ports[IBKR_PORT]}")
    else:
        print(f"  Port {IBKR_PORT} -> Custom (not a standard IBKR port)")


def test_ibkr_account_id_format():
    """IBKR account IDs typically start with 'D' (demo) or 'U' (live) followed by digits."""
    # DU = demo, U = live, F = financial advisor, etc.
    assert len(IBKR_ACCOUNT_ID) >= 2, 'Account ID too short'
    prefix = IBKR_ACCOUNT_ID[:2]
    expected_prefixes = ['DU', 'DF', 'U', 'F', 'FA']
    has_valid_prefix = any(IBKR_ACCOUNT_ID.startswith(p) for p in expected_prefixes)
    if has_valid_prefix:
        is_demo = IBKR_ACCOUNT_ID.startswith('D')
        print(f"  Account type: {'Demo/Paper' if is_demo else 'Live'}")
    else:
        print(f"  Account prefix '{prefix}' - non-standard (may still be valid)")


def test_ibkr_utils_symbol_conversion():
    """Test IBKR symbol to contract parameter conversion."""
    from qengine.modes.import_candles_mode.drivers.IBKR.ibkr_utils import symbol_to_contract_params

    # Forex
    params = symbol_to_contract_params('EUR-USD')
    assert params['sec_type'] == 'CASH'
    assert params['symbol'] == 'EUR'
    assert params['currency'] == 'USD'
    assert params['exchange'] == 'IDEALPRO'

    # Gold
    params = symbol_to_contract_params('XAU-USD')
    assert params['sec_type'] == 'FUT'
    assert params['symbol'] == 'GC'

    # Oil
    params = symbol_to_contract_params('WTI-USD')
    assert params['sec_type'] == 'FUT'
    assert params['symbol'] == 'CL'

    print("  EUR-USD -> CASH IDEALPRO")
    print("  XAU-USD -> FUT GC COMEX")
    print("  WTI-USD -> FUT CL NYMEX")


def test_ibkr_utils_timeframe_conversion():
    """Test IBKR timeframe to bar size conversion."""
    from qengine.modes.import_candles_mode.drivers.IBKR.ibkr_utils import timeframe_to_bar_size
    from qengine.enums import timeframes

    assert timeframe_to_bar_size(timeframes.MINUTE_1) == '1 min'
    assert timeframe_to_bar_size(timeframes.MINUTE_5) == '5 mins'
    assert timeframe_to_bar_size(timeframes.HOUR_1) == '1 hour'
    assert timeframe_to_bar_size(timeframes.HOUR_4) == '4 hours'
    assert timeframe_to_bar_size(timeframes.DAY_1) == '1 day'


def test_ibkr_utils_duration_calculation():
    """Test IBKR duration string calculation."""
    from qengine.modes.import_candles_mode.drivers.IBKR.ibkr_utils import timeframe_to_duration
    from qengine.enums import timeframes

    # 5000 1-min candles ~ 3.5 days
    dur = timeframe_to_duration(timeframes.MINUTE_1, 5000)
    assert 'D' in dur

    # 5000 1-hour candles ~ 208 days
    dur = timeframe_to_duration(timeframes.HOUR_1, 5000)
    assert 'D' in dur

    # Very long duration should use years
    dur = timeframe_to_duration(timeframes.DAY_1, 5000)
    assert 'Y' in dur


# ── Network Connectivity Tests ──

def test_ibkr_tws_port_check():
    """Check if TWS/IB Gateway is listening on the configured port."""
    is_running = _is_tws_running()
    if is_running:
        print(f"  TWS/IB Gateway is RUNNING at {IBKR_HOST}:{IBKR_PORT}")
    else:
        print(f"  TWS/IB Gateway is NOT running at {IBKR_HOST}:{IBKR_PORT}")
        print("  To run IBKR connection tests, start TWS or IB Gateway first")
    # This test always passes - it's informational
    assert True


def test_ibkr_common_ports():
    """Check all common IBKR ports for running instances."""
    ports = {
        7496: 'TWS Live Trading',
        7497: 'TWS Paper Trading',
        4001: 'IB Gateway Live',
        4002: 'IB Gateway Paper',
    }
    found = []
    for port, desc in ports.items():
        if _is_tws_running(IBKR_HOST, port):
            found.append((port, desc))
            print(f"  Port {port} ({desc}): LISTENING")
        else:
            print(f"  Port {port} ({desc}): not available")

    if not found:
        print("  No IBKR services detected on standard ports")


# ── ib_insync Package Tests ──

def test_ibkr_ib_insync_installed():
    """Check if ib_insync package is available."""
    if _has_ib_insync():
        import ib_insync
        print(f"  ib_insync version: {ib_insync.__version__}")
    else:
        print("  ib_insync NOT installed. Install with: pip install ib_insync")
    assert True  # Informational


# ── Live Connection Tests (require TWS running) ──

@skip_no_tws
@skip_no_ib_insync
def test_ibkr_connect():
    """Test connecting to TWS/IB Gateway."""
    from ib_insync import IB
    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=99, timeout=10)
        assert ib.isConnected()
        print(f"  Connected to TWS at {IBKR_HOST}:{IBKR_PORT}")
    finally:
        ib.disconnect()


@skip_no_tws
@skip_no_ib_insync
@skip_no_credentials
def test_ibkr_account_summary():
    """Fetch account summary from TWS."""
    from ib_insync import IB
    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=100, timeout=10)
        summary = ib.accountSummary()
        assert len(summary) > 0, 'No account summary data returned'

        for item in summary:
            if item.tag in ('TotalCashBalance', 'NetLiquidation', 'AvailableFunds') and item.currency == 'USD':
                print(f"  {item.tag}: {item.value} {item.currency}")
    finally:
        ib.disconnect()


@skip_no_tws
@skip_no_ib_insync
def test_ibkr_managed_accounts():
    """Fetch managed accounts list from TWS."""
    from ib_insync import IB
    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=101, timeout=10)
        accounts = ib.managedAccounts()
        assert len(accounts) > 0, 'No managed accounts returned'
        print(f"  Managed accounts: {accounts}")

        if IBKR_ACCOUNT_ID:
            assert IBKR_ACCOUNT_ID in accounts, (
                f'Account {IBKR_ACCOUNT_ID} not in managed accounts: {accounts}'
            )
    finally:
        ib.disconnect()


@skip_no_tws
@skip_no_ib_insync
def test_ibkr_positions():
    """Fetch open positions from TWS (may be empty)."""
    from ib_insync import IB
    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=102, timeout=10)
        positions = ib.positions()
        print(f"  Open positions: {len(positions)}")
        for pos in positions[:5]:
            print(f"    {pos.contract.symbol}/{pos.contract.currency}: {pos.position} @ {pos.avgCost}")
    finally:
        ib.disconnect()


@skip_no_tws
@skip_no_ib_insync
def test_ibkr_open_orders():
    """Fetch open/pending orders from TWS (may be empty)."""
    from ib_insync import IB
    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=103, timeout=10)
        trades = ib.openTrades()
        print(f"  Open orders: {len(trades)}")
        for t in trades[:5]:
            print(f"    {t.contract.symbol}: {t.order.action} {t.order.totalQuantity} ({t.order.orderType})")
    finally:
        ib.disconnect()


@skip_no_tws
@skip_no_ib_insync
def test_ibkr_forex_contract():
    """Verify EUR/USD forex contract can be qualified."""
    from ib_insync import IB, Forex
    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=104, timeout=10)
        contract = Forex('EURUSD')
        qualified = ib.qualifyContracts(contract)
        assert len(qualified) > 0, 'Could not qualify EUR/USD contract'
        c = qualified[0]
        assert c.symbol == 'EUR'
        assert c.currency == 'USD'
        print(f"  EUR/USD contract qualified: conId={c.conId}, exchange={c.exchange}")
    finally:
        ib.disconnect()


@skip_no_tws
@skip_no_ib_insync
def test_ibkr_market_data():
    """Fetch a market data snapshot for EUR/USD."""
    from ib_insync import IB, Forex
    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=105, timeout=10)
        contract = Forex('EURUSD')
        ib.qualifyContracts(contract)

        ticker = ib.reqMktData(contract, snapshot=True)
        ib.sleep(2)

        # At least one of these should be available
        has_data = ticker.last > 0 or ticker.bid > 0 or ticker.ask > 0
        if has_data:
            print(f"  EUR/USD: bid={ticker.bid}, ask={ticker.ask}, last={ticker.last}")
        else:
            print("  No market data (may need market data subscription)")

        ib.cancelMktData(contract)
    finally:
        ib.disconnect()


@skip_no_tws
@skip_no_ib_insync
def test_ibkr_historical_data():
    """Fetch recent historical bars for EUR/USD."""
    from ib_insync import IB, Forex
    ib = IB()
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=106, timeout=10)
        contract = Forex('EURUSD')
        ib.qualifyContracts(contract)

        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='1 hour',
            whatToShow='MIDPOINT',
            useRTH=False,
            formatDate=2,
        )
        assert len(bars) > 0, 'No historical bars returned'
        print(f"  Fetched {len(bars)} hourly bars")
        last_bar = bars[-1]
        print(f"  Latest: O={last_bar.open} H={last_bar.high} L={last_bar.low} C={last_bar.close}")
    finally:
        ib.disconnect()
