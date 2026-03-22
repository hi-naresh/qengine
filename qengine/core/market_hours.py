from datetime import datetime, timezone, timedelta
from typing import Optional

from qengine.core.instruments import instrument_registry

# New York timezone offset (EST = UTC-5, EDT = UTC-4)
# For simplicity we use fixed UTC offsets; a future enhancement could use pytz
NY_OFFSET_STANDARD = timedelta(hours=-5)
NY_OFFSET_DST = timedelta(hours=-4)


def _timestamp_to_utc(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def _is_us_dst(dt: datetime) -> bool:
    """Approximate US DST: second Sunday of March to first Sunday of November."""
    year = dt.year
    # March: second Sunday
    march1 = datetime(year, 3, 1, tzinfo=timezone.utc)
    march_second_sun = march1 + timedelta(days=(6 - march1.weekday()) % 7 + 7)
    dst_start = march_second_sun.replace(hour=7)  # 2am ET = 7am UTC

    # November: first Sunday
    nov1 = datetime(year, 11, 1, tzinfo=timezone.utc)
    nov_first_sun = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    dst_end = nov_first_sun.replace(hour=6)  # 2am ET = 6am UTC

    return dst_start <= dt < dst_end


def _ny_offset(dt: datetime) -> timedelta:
    return NY_OFFSET_DST if _is_us_dst(dt) else NY_OFFSET_STANDARD


def _to_ny_time(dt: datetime) -> datetime:
    return dt + _ny_offset(dt)


class MarketHours:
    """Determines if market is open for a given instrument at a given time."""

    def is_market_open(self, symbol: str, timestamp_ms: int) -> bool:
        dt = _timestamp_to_utc(timestamp_ms)
        schedule = self._get_schedule(symbol)

        if schedule == 'forex':
            return self._is_forex_open(dt)
        elif schedule in ('commodity_metals', 'commodity_energy'):
            return self._is_commodity_open(dt, schedule)
        elif schedule.startswith('index_'):
            return self._is_index_open(dt, schedule)
        # default: 24/7 (crypto-like)
        return True

    def next_market_open(self, symbol: str, timestamp_ms: int) -> Optional[int]:
        if self.is_market_open(symbol, timestamp_ms):
            return timestamp_ms

        dt = _timestamp_to_utc(timestamp_ms)
        schedule = self._get_schedule(symbol)

        if schedule == 'forex':
            return self._next_forex_open(dt)
        return timestamp_ms

    def next_market_close(self, symbol: str, timestamp_ms: int) -> Optional[int]:
        if not self.is_market_open(symbol, timestamp_ms):
            return timestamp_ms

        dt = _timestamp_to_utc(timestamp_ms)
        schedule = self._get_schedule(symbol)

        if schedule == 'forex':
            return self._next_forex_close(dt)
        return None

    def is_rollover_time(self, timestamp_ms: int) -> bool:
        """Check if it's the daily rollover time (5pm NY / 17:00 ET)."""
        dt = _timestamp_to_utc(timestamp_ms)
        ny = _to_ny_time(dt)
        return ny.hour == 17 and ny.minute == 0

    def minutes_to_close(self, symbol: str, timestamp_ms: int) -> Optional[int]:
        if not self.is_market_open(symbol, timestamp_ms):
            return 0
        close_ts = self.next_market_close(symbol, timestamp_ms)
        if close_ts is None:
            return None
        return max(0, (close_ts - timestamp_ms) // 60_000)

    def _get_schedule(self, symbol: str) -> str:
        inst = instrument_registry.get(symbol)
        if inst:
            return inst.trading_hours
        return 'forex'

    def _is_forex_open(self, dt: datetime) -> bool:
        """Forex: Sunday 5pm ET to Friday 5pm ET (continuous)."""
        ny = _to_ny_time(dt)
        weekday = ny.weekday()  # 0=Mon, 6=Sun
        hour = ny.hour

        # Closed: Friday after 5pm through Sunday before 5pm
        if weekday == 4 and hour >= 17:  # Friday after 5pm
            return False
        if weekday == 5:  # Saturday
            return False
        if weekday == 6 and hour < 17:  # Sunday before 5pm
            return False
        return True

    def _is_commodity_open(self, dt: datetime, schedule: str) -> bool:
        """Commodities follow similar hours to forex with a daily break."""
        # First check forex hours (weekend closure applies)
        if not self._is_forex_open(dt):
            return False

        ny = _to_ny_time(dt)
        hour = ny.hour

        if schedule == 'commodity_metals':
            # Metals: daily break 5pm-6pm ET
            if hour == 17:
                return False
        elif schedule == 'commodity_energy':
            # Energy: daily break 5pm-6pm ET
            if hour == 17:
                return False
        return True

    def _is_index_open(self, dt: datetime, schedule: str) -> bool:
        """Index CFDs have extended hours but not 24/7."""
        ny = _to_ny_time(dt)
        weekday = ny.weekday()
        hour = ny.hour

        # Weekend closed
        if weekday == 5:  # Saturday
            return False
        if weekday == 6:  # Sunday
            if schedule == 'index_us':
                return hour >= 18  # US indices open Sunday 6pm ET
            return False
        if weekday == 4 and hour >= 17:  # Friday after 5pm
            return False

        if schedule == 'index_us':
            # US indices: Sun 6pm - Fri 5pm with daily break 4:15pm-4:30pm (simplified)
            return True
        elif schedule == 'index_eu':
            # EU indices: roughly 1am-9pm ET on weekdays
            return 1 <= hour < 21
        elif schedule == 'index_asia':
            # Asia indices: roughly 7pm-4am ET
            return hour >= 19 or hour < 4
        return True

    def _next_forex_open(self, dt: datetime) -> int:
        """Return timestamp (ms) of next forex market open."""
        ny = _to_ny_time(dt)
        weekday = ny.weekday()

        if weekday == 5:  # Saturday -> next Sunday 5pm
            days_ahead = 1
        elif weekday == 6 and ny.hour < 17:  # Sunday before 5pm
            days_ahead = 0
        elif weekday == 4 and ny.hour >= 17:  # Friday after 5pm -> Sunday 5pm
            days_ahead = 2
        else:
            return int(dt.timestamp() * 1000)

        next_open_ny = ny.replace(hour=17, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        # Convert back to UTC
        offset = _ny_offset(dt)
        next_open_utc = next_open_ny - offset
        return int(next_open_utc.replace(tzinfo=timezone.utc).timestamp() * 1000)

    def _next_forex_close(self, dt: datetime) -> int:
        """Return timestamp (ms) of next forex market close (Friday 5pm ET)."""
        ny = _to_ny_time(dt)
        weekday = ny.weekday()

        # Find next Friday
        days_to_friday = (4 - weekday) % 7
        if days_to_friday == 0 and ny.hour >= 17:
            days_to_friday = 7

        next_close_ny = ny.replace(hour=17, minute=0, second=0, microsecond=0) + timedelta(days=days_to_friday)
        offset = _ny_offset(dt)
        next_close_utc = next_close_ny - offset
        return int(next_close_utc.replace(tzinfo=timezone.utc).timestamp() * 1000)


    def current_session(self, timestamp_ms: int) -> str:
        """
        Return the current forex trading session.
        Sessions (in NY/ET time):
        - 'tokyo':    7pm - 4am ET (previous day 19:00 to 04:00)
        - 'london':   3am - 12pm ET
        - 'new_york': 8am - 5pm ET
        - 'overlap':  8am - 12pm ET (London + NY overlap)
        - 'off':      market closed
        """
        dt = _timestamp_to_utc(timestamp_ms)
        ny = _to_ny_time(dt)
        hour = ny.hour

        if not self._is_forex_open(dt):
            return 'off'

        # London: 3am-12pm ET, NY: 8am-5pm ET
        in_london = 3 <= hour < 12
        in_ny = 8 <= hour < 17

        if in_london and in_ny:
            return 'overlap'
        elif in_ny:
            return 'new_york'
        elif in_london:
            return 'london'
        elif hour >= 19 or hour < 4:
            return 'tokyo'
        else:
            return 'new_york'  # 12pm-7pm ET gap defaults to NY


market_hours = MarketHours()
