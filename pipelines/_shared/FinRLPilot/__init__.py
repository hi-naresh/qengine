"""
FinRLPilot — Deep-Reinforcement-Learning pipeline (PPO) for qengine.

Based on:
  Liu et al. (2020). FinRL: A Deep Reinforcement Learning Library for
  Automated Stock Trading in Quantitative Finance. arXiv:2011.09607.
  https://github.com/AI4Finance-Foundation/FinRL

Also cites:
  FinRL Contests 2025 (arXiv:2504.02281).

Design (adapted for this research codebase):
  State   : 10-dim feature vector from the shared FeaturePool
  Action  : discrete index into a 4-entry parameter preset table
            (conservative / moderate / aggressive / tight-TP)
  Reward  : cycle P&L at on_cycle_end, optionally penalised by observed
            drawdown during the cycle
  Policy  : PPO with a small MLP (2×64). Falls back to a tabular Q-learner
            when no deep-learning library is installed.

This pipeline represents the non-evolutionary ML alternative to IslandPilot:
"what if you replace evolution with RL, and regimes with policy learning?"
"""
from __future__ import annotations

import os
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

from qengine.framework.base import Pipeline

from .config import DEFAULT_CONFIG, DEFAULT_STATE_FEATURES, merge_config
from .presets import PRESETS, PRESET_NAMES, TUNABLE_GROUPS, apply_preset_to_hp
from .ppo_agent import BACKEND, HAS_SB3, HAS_TORCH, build_policy  # noqa: F401


_DIR = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_DIR, 'models')

# Cap lookback so indicator cost is O(1) per candle regardless of history.
_MAX_LOOKBACK = 300


def _feature_pool():
    """Lazy import — avoids a hard dep on indicators at import time."""
    from pipelines._shared.components.feature_selector import FeaturePool
    return FeaturePool()


