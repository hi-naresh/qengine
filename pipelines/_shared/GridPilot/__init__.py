"""
GridPilot Pipeline — Danger Scoring + Entry Gate + Q-Learning Abort

The first concrete pipeline for qengine. Designed for grid/martingale strategies
(SurefireV2 etc.) but works with any strategy.

Layers:
  1. DangerScorer: real-time market risk assessment [0, 1]
  2. EntryGate: blocks entries when danger > percentile threshold
  3. QAbort: Q-learning agent that decides whether to abort mid-cycle

All layers are independently toggleable via config.

Phase2 Research Results (20yr EUR-USD, 60,370 cycles):
  - Busts are IID random (HMM regime gate FAILED, p=0.405)
  - Q-learning abort: -32% bust rate, +$1K net over 20yr
  - Danger gate: marginal (2.9% skip, 11 busts avoided)
  - Duration is #1 signal (91x bust rate separation)

Ships with pre-trained models from phase2 research:
  - models/q_table.npy: 1,625-state Q-table (449 states visited)
  - models/q_visit_count.npy: visit counts for safe policy selection
  - models/danger_scorer_params.json: normalizer means/stds from 60K cycles
"""
import os
import json
import numpy as np

from qengine.framework.base import Pipeline
from qengine.framework.stats import PipelineStats
from qengine.framework.components.danger_scorer import DangerScorer
from qengine.framework.components.q_abort import QAbort, TOTAL_STATES
from qengine.framework.components.entry_gate import EntryGate

# Path to shipped model artifacts
_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')


def _extract_features(strategy) -> dict:
    """
    Extract danger scorer features from strategy's candle data.
    Uses the strategy's indicator access (ta module) for multi-timeframe features.

    Returns dict with keys matching DangerScorer FEATURES.
    Missing features are simply omitted (scorer handles missing keys).
    """
    features = {}

    try:
        candles = strategy.candles
        if candles is None or len(candles) < 20:
            return features

        close = candles[:, 2]
        high = candles[:, 3]
        low = candles[:, 4]

        n = len(close)

        # ATR-based features from trading timeframe
        atr_14 = 0
        if n >= 14:
            # Simple ATR calculation (no dependency on ta module)
            tr_vals = []
            for i in range(1, min(n, 15)):
                tr = max(
                    high[-i] - low[-i],
                    abs(high[-i] - close[-i - 1]),
                    abs(low[-i] - close[-i - 1])
                )
                tr_vals.append(tr)

            atr_14 = sum(tr_vals) / len(tr_vals) if tr_vals else 0

            if n >= 50:
                tr_vals_50 = []
                for i in range(1, min(n, 51)):
                    tr = max(
                        high[-i] - low[-i],
                        abs(high[-i] - close[-i - 1]),
                        abs(low[-i] - close[-i - 1])
                    )
                    tr_vals_50.append(tr)
                atr_50 = sum(tr_vals_50) / len(tr_vals_50) if tr_vals_50 else 1
                features['1H_atr_ratio'] = atr_14 / max(atr_50, 1e-10)

        # Range/ATR: 20-bar range / ATR14
        if n >= 20 and atr_14 > 0:
            range_20 = max(high[-20:]) - min(low[-20:])
            features['D1_range_atr'] = range_20 / max(atr_14, 1e-10)

        # Choppiness Index (14-period) — measures trendiness
        # CI = 100 * log10(sum(TR14) / (highest_high - lowest_low)) / log10(14)
        if n >= 14:
            import math
            hh = max(high[-14:])
            ll = min(low[-14:])
            range_hl = hh - ll
            if range_hl > 0 and tr_vals:
                sum_tr = sum(tr_vals[:14])
                chop = 100 * math.log10(sum_tr / range_hl) / math.log10(14)
                features['5m_chop'] = chop
                features['15m_chop'] = chop  # approximate with same TF for now
                features['D1_chop'] = chop

        # ADX approximation (simplified: use directional movement strength)
        if n >= 14:
            plus_dm = max(0, high[-1] - high[-2]) if high[-1] > high[-2] else 0
            minus_dm = max(0, low[-2] - low[-1]) if low[-2] > low[-1] else 0
            dm_strength = abs(plus_dm - minus_dm) / max(plus_dm + minus_dm, 1e-10) * 100
            features['5m_adx'] = dm_strength

        # Hurst exponent approximation (R/S method, simplified)
        if n >= 20:
            returns = []
            for i in range(1, 21):
                if close[-i - 1] != 0:
                    returns.append(close[-i] / close[-i - 1] - 1)
            if len(returns) >= 10:
                import math
                mean_r = sum(returns) / len(returns)
                cumdev = []
                s = 0
                for r in returns:
                    s += (r - mean_r)
                    cumdev.append(s)
                R = max(cumdev) - min(cumdev) if cumdev else 0
                S = (sum((r - mean_r) ** 2 for r in returns) / len(returns)) ** 0.5
                if S > 0 and R > 0:
                    rs = R / S
                    hurst = math.log(rs) / math.log(len(returns))
                    features['5m_hurst'] = max(0.0, min(1.0, hurst))

    except Exception:
        pass

    return features


