"""
HPEngine -- Layer 3 of the ARIA pipeline.

Contextual Thompson Sampling bandits for hyperparameter selection.

For each HP group (General, Entry Signal, Grid/Hedge, etc.) and each
detected market regime, a separate bandit maintains Beta posteriors over
a set of discrete parameter configurations (arms).  On each trading
cycle the engine:

  1. Samples from Beta(alpha, beta) for every arm in every group.
  2. Picks the arm with the highest sample per group.
  3. Merges the selected arms into a single HP dict.
  4. After the cycle ends, updates posteriors with binary reward
     (1.0 if profitable, 0.0 otherwise).

Arms are constructed lazily the first time ``register_strategy()`` is
called.  The default configuration is always arm 0 so the bandit starts
from a known-good baseline.

Two injection points:
  - ``inject_structural()`` -- between cycles, sets structural HPs on
    ``strategy.hp`` (General, Entry Signal, Filters, Risk Management).
  - ``inject_order()`` -- per order, modifies TP/hedge values on an
    OrderIntent (Grid/Hedge, Take Profit).

No external libraries -- pure numpy + stdlib.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SKIP_PARAMS = {'preset'}           # meta-param, not tunable
_N_BINS = 3                         # discretization bins (default ± 1 step)

# Categorical options that produce degenerate behaviour (too few entries,
# no signal, crash-prone, or require external model).  The bandit must
# never explore these.
_EXCLUDED_OPTIONS = {
    'signal_mode': {
        'model',              # needs external ML
        'none',               # enters every bar — no signal at all
        'ema_rsi',            # compound: EMA cross + RSI OB/OS — too restrictive
        'ema_macd',           # compound: EMA + MACD — too restrictive
        'triple',             # compound: EMA + RSI + MACD — extremely restrictive
        'indicator',          # generic: depends on ind_name/ind_rule, often restricts entries
        'dual_indicator',     # compound: two indicators — very restrictive
    },
    'day_filter': {'skip_mon_fri'},            # removes 40% of trading days
    'sizing_curve': {'fixed', 'anti_martingale'},  # fixed ignores sizing_factor; anti is inverse
    'sizing_custom_sequence': {'1_2_4_8_16', '1_3_6_12_24'},  # insanely aggressive sequences
    'abort_mode': {'none'},                    # RiskShield handles abort; strategy must have one too
    'hedge_mode': {'fibonacci_levels'},        # fibonacci spacing creates stuck cycles
    'tp_mode': {'trailing', 'bucket_pct', 'risk_reward'},  # trailing chases forever; bucket_pct/risk_reward produce unreachable TPs with spread
    'vol_filter': {'atr_range', 'natr_min'},   # volatility filters stack with signals → too few entries
    'confidence_gate': {'enabled'},            # additional gate on top of ARIA gate → too few entries
    'equity_curve_filter': {'above_ema'},      # can block entries during drawdowns when recovery is needed
}

# Safety bounds: min/max overrides applied AFTER bandit selection to
# prevent configurations that blow up the account.
_SAFETY_BOUNDS = {
    'max_levels': (2, 10),          # never 0 (no hedging) or >10 (guaranteed bust)
    'base_size_value': (0.1, 3.0),  # 0.1% to 3% equity max
    'max_daily_loss_pct': (0, 5.0), # cap daily loss
    'max_exposure_pct': (0, 80),    # never above 80% margin
    'tp_value': (1.0, 30.0),       # TP must be reachable — 30 pips max for FX scalping
    'hedge_value': (3.0, 30.0),    # hedge distance 3-30 pips — not too tight, not too wide
}

# All HP groups are injected on strategy.hp between cycles.
# The strategy reads hp['hedge_value'], hp['tp_value'] etc. directly,
# so all params must be set structurally — not via OrderIntent.
_ALL_GROUPS = {'General', 'Entry Signal', 'Grid / Hedge', 'Take Profit',
               'Filters', 'Risk Management', 'Position Management'}


# ---------------------------------------------------------------------------
# BanditState
# ---------------------------------------------------------------------------

_DEFAULT_SEED = 42
_RNG = np.random.Generator(np.random.PCG64(seed=_DEFAULT_SEED))


def reset_rng(seed: int = _DEFAULT_SEED) -> None:
    """Reset module RNG to ensure deterministic backtests."""
    global _RNG
    _RNG = np.random.Generator(np.random.PCG64(seed=seed))


@dataclass
class BanditState:
    """Per-group, per-regime Thompson Sampling bandit state.

    Each arm is a dict mapping parameter names to values.  Alpha and beta
    arrays hold the Beta distribution parameters (one pair per arm).

    Initial exploration: every arm is tried once (round-robin) before
    Thompson Sampling takes over.  This prevents the default arm from
    dominating before alternatives are evaluated.
    """

    arms: list                  # list of {param_name: value, ...} dicts
    alpha: np.ndarray           # shape (n_arms,), Beta alpha per arm
    beta: np.ndarray            # shape (n_arms,), Beta beta per arm
    visit_count: np.ndarray = field(default=None)  # shape (n_arms,)

    def __post_init__(self):
        if self.visit_count is None:
            self.visit_count = np.zeros(len(self.arms), dtype=np.int32)

    def sample_best(self) -> int:
        """Select an arm: round-robin until all tried, then Thompson Sampling."""
        # Phase 1: round-robin — try each arm once
        unvisited = np.where(self.visit_count == 0)[0]
        if len(unvisited) > 0:
            return int(unvisited[_RNG.integers(len(unvisited))])
        # Phase 2: Thompson Sampling
        samples = _RNG.beta(self.alpha, self.beta)
        return int(np.argmax(samples))


# ---------------------------------------------------------------------------
# Arm construction helpers
# ---------------------------------------------------------------------------

def _local_float_values(default: float, lo: float, hi: float) -> list:
    """Return candidate float values centered around default.

    Uses multiplicative spread: [default * 0.5, default, default * 2.0],
    clipped to [lo, hi].  This keeps exploration proportional to the
    default magnitude, not the schema range.
    """
    if default <= 0 or default <= lo:
        # Default at or below min — use additive spread from lo
        delta = max((hi - lo) * 0.1, lo * 0.5) if lo > 0 else (hi - lo) * 0.1
        return sorted({round(lo, 6), round(min(hi, lo + delta), 6)})
    vals = sorted({
        round(max(lo, default * 0.5), 6),
        round(default, 6),
        round(min(hi, default * 2.0), 6),
    })
    return vals


def _local_int_values(default: int, lo: int, hi: int) -> list:
    """Return candidate int values centered around default.

    Uses ±50% of default (at least ±1), clipped to [lo, hi].
    """
    delta = max(1, default // 2)
    vals = sorted({
        max(lo, default - delta),
        default,
        min(hi, default + delta),
    })
    return vals


def _param_values(hp_def: dict) -> list:
    """Return discrete candidate values for a single HP definition.

    For categoricals: all options minus excluded ones.
    For numerics: 3 values centered around the default (×0.5 to ×2.0).
    """
    hp_type = hp_def.get('type')
    default = hp_def.get('default')
    name = hp_def.get('name', '')

    if hp_type == 'categorical':
        excluded = _EXCLUDED_OPTIONS.get(name, set())
        options = [o for o in hp_def.get('options', []) if o not in excluded]
        return options if options else [default]

    if hp_type is float or hp_type == float:
        lo = float(hp_def.get('min', 0.0))
        hi = float(hp_def.get('max', 1.0))
        d = float(default) if default is not None else (lo + hi) / 2
        return _local_float_values(d, lo, hi)

    if hp_type is int or hp_type == int:
        lo = int(hp_def.get('min', 0))
        hi = int(hp_def.get('max', 10))
        d = int(default) if default is not None else (lo + hi) // 2
        return _local_int_values(d, lo, hi)

    return [default]


def _build_arms(group_hps: list, max_arms: int, n_bins: int) -> list:
    """Build arm configurations for a group of HPs.

    Arm 0 is always the default config.  Remaining arms are local
    perturbations — each arm changes ONE param from the default,
    then additional arms combine multiple changes.  This ensures
    all arms are reasonable (no insane random combos).

    Parameters
    ----------
    group_hps : list of HP definition dicts
    max_arms : int
        Maximum number of arms to generate.
    n_bins : int
        Ignored (kept for interface compat).  Local spread is fixed.

    Returns
    -------
    list of dicts, each mapping param_name -> param_value.
    """
    if not group_hps:
        return []

    param_names = [hp['name'] for hp in group_hps]
    param_vals = [_param_values(hp) for hp in group_hps]

    # Arm 0: default configuration (with excluded options replaced)
    default_arm = {}
    for i, hp in enumerate(group_hps):
        d = hp.get('default')
        # If default is an excluded option, use first allowed value
        excluded = _EXCLUDED_OPTIONS.get(hp['name'], set())
        if d in excluded and param_vals[i]:
            d = param_vals[i][0]
        default_arm[hp['name']] = d

    arms = [default_arm]
    seen = {_arm_key(default_arm, param_names)}

    # Phase 1: ONE arm per param — guarantees every param is explored.
    # Pick the MOST DIFFERENT non-default value for each param.
    for i, hp in enumerate(group_hps):
        non_defaults = [v for v in param_vals[i] if v != default_arm[hp['name']]]
        if not non_defaults:
            continue
        # Pick the value furthest from default (for categoricals: first non-default)
        if isinstance(non_defaults[0], (int, float)):
            best = max(non_defaults, key=lambda v: abs(v - (default_arm[hp['name']] or 0)))
        else:
            best = non_defaults[0]
        arm = dict(default_arm)
        arm[hp['name']] = best
        key = _arm_key(arm, param_names)
        if key not in seen and len(arms) < max_arms:
            seen.add(key)
            arms.append(arm)

    # Phase 2: remaining single-param variations (other values)
    for i, hp in enumerate(group_hps):
        for val in param_vals[i]:
            if val == default_arm[hp['name']]:
                continue
            arm = dict(default_arm)
            arm[hp['name']] = val
            key = _arm_key(arm, param_names)
            if key not in seen and len(arms) < max_arms:
                seen.add(key)
                arms.append(arm)

    # Phase 3: multi-param combos (random local perturbations)
    attempts = 0
    while len(arms) < max_arms and attempts < max_arms * 5:
        attempts += 1
        arm = dict(default_arm)
        n_perturb = min(len(group_hps), _RNG.integers(1, 4))
        indices = _RNG.choice(len(group_hps), n_perturb, replace=False)
        for idx in indices:
            vals = param_vals[idx]
            if vals:
                arm[param_names[idx]] = vals[_RNG.integers(len(vals))]
        key = _arm_key(arm, param_names)
        if key not in seen:
            seen.add(key)
            arms.append(arm)

    return arms


def _arm_key(arm: dict, names: list) -> tuple:
    """Hashable key for an arm config (for dedup)."""
    return tuple(arm.get(n) for n in names)


# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------

def _check_dependency(hp_def: dict, full_config: dict) -> bool:
    """Return True if the HP's ``depends_on`` constraint is satisfied.

    Only checks dependencies on params present in ``full_config``.
    Missing parents are assumed satisfied — each group's bandit selects
    independently, and the parent is already set on strategy.hp.

    Preset dependencies are stripped at registration time.
    """
    deps = hp_def.get('depends_on')
    if not deps:
        return True
    for parent_name, allowed_values in deps.items():
        if parent_name not in full_config:
            continue
        if full_config[parent_name] not in allowed_values:
            return False
    return True


# ---------------------------------------------------------------------------
# HPEngine
# ---------------------------------------------------------------------------

class HPEngine:
    """ARIA Layer 3 -- contextual Thompson Sampling HP selection.

    Reads the strategy's ``hyperparameters()`` schema, groups parameters,
    and maintains separate bandits per HP group per regime.

    Parameters
    ----------
    config : dict, optional
        - ``warmup_cycles`` (int): cycles before bandit selection activates.
          Default 20.
        - ``max_arms`` (int): max arms per group. Default 30.
        - ``k_max`` (int): max discretization bins. Default 5.
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self._warmup: int = config.get('warmup_cycles', 20)
        self._max_arms: int = config.get('max_arms', 30)
        self._k_max: int = config.get('k_max', 5)

        reset_rng(config.get('seed', _DEFAULT_SEED))

        self._n_cycles: int = 0
        self._hp_schema: Optional[list] = None
        self._hp_lookup: Dict[str, dict] = {}          # name -> hp_def
        self._groups: Dict[str, list] = {}              # group_name -> [hp_defs]
        self._group_arms: Dict[str, list] = {}          # group_name -> [arm dicts]
        self._bandits: Dict[str, Dict[int, BanditState]] = {}  # group -> {regime_id -> BanditState}
        self._current_selection: Dict[str, Any] = {}    # param_name -> value
        self._selected_arms: Dict[str, int] = {}        # group_name -> arm_index
        self._last_regime_id: int = 0
        self._cycle_history: list = []                  # [{cycle, regime, arms, config}]

    # ------------------------------------------------------------------
    # Schema registration
    # ------------------------------------------------------------------

    def register_strategy(self, strategy) -> None:
        """Read HP schema from ``strategy.hyperparameters()``.

        Groups parameters by their ``group`` field.  Skips 'preset' and
        any HP without a group.  Builds arm sets for each group.

        Called once during pipeline initialization.
        """
        raw_schema = strategy.hyperparameters()
        if not raw_schema:
            logger.info('HPEngine: strategy has no hyperparameters, disabled')
            return

        self._hp_schema = raw_schema
        self._hp_lookup = {}
        self._groups = {}

        for hp_def in raw_schema:
            name = hp_def.get('name', '')
            group = hp_def.get('group')

            # Skip meta-params and ungrouped params
            if name in _SKIP_PARAMS or not group:
                continue

            # Strip preset dependency — ARIA controls all params directly
            # and forces preset='custom'. The preset-aware depends_on added
            # by the strategy's schema builder is irrelevant here.
            deps = hp_def.get('depends_on')
            if deps and 'preset' in deps:
                hp_def = dict(hp_def)  # don't mutate original
                hp_def['depends_on'] = {k: v for k, v in deps.items() if k != 'preset'}

            self._hp_lookup[name] = hp_def
            self._groups.setdefault(group, []).append(hp_def)

        # Build arms per group
        for group_name, hp_defs in self._groups.items():
            arms = _build_arms(hp_defs, self._max_arms, self._k_max)
            self._group_arms[group_name] = arms
            self._bandits[group_name] = {}

        logger.info(
            'HPEngine: registered %d groups, %d params, arms per group: %s',
            len(self._groups),
            len(self._hp_lookup),
            {g: len(a) for g, a in self._group_arms.items()},
        )

    # ------------------------------------------------------------------
    # Bandit selection
    # ------------------------------------------------------------------

    def select(self, regime_id: int) -> dict:
        """Thompson Sampling: select HP config for the current cycle.

        Parameters
        ----------
        regime_id : int
            Current market regime from MarketBrain.

        Returns
        -------
        dict mapping param_name -> selected value.  Empty dict during
        warmup or if no schema is registered.

        Note: ``_n_cycles`` counts completed cycles (incremented by
        ``update()``), not ``select()`` calls.  Warmup is based on
        completed cycle count so we don't start exploring before we
        have enough feedback.
        """
        if self._hp_schema is None or self._n_cycles < self._warmup:
            self._current_selection = {}
            self._selected_arms = {}
            return {}

        self._last_regime_id = regime_id
        merged: Dict[str, Any] = {}
        arms_chosen: Dict[str, int] = {}

        for group_name, arms in self._group_arms.items():
            if not arms:
                continue

            bandit = self._get_or_create_bandit(group_name, regime_id)
            arm_idx = bandit.sample_best()
            arms_chosen[group_name] = arm_idx

            arm_config = arms[arm_idx]
            merged.update(arm_config)

        # Filter out params whose dependencies are not satisfied
        filtered = self._filter_dependencies(merged)

        # Apply safety bounds to prevent account-blowing configs
        for param_name, (safe_lo, safe_hi) in _SAFETY_BOUNDS.items():
            if param_name in filtered:
                v = filtered[param_name]
                if isinstance(v, (int, float)):
                    filtered[param_name] = type(v)(max(safe_lo, min(safe_hi, v)))

        self._current_selection = filtered
        self._selected_arms = arms_chosen

        # Record for debugging / Observer
        self._cycle_history.append({
            'cycle': self._n_cycles,
            'regime': regime_id,
            'arms': dict(arms_chosen),
            'config': dict(filtered),
        })
        # Keep history bounded
        if len(self._cycle_history) > 5000:
            self._cycle_history = self._cycle_history[-5000:]

        logger.debug(
            'HPEngine: cycle %d, regime %d, arms=%s',
            self._n_cycles, regime_id, arms_chosen,
        )

        return filtered

    # ------------------------------------------------------------------
    # Bandit update
    # ------------------------------------------------------------------

    def update(self, profitable: bool, duration_bars: int = 0) -> None:
        """Update bandit posteriors after cycle end.

        Parameters
        ----------
        profitable : bool
            True if the cycle was profitable (PnL > 0).
        duration_bars : int
            How many bars the cycle lasted.  Long cycles (>500 bars)
            get a penalty even if profitable, because a martingale
            needs high cycle throughput.
        """
        self._n_cycles += 1  # count completed cycles, not select() calls

        if not self._selected_arms:
            return

        # Base reward: 1.0 for profit, 0.0 for loss
        reward = 1.0 if profitable else 0.0

        # Duration penalty: long cycles reduce reward even if profitable.
        # A 500-bar cycle gets ~0.5 penalty, 1000-bar gets ~0.75.
        if duration_bars > 200:
            duration_penalty = min(0.8, (duration_bars - 200) / 1000.0)
            reward = max(0.0, reward - duration_penalty)

        regime_id = self._last_regime_id

        for group_name, arm_idx in self._selected_arms.items():
            bandits_for_group = self._bandits.get(group_name, {})
            bandit = bandits_for_group.get(regime_id)
            if bandit is None:
                continue
            bandit.alpha[arm_idx] += reward
            bandit.beta[arm_idx] += (1.0 - reward)
            bandit.visit_count[arm_idx] += 1

        # Clear selection for next cycle
        self._selected_arms = {}

    # ------------------------------------------------------------------
    # Intelligent fallback — best known config from history
    # ------------------------------------------------------------------

    def best_known_config(self, observer_sessions: list,
                          regime_id: int = None) -> dict:
        """Find the best-performing HP config from Observer history.

        Ranks past cycles by *efficiency* = pnl / max(duration_bars, 1).
        High PnL in short duration = best.  Filters to the current
        regime if specified and enough data exists.

        Parameters
        ----------
        observer_sessions : list of dict
            Enriched sessions from Observer, each with ``hp_used``,
            ``pnl``, ``bars``, ``regime_id_at_entry``.
        regime_id : int, optional
            Current regime — prefer configs from matching regime.

        Returns
        -------
        dict — the HP config dict from the best session, or ``{}`` if
        no usable history.
        """
        if not observer_sessions:
            return {}

        # Score each session: efficiency = pnl / max(bars, 1)
        # Negative PnL or long duration = low score
        scored = []
        for sess in observer_sessions:
            hp_used = sess.get('hp_used')
            if not hp_used:
                continue
            pnl = sess.get('pnl', 0)
            bars = max(sess.get('bars', 1), 1)
            regime = sess.get('regime_id_at_entry', 0)
            efficiency = pnl / bars
            scored.append((efficiency, regime, hp_used))

        if not scored:
            return {}

        # Filter to current regime if we have enough matching sessions
        if regime_id is not None:
            regime_matches = [(eff, r, hp) for eff, r, hp in scored if r == regime_id]
            if len(regime_matches) >= 3:
                scored = regime_matches

        # Pick the best by efficiency
        scored.sort(key=lambda x: x[0], reverse=True)
        best_hp = scored[0][2]

        # Filter through safety bounds and return
        safe_config = {}
        for name, value in best_hp.items():
            if name in self._hp_lookup:
                safe_config[name] = value
            # Also include params the bandit doesn't manage (like preset)
            # but skip them — only return bandit-managed params

        # Apply safety bounds
        for param_name, (safe_lo, safe_hi) in _SAFETY_BOUNDS.items():
            if param_name in safe_config:
                v = safe_config[param_name]
                if isinstance(v, (int, float)):
                    safe_config[param_name] = type(v)(max(safe_lo, min(safe_hi, v)))

        return safe_config

    # ------------------------------------------------------------------
    # HP injection
    # ------------------------------------------------------------------

    def inject_hp(self, strategy, hp_config: dict) -> None:
        """Set ALL selected HPs on ``strategy.hp`` between cycles.

        The strategy reads all params (hedge_value, tp_value, sizing_factor
        etc.) directly from ``self.hp``, so every group must be injected
        structurally — not via OrderIntent.

        Parameters
        ----------
        strategy : Strategy instance
        hp_config : dict
            HP config from ``select()``.
        """
        if not hp_config or strategy.hp is None:
            return

        for name, value in hp_config.items():
            hp_def = self._hp_lookup.get(name)
            if hp_def is None:
                continue
            # Only set if param exists in strategy.hp
            if name in strategy.hp:
                strategy.hp[name] = value

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_selection(self) -> dict:
        """HP config selected for current cycle (for Observer)."""
        return dict(self._current_selection)

    @property
    def n_cycles(self) -> int:
        """Total cycles seen (including warmup)."""
        return self._n_cycles

    @property
    def is_warmed_up(self) -> bool:
        """True if warmup period has elapsed and schema is registered."""
        return self._hp_schema is not None and self._n_cycles >= self._warmup

    @property
    def history(self) -> list:
        """Cycle-level selection history for analysis."""
        return self._cycle_history

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def state_dict(self) -> dict:
        """Serialize full state for persistence."""
        bandits_ser = {}
        for group_name, regime_map in self._bandits.items():
            bandits_ser[group_name] = {}
            for regime_id, bandit in regime_map.items():
                bandits_ser[group_name][str(regime_id)] = {
                    'alpha': bandit.alpha.tolist(),
                    'beta': bandit.beta.tolist(),
                    'visit_count': bandit.visit_count.tolist(),
                }

        return {
            'n_cycles': self._n_cycles,
            'warmup': self._warmup,
            'max_arms': self._max_arms,
            'k_max': self._k_max,
            'last_regime_id': self._last_regime_id,
            'group_arms': {g: list(arms) for g, arms in self._group_arms.items()},
            'bandits': bandits_ser,
            'cycle_history': self._cycle_history[-1000:],  # keep last 1000
        }

    def load_state_dict(self, d: dict) -> None:
        """Restore from persisted state.

        Arms are restored from saved state, so the same arm indices
        remain valid across save/load cycles.
        """
        self._n_cycles = d.get('n_cycles', 0)
        self._warmup = d.get('warmup', self._warmup)
        self._max_arms = d.get('max_arms', self._max_arms)
        self._k_max = d.get('k_max', self._k_max)
        self._last_regime_id = d.get('last_regime_id', 0)
        self._cycle_history = d.get('cycle_history', [])

        # Restore arms
        saved_arms = d.get('group_arms', {})
        for group_name, arms in saved_arms.items():
            self._group_arms[group_name] = arms

        # Restore bandits
        saved_bandits = d.get('bandits', {})
        for group_name, regime_map in saved_bandits.items():
            if group_name not in self._bandits:
                self._bandits[group_name] = {}
            for regime_id_str, state in regime_map.items():
                regime_id = int(regime_id_str)
                arms = self._group_arms.get(group_name, [])
                n_arms = len(arms)
                alpha = np.array(state['alpha'][:n_arms], dtype=np.float64)
                beta_arr = np.array(state['beta'][:n_arms], dtype=np.float64)
                vc = state.get('visit_count')
                visit_count = np.array(vc[:n_arms], dtype=np.int32) if vc else np.zeros(n_arms, dtype=np.int32)
                self._bandits[group_name][regime_id] = BanditState(
                    arms=arms,
                    alpha=alpha,
                    beta=beta_arr,
                    visit_count=visit_count,
                )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_or_create_bandit(self, group_name: str, regime_id: int) -> BanditState:
        """Get or lazily create a BanditState for the group+regime pair."""
        regime_map = self._bandits.setdefault(group_name, {})
        if regime_id not in regime_map:
            arms = self._group_arms.get(group_name, [])
            n_arms = len(arms)
            regime_map[regime_id] = BanditState(
                arms=arms,
                alpha=np.ones(n_arms, dtype=np.float64),
                beta=np.ones(n_arms, dtype=np.float64),
            )
        return regime_map[regime_id]

    def _filter_dependencies(self, merged: dict) -> dict:
        """Remove params whose ``depends_on`` constraints are not met.

        Uses the merged config itself to check dependency satisfaction,
        so if e.g. ``sizing_factor`` depends on ``sizing_curve`` being
        'geometric', and the merged config has ``sizing_curve='linear'``,
        then ``sizing_factor`` is dropped.
        """
        filtered = {}
        for name, value in merged.items():
            hp_def = self._hp_lookup.get(name)
            if hp_def is None:
                continue
            if _check_dependency(hp_def, merged):
                filtered[name] = value
        return filtered