class FinRLPilot(Pipeline):
    """PPO over a discrete parameter-preset action space."""

    name = 'FinRLPilot'

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, config: Optional[dict] = None):
        self.cfg = merge_config(config or {})
        if self.cfg.get('models_dir') is None:
            self.cfg['models_dir'] = _MODELS_DIR
        # Keep n_actions in sync with the preset table
        self.cfg['n_actions'] = len(PRESETS)

        # Components
        self.feature_pool = _feature_pool()
        self._feature_names: List[str] = self.feature_pool.feature_names
        self._selected_feature_idx: List[int] = self._resolve_state_features()

        # Policy
        self.policy = build_policy(self.cfg)
        self._tried_load = False

        # Runtime state
        self._candle_count: int = 0
        self._cycle_count: int = 0
        self._applied_counts: Counter = Counter()
        self._cycle_hp_log: List[Dict[str, Any]] = []
        self._reward_timeseries: List[List[float]] = []  # [ts, reward, preset_idx]
        # Full training transitions — ts, state_vector, action, reward.
        # Used by the offline training script to replay real (state, action,
        # reward) tuples into a persistent policy for fitting. Only populated
        # in train mode to avoid bloating eval-mode stats payloads.
        self._transitions: List[Dict[str, Any]] = []

        self._state_at_entry: Optional[np.ndarray] = None
        self._action_at_entry: Optional[int] = None
        self._current_preset_idx: Optional[int] = None
        self._current_preset_applied: Dict[str, Any] = {}
        self._last_recorded_session: Optional[int] = None
        self._cycle_start_index: Optional[int] = None
        self._cycle_start_equity: Optional[float] = None
        self._cycle_min_equity: Optional[float] = None

        # Strategy HP spec (discovered on first on_before())
        self._hp_spec: Dict[str, dict] = {}

        # Try loading pre-trained weights
        self._load_pretrained()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_state_features(self) -> List[int]:
        """Return indices into FeaturePool for the configured state features.

        Features that don't exist are silently skipped; we pad with -1 sentinels
        at compute time so the state vector always has length state_dim.
        """
        wanted = self.cfg.get('state_features') or DEFAULT_STATE_FEATURES
        idx = []
        for name in wanted:
            if name in self._feature_names:
                idx.append(self._feature_names.index(name))
            else:
                idx.append(-1)  # sentinel — will produce a zero in state vec
        return idx

    def _load_pretrained(self) -> None:
        """Load pre-trained policy weights from models/.

        Extension-aware: the file on disk determines the required backend.
        If the active backend can't load the file, we rebuild the policy with
        the correct backend (via build_policy with a backend_override) and
        retry. This prevents the silent-random-policy failure where SB3 is
        available but only a torch/tabular weight file exists on disk (or
        vice versa).
        """
        import logging
        if self._tried_load:
            return
        self._tried_load = True

        # Ordered by priority: torch (most capable) > sb3 > tabular.
        # Each entry = (filename, required_backend).
        candidates = [
            ('policy.pt', 'torch'),
            ('policy.zip', 'sb3'),
            ('policy_tabular.npz', 'tabular'),
        ]
        for fname, required_backend in candidates:
            path = os.path.join(_MODELS_DIR, fname)
            if not os.path.exists(path):
                continue

            # If active backend doesn't match the file, rebuild the policy
            # with the right backend before attempting the load.
            if self.policy.kind != required_backend:
                try:
                    cfg = dict(self.cfg)
                    cfg['backend_override'] = required_backend
                    self.policy = build_policy(cfg)
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        "FinRLPilot: cannot rebuild policy with backend=%s (%s); "
                        "skipping %s", required_backend, e, fname,
                    )
                    continue

            try:
                self.policy.load(path)
                return
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "FinRLPilot: failed to load %s into %s backend: %s",
                    fname, self.policy.kind, e,
                )
                continue

        logging.getLogger(__name__).warning(
            "FinRLPilot: no pre-trained policy found in %s — running with "
            "untrained weights (actions will be random/initialised).",
            _MODELS_DIR,
        )

    def _compute_state(self, strategy) -> Optional[np.ndarray]:
        """Compute the 10-dim state vector from the configured FeaturePool features."""
        candles = getattr(strategy, 'candles', None)
        if candles is None or len(candles) < self.cfg['warmup']:
            return None

        tail = candles[-_MAX_LOOKBACK:] if len(candles) > _MAX_LOOKBACK else candles
        try:
            matrix = self.feature_pool.compute(tail)
        except Exception:
            return None
        if matrix is None or len(matrix) == 0:
            return None

        row = matrix[-1]
        state_dim = int(self.cfg.get('state_dim', 10))
        state = np.zeros(state_dim, dtype=np.float64)
        for i, fi in enumerate(self._selected_feature_idx[:state_dim]):
            if fi < 0:
                continue
            val = row[fi]
            state[i] = 0.0 if (val is None or not np.isfinite(val)) else float(val)
        return state

    def _position_is_open(self, strategy) -> bool:
        try:
            if hasattr(strategy, 'position') and hasattr(strategy.position, 'is_open'):
                return bool(strategy.position.is_open)
        except Exception:
            pass
        try:
            v = getattr(strategy, 'vars', {})
            return bool(v.get('cycle_active', False))
        except Exception:
            return False

    def _equity(self, strategy) -> Optional[float]:
        for path in (('portfolio', 'equity'), ('balance',)):
            obj = strategy
            ok = True
            for part in path:
                if not hasattr(obj, part):
                    ok = False
                    break
                obj = getattr(obj, part)
            if ok:
                try:
                    return float(obj)
                except Exception:
                    continue
        return None

    # ------------------------------------------------------------------
    # Pipeline hooks
    # ------------------------------------------------------------------

    def on_before(self, strategy) -> None:
        """Compute features → policy chooses a preset → apply to strategy.hp.

        Preset is only (re)applied when no position is open — we never change
        HP mid-cycle.
        """
        self._candle_count += 1

        # Discover hp spec once
        if not self._hp_spec and hasattr(strategy, 'hyperparameters'):
            try:
                hps = strategy.hyperparameters()
                self._hp_spec = {h['name']: h for h in hps if isinstance(h, dict) and 'name' in h}
            except Exception:
                self._hp_spec = {}

        if self._candle_count < self.cfg['warmup']:
            return

        state = self._compute_state(strategy)
        if state is None:
            return

        # Only change preset between cycles
        if self._position_is_open(strategy):
            # Track floating drawdown for reward shaping
            eq = self._equity(strategy)
            if eq is not None:
                if self._cycle_min_equity is None or eq < self._cycle_min_equity:
                    self._cycle_min_equity = eq
            return

        # Forward pass → action
        action = self.policy.act(state)
        self._state_at_entry = state
        self._action_at_entry = int(action)
        self._current_preset_idx = int(action)

        # Apply preset to HP (only tune General / Grid/Hedge / Take Profit)
        applied = apply_preset_to_hp(strategy, int(action), self._hp_spec)
        self._current_preset_applied = applied
        self._applied_counts[int(action)] += 1

    def gate_entry(self, strategy) -> bool:
        """Allow entries after warmup. Never vetoes — the policy expresses
        preference via its choice of preset."""
        return self._candle_count >= self.cfg['warmup']

    def on_open_position(self, strategy) -> None:
        """Record entry state for per-cycle drawdown tracking."""
        try:
            self._cycle_start_index = int(getattr(strategy, 'index', 0))
        except Exception:
            self._cycle_start_index = None
        self._cycle_start_equity = self._equity(strategy)
        self._cycle_min_equity = self._cycle_start_equity

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Record transition (state, action, reward=pnl - dd_penalty).

        Dedupes via strategy session_number (same guard as IslandPilot/GridPilot)
        to avoid the CFD double-fire."""
        sn = getattr(strategy, 'vars', {}).get('session_number') if strategy else None
        if sn is not None and sn == self._last_recorded_session:
            return
        self._last_recorded_session = sn

        self._cycle_count += 1

        # Drawdown penalty — observed intra-cycle equity drop
        dd_penalty = 0.0
        if (self._cycle_start_equity is not None
                and self._cycle_min_equity is not None
                and self._cycle_start_equity > 0):
            dd = max(0.0, self._cycle_start_equity - self._cycle_min_equity)
            dd_frac = dd / max(1e-9, self._cycle_start_equity)
            coef = float(self.cfg.get('reward', {}).get('drawdown_penalty_coef', 0.1))
            dd_penalty = coef * dd_frac * abs(self._cycle_start_equity)

        reward = float(pnl) - float(dd_penalty)

        if self._state_at_entry is not None and self._action_at_entry is not None:
            self.policy.record(
                state=self._state_at_entry,
                action=int(self._action_at_entry),
                reward=reward,
                done=True,
            )

        # Log per-cycle HP for the UI
        try:
            ts = float(strategy.current_candle[0]) if hasattr(strategy, 'current_candle') else 0.0
        except Exception:
            ts = 0.0
        self._reward_timeseries.append([
            ts,
            float(pnl),
            int(self._action_at_entry) if self._action_at_entry is not None else -1,
        ])

        # Persist full transition for offline-RL replay. Only in train mode —
        # otherwise this balloons eval stats. State vector is serialised as a
        # plain list so the JSON-backed pipeline_stats payload stays clean.
        if self.cfg.get('mode') == 'train' and self._state_at_entry is not None \
                and self._action_at_entry is not None:
            self._transitions.append({
                'ts': ts,
                'state': [float(x) for x in self._state_at_entry.tolist()],
                'action': int(self._action_at_entry),
                'reward': float(reward),
                'pnl': float(pnl),
            })
        self._cycle_hp_log.append({
            'cycle': sn if sn is not None else self._cycle_count,
            'preset_idx': self._action_at_entry,
            'preset_name': (
                PRESET_NAMES[self._action_at_entry]
                if self._action_at_entry is not None
                and 0 <= self._action_at_entry < len(PRESET_NAMES)
                else None
            ),
            'pnl': round(float(pnl), 4),
            'reward': round(float(reward), 4),
            'dd_penalty': round(float(dd_penalty), 4),
            'hp': dict(self._current_preset_applied),
        })

        # Trigger learning update every N cycles (train mode only)
        update_every = int(self.cfg.get('update_every_cycles', 32))
        if self.cfg.get('mode') == 'train' and update_every > 0:
            if self._cycle_count % update_every == 0:
                self.policy.update()

        # Reset cycle trackers
        self._state_at_entry = None
        self._action_at_entry = None
        self._current_preset_applied = {}
        self._cycle_start_equity = None
        self._cycle_min_equity = None
        self._cycle_start_index = None

    # ------------------------------------------------------------------
    # Stats & UI
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        policy_stats = self.policy.stats()
        action_counts_named = {
            PRESET_NAMES[a] if 0 <= a < len(PRESET_NAMES) else f'action_{a}': int(c)
            for a, c in self._applied_counts.items()
        }
        stats: Dict[str, Any] = {
            'backend': policy_stats.get('backend'),
            'mode': self.cfg.get('mode'),
            'n_actions': self.cfg['n_actions'],
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'current_action': self._current_preset_idx,
            'current_preset': (
                PRESET_NAMES[self._current_preset_idx]
                if self._current_preset_idx is not None
                and 0 <= self._current_preset_idx < len(PRESET_NAMES)
                else None
            ),
            'action_counts': {int(k): int(v) for k, v in self._applied_counts.items()},
            'action_counts_named': action_counts_named,
            'mean_reward': policy_stats.get('mean_reward_all', 0.0),
            'mean_reward_100': policy_stats.get('mean_reward_100', 0.0),
            'reward_std_100': policy_stats.get('reward_std_100', 0.0),
            'total_steps': policy_stats.get('total_steps', 0),
            'total_updates': policy_stats.get('total_updates', 0),
            'states_visited': policy_stats.get('states_visited', 0),
            'coverage': policy_stats.get('coverage', 0),
            'presets': [dict(p) for p in PRESETS],
            # Keep the full history available to downstream training / logging
            # callers; UI code can subscript as needed.
            'cycle_hp_log': self._cycle_hp_log,
            'reward_timeseries': self._reward_timeseries,
            'transitions': self._transitions,  # train mode only; consumed by 55_*_train.py
            'policy': policy_stats,
        }
        stats['_ui'] = self.ui_metadata()
        return stats

    def ui_metadata(self) -> dict:
        return {
            'badges': [
                {'label': self.name, 'color': 'brand'},
                {'label': f'backend: {BACKEND}',
                 'color': 'green' if BACKEND in ('sb3', 'torch') else 'amber'},
                {'label': f'preset: {PRESET_NAMES[self._current_preset_idx]}'
                 if self._current_preset_idx is not None
                 and 0 <= self._current_preset_idx < len(PRESET_NAMES)
                 else 'preset: ?',
                 'color': 'brand' if self._current_preset_idx is not None else 'surface'},
                {'label': f'mode: {self.cfg.get("mode", "eval")}', 'color': 'surface'},
            ],
            'metric_cards': [
                {'label': 'Current Preset', 'key': 'current_preset', 'format': 'text',
                 'icon': 'chart',
                 'tooltip': 'Preset currently applied to the strategy'},
                {'label': 'Action Distribution', 'key': 'action_counts_named',
                 'format': 'dict', 'icon': 'chart',
                 'tooltip': 'Times each preset was selected'},
                {'label': 'Mean Reward (100)', 'key': 'mean_reward_100', 'format': 'dec4',
                 'icon': 'chart',
                 'tooltip': 'Rolling mean cycle reward over last 100 cycles'},
                {'label': 'Cycles', 'key': 'cycle_count', 'format': 'int',
                 'icon': 'chart',
                 'tooltip': 'Total completed trading cycles'},
                {'label': 'Policy Updates', 'key': 'total_updates', 'format': 'int',
                 'icon': 'chart',
                 'tooltip': 'Number of policy gradient / Q-learning updates applied'},
            ],
            'sections': [
                {
                    'type': 'bar_breakdown',
                    'title': 'Action Frequency (presets chosen)',
                    'data_key': 'action_counts_named',
                    'empty_message': 'Policy has not selected any actions yet.',
                    'label_prefix': '',
                    'mode': 'count_only',
                },
                {
                    'type': 'line_chart',
                    'title': 'Reward per Cycle',
                    'subtitle': 'Cycle P&L reward fed to the policy',
                    'data_key': 'reward_timeseries',
                    'show_if': 'reward_timeseries',
                    'empty_message': 'No cycles completed yet.',
                    'series': [
                        {'index': 1, 'label': 'Reward', 'color': '#818cf8', 'width': 2},
                    ],
                    'x_label': 'Cycle',
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Policy Backend',
                    'data_key': 'policy',
                    'show_if': 'policy',
                    'auto_items': True,
                    'grid': 'full',
                },
            ],
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_state(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        if self.policy.kind == 'sb3':
            self.policy.save(os.path.join(path, 'policy.zip'))
        elif self.policy.kind == 'torch':
            self.policy.save(os.path.join(path, 'policy.pt'))
        else:
            self.policy.save(os.path.join(path, 'policy_tabular.npz'))

        import json
        runtime = {
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'applied_counts': dict(self._applied_counts),
            'current_preset_idx': self._current_preset_idx,
        }
        with open(os.path.join(path, 'runtime.json'), 'w') as f:
            json.dump(runtime, f, indent=2)

    def load_state(self, path: str) -> None:
        import json
        for fname in ('policy.zip', 'policy.pt', 'policy_tabular.npz'):
            full = os.path.join(path, fname)
            if os.path.exists(full):
                try:
                    self.policy.load(full)
                    break
                except Exception:
                    continue

        runtime_path = os.path.join(path, 'runtime.json')
        if os.path.exists(runtime_path):
            with open(runtime_path) as f:
                runtime = json.load(f)
            self._candle_count = int(runtime.get('candle_count', 0))
            self._cycle_count = int(runtime.get('cycle_count', 0))
            self._applied_counts = Counter({int(k): int(v) for k, v in runtime.get('applied_counts', {}).items()})
            self._current_preset_idx = runtime.get('current_preset_idx')

    # ------------------------------------------------------------------
    # Classmethods
    # ------------------------------------------------------------------

    @classmethod
    def default_config(cls) -> dict:
        return merge_config({})

    @classmethod
    def architecture(cls) -> dict:
        # Detect weights present in the shipped models dir
        models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
        has_weights = any(
            os.path.exists(os.path.join(models_dir, f))
            for f in ('policy.zip', 'policy.pt', 'policy_tabular.npz')
        )

        return {
            'name': 'FinRLPilot',
            'summary': 'PPO policy over a discrete parameter-preset action space. '
                       'Represents the non-evolutionary ML alternative to IslandPilot: '
                       'what if you replace evolution with RL and regimes with policy learning?',
            'designed_for': ['Martingale', 'Grid strategies', 'SurefireHedge variants'],
            'research_basis': 'Liu et al. (2020) — FinRL: A Deep RL Library for '
                              'Automated Stock Trading (arXiv:2011.09607). '
                              'FinRL Contests 2025 (arXiv:2504.02281).',
            'requires_training': True,
            'training_status': 'trained' if has_weights else 'untrained',
            'training_description': 'Trains a PPO policy on historical cycles. State = 10 '
                                    'market features from the shared FeaturePool, action = '
                                    'discrete index into a 4-preset HP table, reward = cycle '
                                    'P&L (with drawdown penalty).',
            'training_steps': [
                'Load EUR-USD 30m candles from the configured training window',
                'Initialise a policy (SB3 PPO, Torch PPO, or tabular Q-learner) based on '
                'available dependencies',
                'Run a random-policy rollout to collect (state, action, reward) trajectories '
                'across full backtests',
                'Fine-tune / warm-start the policy on the collected offline buffer',
                'Save policy weights to pipelines/_shared/FinRLPilot/models/',
            ],
            'layers': [
                {
                    'name': 'FeaturePool',
                    'order': 1,
                    'type': 'feature_extractor',
                    'hook': 'on_before()',
                    'description': 'Shared feature extractor (same as IslandPilot). '
                                   'Emits a fixed set of volatility, trend, chop, momentum, '
                                   'and structure features.',
                    'output': f'{len(DEFAULT_STATE_FEATURES)}-dim state vector per candle',
                    'selected_features': DEFAULT_STATE_FEATURES,
                },
                {
                    'name': 'PPOPolicy',
                    'order': 2,
                    'type': 'policy',
                    'hook': 'on_before() → act()',
                    'description': 'Small MLP (2x64) trained with PPO (clip=0.2). '
                                   'Falls back to a tabular Q-learner if SB3 / PyTorch '
                                   'are not installed on the host.',
                    'algorithm': 'PPO (Schulman et al. 2017) as implemented in FinRL. '
                                 'Fallback: tabular Q-learning with epsilon-greedy '
                                 'exploration over a discretised state grid.',
                    'state_space': {
                        'dim': len(DEFAULT_STATE_FEATURES),
                        'features': DEFAULT_STATE_FEATURES,
                    },
                    'action_space': {
                        'type': 'Discrete',
                        'n': len(PRESET_NAMES),
                        'presets': PRESET_NAMES,
                    },
                    'config_keys': {
                        'lr': 'Adam learning rate (default: 3e-4)',
                        'gamma': 'Discount factor (default: 0.99)',
                        'clip_eps': 'PPO clip parameter (default: 0.2)',
                        'n_steps': 'Steps per rollout (default: 256)',
                        'batch_size': 'Minibatch size (default: 64)',
                    },
                    'current_backend': BACKEND,
                    'backends_available': {
                        'stable_baselines3': HAS_SB3,
                        'torch': HAS_TORCH,
                        'tabular': True,  # always available
                    },
                },
                {
                    'name': 'PresetTable',
                    'order': 3,
                    'type': 'action_decoder',
                    'hook': 'on_before() → apply_preset_to_hp()',
                    'description': 'Discrete action → concrete HP dict applied to '
                                   'strategy.hp. Only tunes General / Grid-Hedge / '
                                   'Take-Profit parameter groups.',
                    'presets': [dict(p) for p in PRESETS],
                    'tunable_groups': sorted(TUNABLE_GROUPS),
                    'safety': 'HP changes happen only when no position is open '
                              '(never mid-cycle).',
                },
            ],
            'lifecycle': [
                {'hook': 'on_before()', 'description': 'Compute 10-dim state → policy selects '
                                                      'preset index → apply to strategy.hp '
                                                      '(between cycles only)'},
                {'hook': 'gate_entry()', 'description': 'Passes through after warmup — the '
                                                        'policy expresses preference via its '
                                                        'choice of preset, not via vetoes'},
                {'hook': 'on_open_position()', 'description': 'Snapshots start equity for '
                                                              'drawdown reward shaping'},
                {'hook': 'on_cycle_end()', 'description': 'Store (state, action, pnl) in the '
                                                          'policy buffer. In train mode, '
                                                          'trigger PPO/Q update every N cycles'},
            ],
            'composition_rules': {
                'gate_entry': 'AND — all pipelines must allow (any veto blocks)',
                'adjust_size': 'Multiplicative chain (FinRLPilot does not scale)',
                'suggest_exit': 'Most aggressive action wins (FinRLPilot does not suggest exits)',
                'filter_order': 'Sequential chain — any None cancels the order',
            },
        }
