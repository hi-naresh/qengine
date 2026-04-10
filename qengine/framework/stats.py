from dataclasses import dataclass, field
import math


@dataclass
class PipelineStats:
    """
    Comprehensive pipeline analytics — tracks every decision with outcome linkage.

    Decision correctness is evaluated retrospectively: when a cycle ends, we know
    the PnL and can judge whether gate/abort decisions were right.
    """

    # ── Counters ──
    total_gate_checks: int = 0
    entries_blocked: int = 0
    entries_allowed: int = 0
    abort_checks: int = 0
    aborts_triggered: int = 0
    aborts_continued: int = 0
    cycles_completed: int = 0

    # ── Per-decision records ──
    gate_decisions: list = field(default_factory=list)    # full gate log
    abort_decisions: list = field(default_factory=list)   # full abort log
    cycle_outcomes: list = field(default_factory=list)    # per-cycle outcome summary

    # ── Time-series for charting ──
    danger_scores: list = field(default_factory=list)     # [[ts, score], ...]
    gate_threshold_series: list = field(default_factory=list)  # [[ts, threshold], ...]

    # ── Config & learning ──
    config_snapshot: dict = field(default_factory=dict)
    q_value_progression: list = field(default_factory=list)  # [[ts, mean_q, std_q, coverage], ...]

    # ── Size adjustment tracking ──
    size_adjustments: list = field(default_factory=list)  # [[ts, original, adjusted, side], ...]
    total_size_adjustments: int = 0

    # ── Exit suggestion tracking ──
    exit_suggestions: list = field(default_factory=list)  # [[ts, action, details], ...]
    total_exit_suggestions: int = 0

    # ── Order filter tracking ──
    orders_filtered: int = 0
    orders_cancelled_by_filter: int = 0

    # ── Current cycle tracking (internal) ──
    _current_cycle: dict = field(default_factory=dict)
    _pre_entry_blocks: int = 0

    def start_cycle(self, timestamp: float, danger_at_entry: float):
        """Call when a new cycle/position opens."""
        self._current_cycle = {
            'entry_ts': timestamp,
            'danger_at_entry': round(danger_at_entry, 4),
            'abort_checks': 0,
            'abort_triggers': 0,
            'max_danger': danger_at_entry,
            'min_danger': danger_at_entry,
            'danger_sum': 0.0,
            'danger_count': 0,
            'gate_blocks_before_entry': self._pre_entry_blocks,
        }
        self._pre_entry_blocks = 0

    def record_gate(self, timestamp: float, danger: float, allowed: bool,
                    threshold: float = None):
        self.total_gate_checks += 1
        if allowed:
            self.entries_allowed += 1
        else:
            self.entries_blocked += 1
            self._pre_entry_blocks += 1
        safe_threshold = round(threshold, 4) if threshold is not None and math.isfinite(threshold) else None
        self.gate_decisions.append({
            'ts': timestamp,
            'danger': round(danger, 4),
            'threshold': safe_threshold,
            'allowed': allowed,
            'outcome_pnl': None,
        })
        if safe_threshold is not None:
            self.gate_threshold_series.append([timestamp, safe_threshold])
            if len(self.gate_threshold_series) > 6000:
                self.gate_threshold_series = self.gate_threshold_series[-5000:]
        # Cap gate decisions to prevent memory bloat
        if len(self.gate_decisions) > 1000:
            self.gate_decisions = self.gate_decisions[-500:]

    def record_abort(self, timestamp: float, level: int, danger: float,
                     action: str, q_values: list = None,
                     danger_entry: float = None, duration_bars: int = None,
                     pnl_at_abort: float = None):
        self.abort_checks += 1
        if action == 'abort':
            self.aborts_triggered += 1
        else:
            self.aborts_continued += 1

        rec = {
            'ts': timestamp,
            'level': level,
            'danger': round(danger, 4),
            'action': action,
        }
        if q_values is not None:
            rec['q_continue'] = round(q_values[0], 6)
            rec['q_abort'] = round(q_values[1], 6)
            rec['q_margin'] = round(q_values[1] - q_values[0], 6)
        if danger_entry is not None:
            rec['danger_entry'] = round(danger_entry, 4)
        if duration_bars is not None:
            rec['duration_bars'] = duration_bars
        if pnl_at_abort is not None:
            rec['pnl_at_abort'] = round(pnl_at_abort, 4)
        self.abort_decisions.append(rec)
        # Cap abort decisions to prevent memory bloat
        if len(self.abort_decisions) > 1000:
            self.abort_decisions = self.abort_decisions[-500:]

        # Track per-cycle abort activity
        if self._current_cycle:
            self._current_cycle['abort_checks'] += 1
            if action == 'abort':
                self._current_cycle['abort_triggers'] += 1

    def record_size_adjustment(self, timestamp: float, original: float, adjusted: float, side: str):
        self.total_size_adjustments += 1
        self.size_adjustments.append([timestamp, round(original, 4), round(adjusted, 4), side])

    def record_exit_suggestion(self, timestamp: float, action: str, details: dict = None):
        self.total_exit_suggestions += 1
        self.exit_suggestions.append([timestamp, action, details or {}])

    def record_order_filter(self, timestamp: float, side: str, cancelled: bool):
        self.orders_filtered += 1
        if cancelled:
            self.orders_cancelled_by_filter += 1

    def record_danger(self, timestamp: float, score: float):
        self.danger_scores.append([timestamp, round(score, 4)])
        # Cap to last 5000 entries to prevent unbounded memory growth
        if len(self.danger_scores) > 6000:
            self.danger_scores = self.danger_scores[-5000:]
        # Track per-cycle danger range
        if self._current_cycle:
            self._current_cycle['max_danger'] = max(
                self._current_cycle.get('max_danger', 0), score)
            self._current_cycle['min_danger'] = min(
                self._current_cycle.get('min_danger', 1), score)
            self._current_cycle['danger_sum'] += score
            self._current_cycle['danger_count'] += 1

    def end_cycle(self, pnl: float, exit_reason: str = '', level: int = 0,
                  danger_at_exit: float = None, duration_bars: int = 0,
                  session_number: int = None, hp_snapshot: dict = None):
        """Call when cycle ends — records outcome and links back to decisions."""
        self.cycles_completed += 1

        cycle = {
            'cycle': session_number if session_number is not None else self.cycles_completed,
            'pnl': round(pnl, 4),
            'exit_reason': exit_reason,
            'level': level,
            'duration_bars': duration_bars,
            'danger_at_exit': round(danger_at_exit, 4) if danger_at_exit is not None else None,
        }
        if hp_snapshot:
            cycle['hp'] = hp_snapshot

        if self._current_cycle:
            cycle['danger_at_entry'] = self._current_cycle.get('danger_at_entry')
            cycle['max_danger'] = round(self._current_cycle.get('max_danger', 0), 4)
            cycle['min_danger'] = round(self._current_cycle.get('min_danger', 1), 4)
            cnt = self._current_cycle.get('danger_count', 0)
            cycle['avg_danger'] = round(
                self._current_cycle['danger_sum'] / cnt, 4) if cnt > 0 else None
            cycle['abort_checks'] = self._current_cycle.get('abort_checks', 0)
            cycle['abort_triggers'] = self._current_cycle.get('abort_triggers', 0)
            cycle['gate_blocks_before_entry'] = self._current_cycle.get('gate_blocks_before_entry', 0)

        self.cycle_outcomes.append(cycle)

        # Retrospective: link most recent allowed gate decision to this outcome
        for gd in reversed(self.gate_decisions):
            if gd['outcome_pnl'] is None and gd['allowed']:
                gd['outcome_pnl'] = round(pnl, 4)
                break

        self._current_cycle = {}

    def record_cycle_end(self):
        """Backward-compat: simple cycle end without details."""
        if not any(c.get('cycle') == self.cycles_completed + 1 for c in self.cycle_outcomes):
            self.cycles_completed += 1

    def to_dict(self) -> dict:
        # ── Compute analytics ──
        gate_decs = self.gate_decisions
        abort_decs = self.abort_decisions
        outcomes = self.cycle_outcomes
        danger = self.danger_scores

        # Gate analytics
        allowed_with_outcome = [g for g in gate_decs if g['allowed'] and g.get('outcome_pnl') is not None]
        blocked = [g for g in gate_decs if not g['allowed']]
        gate_correct_allows = sum(1 for g in allowed_with_outcome if g['outcome_pnl'] > 0)
        gate_wrong_allows = sum(1 for g in allowed_with_outcome if g['outcome_pnl'] <= 0)
        wrong_allows = [g for g in allowed_with_outcome if g['outcome_pnl'] <= 0]
        correct_allows = [g for g in allowed_with_outcome if g['outcome_pnl'] > 0]
        avg_danger_at_block = (
            sum(g['danger'] for g in blocked) / len(blocked)
        ) if blocked else None
        avg_danger_at_allow = (
            sum(g['danger'] for g in allowed_with_outcome) / len(allowed_with_outcome)
        ) if allowed_with_outcome else None

        # Abort analytics
        abort_triggers = [a for a in abort_decs if a['action'] == 'abort']
        abort_continues = [a for a in abort_decs if a['action'] == 'continue']

        # Cycle analytics
        wins = [c for c in outcomes if c['pnl'] > 0]
        losses = [c for c in outcomes if c['pnl'] <= 0]
        aborted_cycles = [c for c in outcomes if c.get('exit_reason') == 'pipeline_abort']
        busted_cycles = [c for c in outcomes if c.get('exit_reason') in ('max_level_sl', 'max_levels')]

        # Danger distribution
        danger_vals = [d[1] for d in danger] if danger else []
        danger_quartiles = _quartiles(danger_vals) if danger_vals else None

        # Danger at entry/exit for cycles
        entry_dangers = [c['danger_at_entry'] for c in outcomes if c.get('danger_at_entry') is not None]
        exit_dangers = [c['danger_at_exit'] for c in outcomes if c.get('danger_at_exit') is not None]

        # Abort PnL tracking
        abort_triggers_with_pnl = [a for a in abort_triggers if a.get('pnl_at_abort') is not None]
        aborts_at_loss = sum(1 for a in abort_triggers_with_pnl if a['pnl_at_abort'] < 0)
        aborts_at_profit = sum(1 for a in abort_triggers_with_pnl if a['pnl_at_abort'] >= 0)

        # Protection estimates
        avg_wrong_allow_loss = abs(_avg([g['outcome_pnl'] for g in wrong_allows]) or 0) if wrong_allows else 0
        est_pnl_saved_blocks = round(self.entries_blocked * avg_wrong_allow_loss, 4) if self.entries_blocked > 0 else 0
        pnl_saved_aborts = round(
            sum(abs(a['pnl_at_abort']) for a in abort_triggers_with_pnl if a['pnl_at_abort'] < 0), 4
        )
        total_protection = round(est_pnl_saved_blocks + pnl_saved_aborts, 4)

        return {
            # ── Summary counters ──
            'total_gate_checks': self.total_gate_checks,
            'entries_blocked': self.entries_blocked,
            'entries_allowed': self.entries_allowed,
            'block_rate': _pct(self.entries_blocked, self.total_gate_checks),
            'abort_checks': self.abort_checks,
            'aborts_triggered': self.aborts_triggered,
            'abort_rate': _pct(self.aborts_triggered, self.abort_checks),
            'cycles_completed': self.cycles_completed,

            # ── Gate analytics ──
            'gate': {
                'correct_allows': gate_correct_allows,
                'wrong_allows': gate_wrong_allows,
                'allow_accuracy': _pct(gate_correct_allows, gate_correct_allows + gate_wrong_allows),
                'avg_danger_at_block': _r(avg_danger_at_block),
                'avg_danger_at_allow': _r(avg_danger_at_allow),
                'pnl_of_allowed': round(sum(g['outcome_pnl'] for g in allowed_with_outcome), 4) if allowed_with_outcome else 0,
                # Decision quality
                'wrong_allow_avg_danger': _r(_avg([g['danger'] for g in wrong_allows])),
                'correct_allow_avg_danger': _r(_avg([g['danger'] for g in correct_allows])),
                'wrong_allow_total_loss': round(sum(g['outcome_pnl'] for g in wrong_allows), 4) if wrong_allows else 0,
                'blocks_above_avg_danger': sum(1 for g in blocked if g['danger'] > (avg_danger_at_allow or 0.5)),
                'est_pnl_saved_by_blocks': est_pnl_saved_blocks,
            },

            # ── Abort analytics ──
            'abort': {
                'total_triggers': len(abort_triggers),
                'total_continues': len(abort_continues),
                'avg_level_at_abort': _r(_avg([a['level'] for a in abort_triggers])),
                'avg_danger_at_abort': _r(_avg([a['danger'] for a in abort_triggers])),
                'avg_danger_at_continue': _r(_avg([a['danger'] for a in abort_continues])),
                'q_margin_at_abort': _r(_avg([a.get('q_margin', 0) for a in abort_triggers])),
                # Decision quality
                'avg_pnl_at_abort': _r(_avg([a['pnl_at_abort'] for a in abort_triggers_with_pnl])),
                'aborts_at_loss': aborts_at_loss,
                'aborts_at_profit': aborts_at_profit,
                'aborted_cycle_avg_pnl': _r(_avg([c['pnl'] for c in aborted_cycles])),
                'aborted_cycle_total_pnl': round(sum(c['pnl'] for c in aborted_cycles), 4) if aborted_cycles else 0,
                'pnl_saved_by_aborts': pnl_saved_aborts,
                # Learning progression
                'q_progression': self.q_value_progression[-100:],
            },

            # ── Cycle analytics ──
            'cycles': {
                'total': len(outcomes),
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': _pct(len(wins), len(outcomes)),
                'aborted': len(aborted_cycles),
                'busted': len(busted_cycles),
                'avg_pnl': _r(_avg([c['pnl'] for c in outcomes])),
                'avg_win': _r(_avg([c['pnl'] for c in wins])),
                'avg_loss': _r(_avg([c['pnl'] for c in losses])),
                'avg_level': _r(_avg([c['level'] for c in outcomes])),
                'avg_duration': _r(_avg([c.get('duration_bars', 0) for c in outcomes])),
                'pnl_by_exit': _group_pnl(outcomes),
            },

            # ── Danger analytics ──
            'danger': {
                'current': danger_vals[-1] if danger_vals else None,
                'mean': _r(_avg(danger_vals)),
                'std': _r(_std(danger_vals)),
                'quartiles': danger_quartiles,
                'avg_at_entry': _r(_avg(entry_dangers)),
                'avg_at_exit': _r(_avg(exit_dangers)),
                'high_danger_pct': _pct(
                    sum(1 for d in danger_vals if d > 0.7), len(danger_vals)),
            },

            # ── Risk intelligence ──
            'risk_intel': {
                'danger_buckets': _danger_outcome_buckets(outcomes),
                'high_danger_entries': sum(1 for c in outcomes if (c.get('danger_at_entry') or 0) > 0.7),
                'high_danger_entry_winrate': _pct(
                    sum(1 for c in outcomes if (c.get('danger_at_entry') or 0) > 0.7 and c['pnl'] > 0),
                    sum(1 for c in outcomes if (c.get('danger_at_entry') or 0) > 0.7)),
                'high_danger_entry_pnl': round(sum(c['pnl'] for c in outcomes if (c.get('danger_at_entry') or 0) > 0.7), 4),
                'avg_danger_before_bust': _r(_avg([c.get('danger_at_entry') for c in busted_cycles if c.get('danger_at_entry') is not None])),
                'avg_max_danger_during_bust': _r(_avg([c.get('max_danger') for c in busted_cycles if c.get('max_danger') is not None])),
                'peak_danger_window': _find_peak_danger_window(danger),
            },

            # ── Protection score ──
            'protection': {
                'est_pnl_saved_by_blocks': est_pnl_saved_blocks,
                'pnl_saved_by_aborts': pnl_saved_aborts,
                'total_protection_value': total_protection,
                'aborts_before_max_level': sum(1 for c in aborted_cycles if c.get('level', 0) >= 3),
            },

            # ── Per-level performance ──
            'level_performance': _level_performance(outcomes),

            # ── Config ──
            'config': self.config_snapshot,

            # ── Size adjustment analytics ──
            'size_adjustment': {
                'total': self.total_size_adjustments,
                'avg_scale': _r(_avg([a[2] / a[1] for a in self.size_adjustments if a[1] > 0])),
                'entries_scaled': sum(1 for a in self.size_adjustments if a[1] != a[2]),
                'entries_cancelled': sum(1 for a in self.size_adjustments if a[2] <= 0),
            } if self.total_size_adjustments > 0 else None,

            # ── Exit suggestion analytics ──
            'exit_suggestions': {
                'total': self.total_exit_suggestions,
                'by_action': _group_count([s[1] for s in self.exit_suggestions]),
            } if self.total_exit_suggestions > 0 else None,

            # ── Order filter analytics ──
            'order_filter': {
                'total_filtered': self.orders_filtered,
                'cancelled': self.orders_cancelled_by_filter,
                'cancel_rate': _pct(self.orders_cancelled_by_filter, self.orders_filtered),
            } if self.orders_filtered > 0 else None,

            # ── Raw data for charts/tables ──
            'gate_decisions': gate_decs[-200:],  # last 200 for UI
            'abort_decisions': abort_decs[-200:],
            'cycle_outcomes': outcomes,
            'danger_scores': danger,
            'gate_threshold_series': self.gate_threshold_series,
        }


