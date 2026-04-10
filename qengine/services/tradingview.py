import os

import qengine.helpers as jh
from qengine.store import store


def tradingview_logs(study_name: str) -> str:
    starting_balance = sum(
        store.exchanges.storage[e].starting_assets[jh.app_currency()]
        for e in store.exchanges.storage
    )

    trades = store.closed_trades.trades
    if not trades:
        path = _output_path()
        os.makedirs('./storage/trading-view-pine-editor', exist_ok=True)
        with open(path, 'w+') as outfile:
            outfile.write(
                f'//@version=6\nstrategy("{study_name}", overlay=true, '
                f'initial_capital={starting_balance})\n'
            )
        return path

    # Group trades by session
    sessions_map = {}
    standalone_idx = 0
    for t in trades:
        meta = getattr(t, 'meta', {})
        sn = meta.get('session')
        if sn is not None:
            if sn not in sessions_map:
                sessions_map[sn] = []
            sessions_map[sn].append(t)
        else:
            standalone_idx += 1
            sessions_map[f'T{standalone_idx}'] = [t]

    sorted_keys = sorted(sessions_map.keys(), key=lambda k: (isinstance(k, str), k))

    # Session colors — cycle through palette
    palette = [
        '#2962FF', '#FF6D00', '#00C853', '#AA00FF', '#FFD600',
        '#00BFA5', '#FF1744', '#651FFF', '#F50057', '#00B0FF',
    ]

    # Build arrays of timestamps and metadata for data-driven plotting
    # This avoids per-trade if blocks and works on ANY chart timeframe
    entry_times = []
    exit_times = []
    entry_prices = []
    exit_prices = []
    entry_qtys = []
    entry_dirs = []   # 1 = long, -1 = short
    entry_labels = []
    trade_session_idx = []  # index into sorted_keys for color

    tp_lines = []   # (start_ts, end_ts, price, session_idx)
    sl_lines = []   # (start_ts, end_ts, price, session_idx)
    hedge_lines = [] # (start_ts, end_ts, price, session_idx, level)
    session_regions = []  # (start_ts, end_ts, session_idx)

    for si, session_key in enumerate(sorted_keys):
        session_trades = sessions_map[session_key]

        session_open = int(session_trades[0].opened_at)
        session_close = None
        session_exit = None

        for t in session_trades:
            meta = getattr(t, 'meta', {})
            reason = meta.get('session_exit_reason', meta.get('exit_reason'))
            if reason:
                session_exit = reason
            if t.closed_at:
                session_close = int(t.closed_at)

        # Collect trade data
        for t in session_trades:
            meta = getattr(t, 'meta', {})
            level = meta.get('level', 0)
            is_long = t.type == 'long'

            entry_times.append(int(t.opened_at))
            entry_prices.append(t.entry_price)
            entry_qtys.append(abs(t.qty))
            entry_dirs.append(1 if is_long else -1)
            entry_labels.append(f'S{session_key}_L{level}')
            trade_session_idx.append(si)

            if t.closed_at:
                exit_times.append(int(t.closed_at))
                exit_prices.append(t.exit_price)
            else:
                exit_times.append(0)
                exit_prices.append(0)

        # Session region
        if session_close:
            session_regions.append((session_open, session_close, si))

        # TP line
        if session_exit == 'tp_hit' and session_trades and session_close:
            tp_price = session_trades[0].exit_price
            tp_lines.append((session_open, session_close, tp_price, si))

        # SL/bust line
        if session_exit in ('bust', 'liquidation', 'margin_call') and session_trades and session_close:
            bust_price = session_trades[-1].exit_price
            sl_lines.append((session_open, session_close, bust_price, si))

        # Hedge entry lines (L1+)
        for t in session_trades:
            meta = getattr(t, 'meta', {})
            level = meta.get('level', 0)
            if level == 0:
                continue
            end_ts = int(t.closed_at) if t.closed_at else session_close
            if end_ts:
                hedge_lines.append((int(t.opened_at), end_ts, t.entry_price, si, level))

    n = len(entry_times)

    # Pine Script v6 — data-driven approach using arrays
    tv = []
    tv.append(f'//@version=6')
    tv.append(
        f'strategy("{study_name}", overlay=true, initial_capital={starting_balance}, '
        f'commission_type=strategy.commission.percent, commission_value=0.2, '
        f'max_lines_count=500, max_labels_count=500)'
    )
    tv.append('')

    # Helper function to check if a timestamp falls within the current candle
    # Works on ANY chart timeframe
    tv.append('_in_candle(int ts) => time <= ts and time_close >= ts')
    tv.append('')

    # --- Strategy entries and exits ---
    # Use compact array-based lookup: store all timestamps in arrays,
    # scan on each bar for matches
    tv.append(f'// === {n} trades across {len(sorted_keys)} sessions ===')
    tv.append(f'var int TRADE_COUNT = {n}')

    # Entry timestamp array
    tv.append(f'var array<int> _et = array.from({", ".join(str(t) for t in entry_times)})')
    # Exit timestamp array
    tv.append(f'var array<int> _xt = array.from({", ".join(str(t) for t in exit_times)})')
    # Entry qty array
    tv.append(f'var array<float> _eq = array.from({", ".join(_fmt_f(q) for q in entry_qtys)})')
    # Direction array (1=long, -1=short)
    tv.append(f'var array<int> _ed = array.from({", ".join(str(d) for d in entry_dirs)})')
    # Entry price array (for labels)
    tv.append(f'var array<float> _ep = array.from({", ".join(_fmt_f(p) for p in entry_prices)})')
    # Session index per trade (for coloring)
    tv.append(f'var array<int> _si = array.from({", ".join(str(s) for s in trade_session_idx)})')
    tv.append('')

    # Trade labels array
    tv.append('var array<string> _lbl = array.from(')
    for i, lbl in enumerate(entry_labels):
        comma = ',' if i < n - 1 else ''
        tv.append(f'  "{lbl}"{comma}')
    tv.append(')')
    tv.append('')

    # Session palette
    n_colors = min(len(sorted_keys), len(palette))
    color_entries = ', '.join(
        _pine_color(palette[i % len(palette)]) for i in range(n_colors)
    )
    tv.append(f'var array<color> _scolors = array.from({color_entries})')
    tv.append('')

    # Main loop: scan all trades on each bar
    tv.append('for i = 0 to TRADE_COUNT - 1')
    tv.append('    string id = array.get(_lbl, i)')
    tv.append('    int dir = array.get(_ed, i)')
    tv.append('    float qty = array.get(_eq, i)')
    tv.append('    float ep = array.get(_ep, i)')
    tv.append('    int si = array.get(_si, i)')
    tv.append('    color sc = array.get(_scolors, si % array.size(_scolors))')
    tv.append('')
    tv.append('    // Entry')
    tv.append('    if _in_candle(array.get(_et, i))')
    tv.append('        if dir == 1')
    tv.append('            strategy.entry(id, strategy.long, qty=qty)')
    tv.append('            label.new(bar_index, ep, id, color=sc, textcolor=color.white, style=label.style_label_up, size=size.tiny)')
    tv.append('        else')
    tv.append('            strategy.entry(id, strategy.short, qty=qty)')
    tv.append('            label.new(bar_index, ep, id, color=sc, textcolor=color.white, style=label.style_label_down, size=size.tiny)')
    tv.append('')
    tv.append('    // Exit')
    tv.append('    int xt = array.get(_xt, i)')
    tv.append('    if xt > 0 and _in_candle(xt)')
    tv.append('        strategy.close(id)')
    tv.append('')

    # --- TP lines (green dashed) ---
    if tp_lines:
        _emit_session_lines(tv, tp_lines, '#00C853', 'line.style_dashed', '_tp', 'TP')

    # --- SL/bust lines (red dashed) ---
    if sl_lines:
        _emit_session_lines(tv, sl_lines, '#FF1744', 'line.style_dashed', '_sl', 'SL')

    # --- Hedge entry lines (orange dotted) — limit to avoid hitting 500 line cap ---
    if hedge_lines and len(hedge_lines) <= 200:
        tv.append(f'// Hedge entry levels ({len(hedge_lines)} lines)')
        tv.append(f'var int HEDGE_COUNT = {len(hedge_lines)}')
        tv.append(f'var array<int> _hs = array.from({", ".join(str(h[0]) for h in hedge_lines)})')
        tv.append(f'var array<int> _he = array.from({", ".join(str(h[1]) for h in hedge_lines)})')
        tv.append(f'var array<float> _hp = array.from({", ".join(_fmt_f(h[2]) for h in hedge_lines)})')
        tv.append(f'var array<line> _hlines = array.new<line>(HEDGE_COUNT, na)')
        tv.append('')
        tv.append('for i = 0 to HEDGE_COUNT - 1')
        tv.append('    if _in_candle(array.get(_hs, i))')
        tv.append(f'        array.set(_hlines, i, line.new(bar_index, array.get(_hp, i), bar_index, array.get(_hp, i), color={_pine_color("#FF6D00")}, style=line.style_dotted, width=1))')
        tv.append('    if _in_candle(array.get(_he, i))')
        tv.append('        line l = array.get(_hlines, i)')
        tv.append('        if not na(l)')
        tv.append('            line.set_x2(l, bar_index)')
        tv.append('')

    # --- Session background regions ---
    if session_regions:
        tv.append(f'// Session backgrounds ({len(session_regions)} regions)')
        tv.append(f'var int REGION_COUNT = {len(session_regions)}')
        tv.append(f'var array<int> _rs = array.from({", ".join(str(r[0]) for r in session_regions)})')
        tv.append(f'var array<int> _re = array.from({", ".join(str(r[1]) for r in session_regions)})')
        tv.append(f'var array<int> _ri = array.from({", ".join(str(r[2]) for r in session_regions)})')
        tv.append('')
        tv.append('color _bgc = na')
        tv.append('for i = 0 to REGION_COUNT - 1')
        tv.append('    if time_close >= array.get(_rs, i) and time_close <= array.get(_re, i)')
        tv.append('        _bgc := color.new(array.get(_scolors, array.get(_ri, i) % array.size(_scolors)), 92)')
        tv.append('bgcolor(_bgc)')
        tv.append('')

    path = _output_path()
    os.makedirs('./storage/trading-view-pine-editor', exist_ok=True)
    with open(path, 'w+') as outfile:
        outfile.write('\n'.join(tv))

    return path


