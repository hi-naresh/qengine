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


import math as _math

# Maximum lookback needed by any feature (keeps slicing bounded)
_MAX_LOOKBACK = 300


def _extract_features(strategy) -> dict:
    """
    Extract danger scorer features from strategy's candle data.
    Uses numpy vectorized ops on a fixed-size tail slice (max 300 bars)
    so cost is O(1) per candle regardless of total history length.

    Returns dict with keys matching DangerScorer FEATURES.
    Missing features are simply omitted (scorer handles missing keys).
    """
    features = {}

    try:
        candles = strategy.candles
        if candles is None or len(candles) < 50:
            return features

        # Slice only the tail we need — O(1) not O(n)
        tail = candles[-_MAX_LOOKBACK:] if len(candles) > _MAX_LOOKBACK else candles
        close = tail[:, 2]
        high = tail[:, 3]
        low = tail[:, 4]
        n = len(close)

        # ── True Range array (vectorized, computed once) ──
        # TR[i] = max(H[i]-L[i], |H[i]-C[i-1]|, |L[i]-C[i-1]|)
        hl = high[1:] - low[1:]
        hc = np.abs(high[1:] - close[:-1])
        lc = np.abs(low[1:] - close[:-1])
        tr = np.maximum(hl, np.maximum(hc, lc))  # length n-1, index 0 → bar 1

        # ── ATR at two scales ──
        atr_14 = float(tr[-14:].mean()) if len(tr) >= 14 else 0.0
        atr_50 = float(tr[-50:].mean()) if len(tr) >= 50 else 0.0

        if atr_50 > 0:
            features['1H_atr_ratio'] = atr_14 / atr_50

        # ── D1_range_atr: long-period range / ATR14 ──
        rng_period = min(288, n)
        if atr_14 > 0 and rng_period >= 20:
            features['D1_range_atr'] = float(
                high[-rng_period:].max() - low[-rng_period:].min()
            ) / atr_14

        # ── Choppiness Index at 3 scales ──
        # CI(p) = 100 * log10(sum(TR_p) / (HH_p - LL_p)) / log10(p)
        for period, key in [(14, '5m_chop'), (42, '15m_chop'), (288, 'D1_chop')]:
            if len(tr) < period:
                continue
            actual_p = min(period, len(tr))
            tr_slice = tr[-actual_p:]
            h_slice = high[-(actual_p + 1):-1] if actual_p < n - 1 else high[:-1]
            l_slice = low[-(actual_p + 1):-1] if actual_p < n - 1 else low[:-1]
            # Use the bars corresponding to TR indices
            hh = float(high[-actual_p:].max())
            ll = float(low[-actual_p:].min())
            rng = hh - ll
            if rng > 0:
                features[key] = 100 * _math.log10(float(tr_slice.sum()) / rng) / _math.log10(actual_p)

        # ── ADX (14-period, last 42 bars only) ──
        # Only iterate the tail needed for convergence, not full history
        adx_window = min(42, n - 1)  # 3x period is enough for EMA convergence
        if adx_window >= 28:
            alpha = 1.0 / 14
            pdm_s = mdm_s = tr_s = 0.0
            dx_vals = []
            start = n - adx_window
            for i in range(start, n):
                up = high[i] - high[i - 1]
                dn = low[i - 1] - low[i]
                pdm = max(up, 0.0) if up > dn else 0.0
                mdm = max(dn, 0.0) if dn > up else 0.0
                t = float(tr[i - 1]) if i - 1 < len(tr) else max(high[i] - low[i], 0.0)
                j = i - start
                if j < 14:
                    pdm_s += pdm; mdm_s += mdm; tr_s += t
                    if j == 13:
                        pdm_s /= 14; mdm_s /= 14; tr_s /= 14
                else:
                    pdm_s = pdm_s * (1 - alpha) + pdm * alpha
                    mdm_s = mdm_s * (1 - alpha) + mdm * alpha
                    tr_s = tr_s * (1 - alpha) + t * alpha
                if j >= 13 and tr_s > 0:
                    pdi = 100 * pdm_s / tr_s
                    mdi = 100 * mdm_s / tr_s
                    di_sum = pdi + mdi
                    dx_vals.append(100 * abs(pdi - mdi) / di_sum if di_sum > 0 else 0.0)
            if len(dx_vals) >= 14:
                adx = sum(dx_vals[:14]) / 14
                for dx in dx_vals[14:]:
                    adx = adx * (1 - alpha) + dx * alpha
                features['5m_adx'] = adx

        # ── Hurst exponent (R/S method, last 50 bars, vectorized) ──
        if n >= 51:
            rets = close[-50:] / close[-51:-1] - 1.0
            valid = rets[np.isfinite(rets)]
            if len(valid) >= 20:
                mean_r = float(valid.mean())
                cumdev = np.cumsum(valid - mean_r)
                R = float(cumdev.max() - cumdev.min())
                S = float(valid.std())
                if S > 0 and R > 0:
                    features['5m_hurst'] = max(0.0, min(1.0,
                        _math.log(R / S) / _math.log(len(valid))))

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

        # Scorer config — pre-trained normalizer params are disabled because
        # feature extraction now uses proper multi-period calculations that
        # produce different distributions than the old single-TF approximations.
        # The Welford normalizer will recalibrate during warmup.
        scorer_cfg = dict(config.get('scorer', {}))
        if not scorer_cfg.get('warmup'):
            scorer_cfg['warmup'] = 200  # longer warmup to build good stats

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
        """Block entry if danger exceeds percentile threshold.
        Always allows during scorer warmup (scores are neutral 0.5)."""
        if not self.scorer._seeded and self.scorer._update_count < self.scorer.warmup:
            return True  # scorer not ready yet, allow entry
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
        """Ask Q-learner whether to abort current cycle.
        Skips during scorer warmup (danger_now would be neutral 0.5)."""
        if not self.abort.enabled:
            return False
        if not self.scorer._seeded and self.scorer._update_count < self.scorer.warmup:
            return False  # scorer not calibrated yet

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
            'scorer': {'warmup': 200},
            'gate': {'percentile': 75, 'window': 500, 'enabled': True},
            'abort': {'enabled': True, 'mode': 'eval'},
        }

    @classmethod
    def architecture(cls) -> dict:
        return {
            'summary': 'Three-layer protection pipeline for grid/martingale strategies. '
                       'Scores market danger, gates risky entries, and aborts losing cycles via Q-learning.',
            'designed_for': ['Grid strategies', 'Martingale strategies', 'SurefireHedge variants'],
            'research_basis': 'Phase2 research: 20yr EUR-USD, 60,370 cycles, 103 busts analyzed',
            'requires_training': False,
            'training_status': 'ready',
            'training_description': 'Ships with pre-trained models from Phase2 research. Ready to use immediately.',
            'layers': [
                {
                    'name': 'DangerScorer',
                    'order': 1,
                    'type': 'observation',
                    'hook': 'on_before()',
                    'description': 'Real-time market risk assessment producing a danger score in [0, 1]',
                    'algorithm': 'Weighted sum of 7 z-scored features → sigmoid normalization',
                    'output': 'Single float [0, 1] per candle (0 = safe, 1 = dangerous)',
                    'features': [
                        {'key': 'D1_range_atr', 'weight': 0.30, 'inverted': True, 'description': 'Daily range / ATR — low = choppy = danger'},
                        {'key': '5m_chop', 'weight': 0.15, 'inverted': False, 'description': 'Choppiness index (5m) — high = danger'},
                        {'key': '15m_chop', 'weight': 0.15, 'inverted': False, 'description': 'Choppiness index (15m) — high = danger'},
                        {'key': 'D1_chop', 'weight': 0.10, 'inverted': False, 'description': 'Choppiness index (daily) — high = danger'},
                        {'key': '5m_adx', 'weight': 0.10, 'inverted': True, 'description': 'ADX trend strength (5m) — low = no trend = danger'},
                        {'key': '5m_hurst', 'weight': 0.10, 'inverted': True, 'description': 'Hurst exponent (5m) — near 0.5 = random walk = danger'},
                        {'key': '1H_atr_ratio', 'weight': 0.10, 'inverted': False, 'description': 'ATR 14/50 ratio (1H) — high = volatile = danger'},
                    ],
                    'normalization': 'Welford online normalizer (seeded with pre-trained stats from 60K cycles)',
                    'config_keys': {
                        'warmup': 'Candles before scoring begins (default: 50, 0 if seeded)',
                        'pretrained_params': 'Pre-computed feature means/stds (auto-loaded from models/)',
                    },
                },
                {
                    'name': 'EntryGate',
                    'order': 2,
                    'type': 'entry_control',
                    'hook': 'gate_entry()',
                    'description': 'Blocks strategy entries when danger exceeds a rolling percentile threshold',
                    'algorithm': 'Rolling window percentile threshold on danger scores',
                    'output': 'Boolean allow/block decision per entry attempt',
                    'mechanism': 'Maintains sorted rolling window → computes Nth percentile → blocks if danger > threshold',
                    'config_keys': {
                        'percentile': 'Block threshold as percentile of recent scores (default: 80 = block top 20%)',
                        'window': 'Rolling window size in candles (default: 500)',
                        'enabled': 'Toggle gate on/off (default: true)',
                    },
                    'stats_tracked': ['allow_accuracy', 'entries_blocked', 'avg_danger_at_block'],
                },
                {
                    'name': 'QAbort',
                    'order': 3,
                    'type': 'exit_control',
                    'hook': 'suggest_exit() → should_abort()',
                    'description': 'Tabular Q-learning agent that decides whether to abort a losing cycle mid-trade',
                    'algorithm': 'Tabular Q-learning with epsilon-greedy exploration',
                    'output': 'Binary action: continue or abort (force close_all)',
                    'state_space': {
                        'total_states': 1625,
                        'dimensions': [
                            {'name': 'hedge_level', 'bins': 13, 'range': '0-12'},
                            {'name': 'duration_bin', 'bins': 5, 'edges': [5, 10, 20, 50], 'unit': 'bars'},
                            {'name': 'danger_at_entry', 'bins': 5, 'edges': [0.3, 0.5, 0.7, 0.85]},
                            {'name': 'danger_now', 'bins': 5, 'edges': [0.3, 0.5, 0.7, 0.85]},
                        ],
                        'actions': {'0': 'continue', '1': 'abort'},
                    },
                    'pretrained': {
                        'states_visited': 449,
                        'prefer_abort': 45,
                        'prefer_continue': 404,
                        'bust_rate_reduction': '-32%',
                        'abort_rate': '0.16%',
                    },
                    'modes': [
                        {'name': 'eval', 'description': 'Frozen policy — no learning, no exploration (production)'},
                        {'name': 'train', 'description': 'Full RL — epsilon-greedy exploration + Q-updates (research)'},
                        {'name': 'online', 'description': 'Learns from experience, minimal exploration (legacy)'},
                    ],
                    'config_keys': {
                        'enabled': 'Toggle abort agent on/off (default: true)',
                        'mode': 'Operating mode: eval, train, or online (default: eval)',
                        'alpha': 'Learning rate (default: 0.01)',
                        'gamma': 'Discount factor (default: 0.95)',
                        'epsilon': 'Exploration rate for train mode (default: 0.15)',
                    },
                },
            ],
            'lifecycle': [
                {'hook': 'on_before()', 'description': 'DangerScorer extracts features and updates score every candle'},
                {'hook': 'gate_entry()', 'description': 'EntryGate checks danger vs threshold, blocks if too high'},
                {'hook': 'on_open_position()', 'description': 'Records danger at entry, starts Q-learning episode'},
                {'hook': 'suggest_exit()', 'description': 'QAbort evaluates state and may force close_all'},
                {'hook': 'on_cycle_end()', 'description': 'Feeds P&L reward to Q-learner, snapshots convergence'},
            ],
            'composition_rules': {
                'gate_entry': 'AND — all pipelines must allow (any veto blocks)',
                'adjust_size': 'Multiplicative chain (each scales previous output)',
                'suggest_exit': 'Most aggressive action wins (close_all > partial > tighten_sl > set_tp)',
                'filter_order': 'Sequential chain — any None cancels the order',
            },
        }