# ── Helpers ──

def _r(v):
    """Round or None."""
    return round(v, 4) if v is not None else None

def _pct(num, den):
    return round(num / den, 4) if den > 0 else 0.0

def _avg(vals):
    return sum(vals) / len(vals) if vals else None

def _std(vals):
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))

def _quartiles(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return {
        'min': round(s[0], 4),
        'p25': round(s[n // 4], 4),
        'p50': round(s[n // 2], 4),
        'p75': round(s[3 * n // 4], 4),
        'max': round(s[-1], 4),
    }

def _group_pnl(outcomes):
    """Group total PnL by exit_reason."""
    groups = {}
    for c in outcomes:
        reason = c.get('exit_reason', 'unknown')
        if reason not in groups:
            groups[reason] = {'count': 0, 'pnl': 0.0}
        groups[reason]['count'] += 1
        groups[reason]['pnl'] = round(groups[reason]['pnl'] + c['pnl'], 4)
    return groups

def _group_count(items):
    """Count occurrences of each item."""
    counts = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts

def _danger_outcome_buckets(outcomes):
    """Bucket cycles by danger_at_entry into 5 bins, compute win_rate and avg_pnl per bucket."""
    edges = [0.3, 0.5, 0.7, 0.85]
    labels = ['very_low', 'low', 'medium', 'high', 'extreme']
    buckets = {l: {'count': 0, 'wins': 0, 'pnl': 0.0} for l in labels}
    for c in outcomes:
        d = c.get('danger_at_entry')
        if d is None:
            continue
        idx = sum(1 for e in edges if d >= e)
        label = labels[idx]
        buckets[label]['count'] += 1
        buckets[label]['pnl'] += c['pnl']
        if c['pnl'] > 0:
            buckets[label]['wins'] += 1
    for b in buckets.values():
        b['pnl'] = round(b['pnl'], 4)
        b['win_rate'] = _pct(b['wins'], b['count'])
    return buckets

def _level_performance(outcomes):
    """Performance breakdown by max level reached in cycle."""
    levels = {}
    for c in outcomes:
        lv = c.get('level', 0)
        if lv not in levels:
            levels[lv] = {'count': 0, 'wins': 0, 'pnl': 0.0, 'avg_danger': []}
        levels[lv]['count'] += 1
        levels[lv]['pnl'] += c['pnl']
        if c['pnl'] > 0:
            levels[lv]['wins'] += 1
        if c.get('danger_at_entry') is not None:
            levels[lv]['avg_danger'].append(c['danger_at_entry'])
    for lv, data in levels.items():
        data['pnl'] = round(data['pnl'], 4)
        data['win_rate'] = _pct(data['wins'], data['count'])
        data['avg_danger'] = _r(_avg(data['avg_danger']))
    return dict(sorted(levels.items()))

def _find_peak_danger_window(danger_scores, window=50):
    """Find the window of N consecutive danger scores with highest average."""
    if len(danger_scores) < window:
        return None
    vals = [d[1] for d in danger_scores]
    best_avg = 0
    best_start_ts = None
    best_end_ts = None
    running_sum = sum(vals[:window])
    avg = running_sum / window
    if avg > best_avg:
        best_avg = avg
        best_start_ts = danger_scores[0][0]
        best_end_ts = danger_scores[window - 1][0]
    for i in range(window, len(vals)):
        running_sum += vals[i] - vals[i - window]
        avg = running_sum / window
        if avg > best_avg:
            best_avg = avg
            best_start_ts = danger_scores[i - window + 1][0]
            best_end_ts = danger_scores[i][0]
    return {'avg_danger': round(best_avg, 4), 'start_ts': best_start_ts, 'end_ts': best_end_ts}
