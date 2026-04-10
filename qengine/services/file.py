import csv
import json
import os

import arrow

from qengine.config import config
from qengine.services.tradingview import tradingview_logs
from qengine.services import report as report_service
from qengine.store import store
import qengine.helpers as jh


def _holding_period_hours(holding_period) -> str:
    """Convert holding period (seconds) to hours with 2 decimal places."""
    if not holding_period:
        return ''
    try:
        seconds = float(holding_period)
        hours = seconds / 3600
        return f'{hours:.2f}'
    except (ValueError, TypeError):
        return str(holding_period)


def _fmt_timestamp(ts) -> str:
    """Convert millisecond timestamp to readable datetime string."""
    if not ts:
        return ''
    try:
        return jh.timestamp_to_time(int(ts))[:19]
    except (ValueError, TypeError):
        return str(ts)


def store_logs(export_json: bool = False, export_tradingview: bool = False, export_csv: bool = False) -> dict:
    if store.closed_trades.count == 0:
        return {
            'json': None,
            'tradingview': None,
            'csv': None
        }

    result = {}
    file_name = jh.get_session_id()
    trades_json = {'trades': [], 'considering_timeframes': config['app']['considering_timeframes']}
    for t in store.closed_trades.trades:
        trades_json['trades'].append(t.to_json)

    if export_json:
        path = f'storage/json/{file_name}.json'

        os.makedirs('./storage/json', exist_ok=True)
        with open(path, 'w+') as outfile:
            def set_default(obj):
                if isinstance(obj, set):
                    return list(obj)
                raise TypeError

            json.dump(trades_json, outfile, default=set_default)
            result['json'] = path

    # store output for TradingView.com's pine-editor
    if export_tradingview:
        result['tradingview'] = tradingview_logs(file_name)

    # write CSV grouped by sessions/cycles
    if export_csv:
        path = f'storage/csv/{file_name}.csv'
        os.makedirs('./storage/csv', exist_ok=True)

        sessions = report_service.hedge_sessions()

        with open(path, 'w', newline='') as outfile:
            wr = csv.writer(outfile, quoting=csv.QUOTE_ALL)

            if sessions:
                # Session-aware CSV: each trade row includes session context
                header = [
                    'session', 'outcome', 'levels', 'session_pnl',
                    'trade_#', 'symbol', 'type', 'level',
                    'entry_price', 'exit_price', 'qty', 'fee', 'size',
                    'pnl', 'pnl_percentage', 'holding_period',
                    'opened_at', 'closed_at',
                ]
                wr.writerow(header)

                for s in sessions:
                    for ti, t in enumerate(s['trades']):
                        meta = t.get('meta', {})
                        wr.writerow([
                            s['session'],
                            s['outcome'],
                            s['levels'],
                            round(s['total_pnl'], 6),
                            ti + 1,
                            t.get('symbol', ''),
                            t.get('type', ''),
                            meta.get('level', ''),
                            t.get('entry_price', ''),
                            t.get('exit_price', ''),
                            t.get('qty', ''),
                            t.get('fee', ''),
                            t.get('size', ''),
                            t.get('pnl', t.get('PNL', '')),
                            t.get('pnl_percentage', t.get('PNL_percentage', '')),
                            _holding_period_hours(t.get('holding_period', '')),
                            _fmt_timestamp(t.get('opened_at')),
                            _fmt_timestamp(t.get('closed_at')),
                        ])
            else:
                # Fallback: flat trade list (no session metadata)
                for i, t in enumerate(trades_json['trades']):
                    if i == 0:
                        wr.writerow(t.keys())
                    wr.writerow(t.values())

            result['csv'] = path

    return result