def _emit_session_lines(tv: list, lines_data: list, hex_color: str, style: str, prefix: str, label_text: str):
    """Emit Pine code for session-level horizontal lines (TP or SL)."""
    n = len(lines_data)
    tv.append(f'// {label_text} lines ({n})')
    tv.append(f'var int {prefix}_COUNT = {n}')
    tv.append(f'var array<int> {prefix}_s = array.from({", ".join(str(l[0]) for l in lines_data)})')
    tv.append(f'var array<int> {prefix}_e = array.from({", ".join(str(l[1]) for l in lines_data)})')
    tv.append(f'var array<float> {prefix}_p = array.from({", ".join(_fmt_f(l[2]) for l in lines_data)})')
    tv.append(f'var array<line> {prefix}_lines = array.new<line>({prefix}_COUNT, na)')
    tv.append('')
    tv.append(f'for i = 0 to {prefix}_COUNT - 1')
    tv.append(f'    if _in_candle(array.get({prefix}_s, i))')
    tv.append(f'        float p = array.get({prefix}_p, i)')
    tv.append(f'        array.set({prefix}_lines, i, line.new(bar_index, p, bar_index, p, color={_pine_color(hex_color)}, style={style}, width=2))')
    tv.append(f'        label.new(bar_index, p, "{label_text}", color={_pine_color(hex_color)}, textcolor=color.white, style=label.style_label_left, size=size.tiny)')
    tv.append(f'    if _in_candle(array.get({prefix}_e, i))')
    tv.append(f'        line l = array.get({prefix}_lines, i)')
    tv.append(f'        if not na(l)')
    tv.append(f'            line.set_x2(l, bar_index)')
    tv.append('')


def _output_path() -> str:
    return f'storage/trading-view-pine-editor/{jh.get_session_id()}.txt'.replace(":", "-")


def _fmt_f(v) -> str:
    """Format a float for Pine Script (avoid scientific notation)."""
    return f'{v:.6f}' if isinstance(v, float) else str(v)


def _pine_color(hex_color: str) -> str:
    """Convert hex color to Pine Script color.rgb()."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f'color.rgb({r}, {g}, {b})'