def _load_pretrained_params() -> dict:
    """Load pre-trained normalizer params from models/ directory."""
    params_path = os.path.join(_MODELS_DIR, 'danger_scorer_params.json')
    if os.path.exists(params_path):
        with open(params_path) as f:
            return json.load(f)
    return {}


class GridPilot(Pipeline):
    """
    Grid/martingale strategy protection pipeline.

    Composes DangerScorer + EntryGate + QAbort into a unified pipeline
    that scores market danger, gates risky entries, and aborts losing cycles.

    Auto-loads pre-trained models from models/ directory if available.
    Set config 'use_pretrained': False to disable.
    """

    name = 'GridPilot'

    def __init__(self, config: dict = None):
        config = config or {}
        use_pretrained = config.get('use_pretrained', True)

        # Scorer config — inject pre-trained normalizer params
        scorer_cfg = dict(config.get('scorer', {}))
        if use_pretrained and 'pretrained_params' not in scorer_cfg:
            params = _load_pretrained_params()
            if params:
                scorer_cfg['pretrained_params'] = params

        self.scorer = DangerScorer(scorer_cfg)
        self.gate = EntryGate(config.get('gate', {}))

        # Abort config — inject pre-trained Q-table paths
        abort_cfg = dict(config.get('abort', {}))
        if use_pretrained:
            q_path = os.path.join(_MODELS_DIR, 'q_table.npy')
            vc_path = os.path.join(_MODELS_DIR, 'q_visit_count.npy')
            if 'q_table_path' not in abort_cfg and os.path.exists(q_path):
                abort_cfg['q_table_path'] = q_path
            if 'visit_count_path' not in abort_cfg and os.path.exists(vc_path):
                abort_cfg['visit_count_path'] = vc_path

        self.abort = QAbort(abort_cfg)
        self._stats = PipelineStats()

        # Capture config snapshot for analytics display
        self._stats.config_snapshot = {
            'pipeline': 'GridPilot',
            'use_pretrained': use_pretrained,
            'scorer': config.get('scorer', {}),
            'gate': config.get('gate', {}),
            'abort': config.get('abort', {}),
        }

        # Track per-cycle state
        self._danger_at_entry = 0.5
        self._cycle_start_index = 0

    def on_before(self, strategy) -> None:
        """Update danger score from current candle features."""
        features = _extract_features(strategy)
        score = self.scorer.update(features)
        self.gate.observe(score)

        try:
            ts = strategy.current_candle[0]
        except Exception:
            ts = 0
        self._stats.record_danger(ts, score)

    def gate_entry(self, strategy) -> bool:
        """Block entry if danger exceeds percentile threshold."""
        score = self.scorer.current_score
        threshold = self.gate.current_threshold
        allowed = self.gate.should_allow(score)

        try:
            ts = self._stats.danger_scores[-1][0] if self._stats.danger_scores else 0
        except Exception:
            ts = 0
        self._stats.record_gate(ts, score, allowed, threshold=threshold)
        return allowed

    def should_abort(self, strategy) -> bool:
        """Ask Q-learner whether to abort current cycle."""
        if not self.abort.enabled:
            return False

        level = strategy.vars.get('level', 0)
        duration = strategy.index - self._cycle_start_index
        danger_now = self.scorer.current_score

        # Get Q-values before decide() for logging
        from qengine.framework.components.q_abort import _encode_state
        state_idx = _encode_state(level, duration, self._danger_at_entry, danger_now)
        q_values = [float(self.abort.q_table[state_idx, 0]),
                    float(self.abort.q_table[state_idx, 1])]

        action = self.abort.decide(
            level=level,
            duration_bars=duration,
            danger_entry=self._danger_at_entry,
            danger_now=danger_now,
        )

        # Capture floating PnL for abort quality analysis
        floating_pnl = None
        try:
            if hasattr(strategy, 'position') and strategy.position.is_open:
                floating_pnl = strategy.position.pnl
        except Exception:
            pass

        try:
            ts = strategy.current_candle[0]
        except Exception:
            ts = 0
        self._stats.record_abort(
            ts, level, danger_now, action,
            q_values=q_values,
            danger_entry=self._danger_at_entry,
            duration_bars=duration,
            pnl_at_abort=floating_pnl,
        )

        return action == 'abort'

    def on_open_position(self, strategy) -> None:
        """Track entry state for Q-learning."""
        self._danger_at_entry = self.scorer.current_score
        self._cycle_start_index = strategy.index
        self.abort.start_episode()

        try:
            ts = strategy.current_candle[0]
        except Exception:
            ts = 0
        self._stats.start_cycle(ts, self._danger_at_entry)

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Feed reward to Q-learner."""
        self.abort.end_episode(reward=pnl)

        level = strategy.vars.get('level', 0)
        duration = strategy.index - self._cycle_start_index
        # Try closed trade meta first (available before _reset_cycle runs),
        # fall back to strategy vars
        exit_reason = ''
        try:
            from qengine.store import store
            if store.closed_trades.trades:
                ct_meta = getattr(store.closed_trades.trades[-1], 'meta', None)
                if ct_meta:
                    exit_reason = ct_meta.get('exit_reason', '')
        except Exception:
            pass
        if not exit_reason:
            exit_reason = strategy.vars.get('last_cycle_outcome', '')

        try:
            ts = strategy.current_candle[0]
        except Exception:
            ts = 0

        self._stats.end_cycle(
            pnl=pnl,
            exit_reason=exit_reason,
            level=level,
            danger_at_exit=self.scorer.current_score,
            duration_bars=duration,
        )

        # Snapshot Q-learning progression for convergence chart
        if self.abort.enabled:
            nonzero = self.abort.q_table[self.abort.q_table != 0]
            if len(nonzero) > 0:
                self._stats.q_value_progression.append([
                    ts,
                    round(float(np.mean(nonzero)), 6),
                    round(float(np.std(nonzero)), 6),
                    round(int(np.sum(self.abort.visit_count > 0)) / TOTAL_STATES, 4),
                ])

    def get_stats(self) -> dict:
        stats = self._stats.to_dict()
        stats['scorer'] = self.scorer.stats
        # Merge PipelineStats analytics with component stats (don't overwrite)
        stats['gate'] = {**stats.get('gate', {}), **self.gate.stats}
        stats['abort'] = {**stats.get('abort', {}), **self.abort.stats}
        return stats

    def save_state(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        self.abort.save(path)
        with open(os.path.join(path, 'scorer_state.json'), 'w') as f:
            json.dump(self.scorer.state_dict(), f)

    def load_state(self, path: str) -> None:
        self.abort.load(path)
        scorer_path = os.path.join(path, 'scorer_state.json')
        if os.path.exists(scorer_path):
            with open(scorer_path) as f:
                self.scorer.load_state_dict(json.load(f))

    @classmethod
    def default_config(cls) -> dict:
        return {
            'use_pretrained': True,
            'scorer': {'warmup': 50},
            'gate': {'percentile': 80, 'window': 500, 'enabled': True},
            'abort': {'enabled': True, 'mode': 'eval'},
        }
