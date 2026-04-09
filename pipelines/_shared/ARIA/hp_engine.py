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
_N_BINS = 5                         # default discretization bins

# Groups whose HPs are set on strategy.hp between cycles
_STRUCTURAL_GROUPS = {'General', 'Entry Signal', 'Filters', 'Risk Management',
                      'Position Management'}

# Groups whose HPs are injected per-order on OrderIntent
_ORDER_GROUPS = {'Grid / Hedge', 'Take Profit'}


# ---------------------------------------------------------------------------
# BanditState
# ---------------------------------------------------------------------------

@dataclass
class BanditState:
    """Per-group, per-regime Thompson Sampling bandit state.

    Each arm is a dict mapping parameter names to values.  Alpha and beta
    arrays hold the Beta distribution parameters (one pair per arm).
    """

    arms: list                  # list of {param_name: value, ...} dicts
    alpha: np.ndarray           # shape (n_arms,), Beta alpha per arm
    beta: np.ndarray            # shape (n_arms,), Beta beta per arm

    def sample_best(self) -> int:
        """Thompson Sampling: draw from each arm's Beta, return index of max."""
        samples = np.random.beta(self.alpha, self.beta)
        return int(np.argmax(samples))


# ---------------------------------------------------------------------------
# Arm construction helpers
# ---------------------------------------------------------------------------

def _discretize_float(lo: float, hi: float, n_bins: int = _N_BINS) -> list:
    """Return n_bins evenly-spaced float values in [lo, hi]."""
    if n_bins <= 1:
        return [lo]
    step = (hi - lo) / (n_bins - 1)
    return [round(lo + i * step, 8) for i in range(n_bins)]


def _discretize_int(lo: int, hi: int, n_bins: int = _N_BINS) -> list:
    """Return up to n_bins integer values in [lo, hi]."""
    span = hi - lo + 1
    if span <= n_bins:
        return list(range(lo, hi + 1))
    step = (hi - lo) / (n_bins - 1)
    vals = sorted(set(int(round(lo + i * step)) for i in range(n_bins)))
    return vals


def _param_values(hp_def: dict, n_bins: int = _N_BINS) -> list:
    """Return discrete candidate values for a single HP definition."""
    hp_type = hp_def.get('type')
    if hp_type == 'categorical':
        return list(hp_def.get('options', []))
    if hp_type is float or hp_type == float:
        lo = hp_def.get('min', 0.0)
        hi = hp_def.get('max', 1.0)
        return _discretize_float(lo, hi, n_bins)
    if hp_type is int or hp_type == int:
        lo = int(hp_def.get('min', 0))
        hi = int(hp_def.get('max', 10))
        return _discretize_int(lo, hi, n_bins)
    return [hp_def.get('default')]


def _build_arms(group_hps: list, max_arms: int, n_bins: int) -> list:
    """Build a set of arm configurations for a group of HPs.

    Always includes the default config as arm 0.  Remaining arms are
    sampled randomly from the cartesian product of per-param discrete
    values, capped at ``max_arms``.

    Parameters
    ----------
    group_hps : list of HP definition dicts
    max_arms : int
        Maximum number of arms to generate.
    n_bins : int
        Number of bins for numeric discretization.

    Returns
    -------
    list of dicts, each mapping param_name -> param_value.
    """
    if not group_hps:
        return []

    # Collect per-param candidate values
    param_names = [hp['name'] for hp in group_hps]
    param_vals = [_param_values(hp, n_bins) for hp in group_hps]

    # Arm 0: default configuration
    default_arm = {}
    for hp in group_hps:
        default_arm[hp['name']] = hp.get('default')

    arms = [default_arm]
    seen = {_arm_key(default_arm, param_names)}

    # Estimate combinatorial size
    total_combos = 1
    for vals in param_vals:
        total_combos *= max(len(vals), 1)
        if total_combos > max_arms * 100:
            break  # no point computing further

    # Sample random arms
    attempts = 0
    max_attempts = max_arms * 10
    while len(arms) < max_arms and attempts < max_attempts:
        attempts += 1
        arm = {}
        for name, vals in zip(param_names, param_vals):
            if vals:
                arm[name] = vals[np.random.randint(len(vals))]
            else:
                arm[name] = None
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

    If the HP has no dependency, it is always valid.  Otherwise, for each
    parent param in ``depends_on``, the current config must have one of
    the allowed values.
    """
    deps = hp_def.get('depends_on')
    if not deps:
        return True
    for parent_name, allowed_values in deps.items():
        current = full_config.get(parent_name)
        if current not in allowed_values:
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

    def update(self, profitable: bool) -> None:
        """Update bandit posteriors after cycle end.

        Parameters
        ----------
        profitable : bool
            True if the cycle was profitable (PnL > 0).
        """
        self._n_cycles += 1  # count completed cycles, not select() calls

        if not self._selected_arms:
            return

        reward = 1.0 if profitable else 0.0
        regime_id = self._last_regime_id

        for group_name, arm_idx in self._selected_arms.items():
            bandits_for_group = self._bandits.get(group_name, {})
            bandit = bandits_for_group.get(regime_id)
            if bandit is None:
                continue
            bandit.alpha[arm_idx] += reward
            bandit.beta[arm_idx] += (1.0 - reward)

        # Clear selection for next cycle
        self._selected_arms = {}

    # ------------------------------------------------------------------
    # HP injection
    # ------------------------------------------------------------------

    def inject_structural(self, strategy, hp_config: dict) -> None:
        """Set structural HPs on ``strategy.hp`` between cycles.

        Only injects params that belong to structural groups (General,
        Entry Signal, Filters, Risk Management, Position Management) and
        exist in the strategy's HP schema.

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
            group = hp_def.get('group', '')
            if group not in _STRUCTURAL_GROUPS:
                continue
            # Only set if param exists in strategy.hp
            if name in strategy.hp:
                strategy.hp[name] = value

    def inject_order(self, order_intent, hp_config: dict):
        """Modify order TP/hedge values based on selected config.

        Only touches params from order-time groups (Grid/Hedge, Take
        Profit).  Modifies price on the OrderIntent when appropriate.

        Parameters
        ----------
        order_intent : OrderIntent
            The order about to be submitted.
        hp_config : dict
            HP config from ``select()``.

        Returns
        -------
        OrderIntent (possibly modified).
        """
        if not hp_config:
            return order_intent

        # Collect order-time params
        order_params = {}
        for name, value in hp_config.items():
            hp_def = self._hp_lookup.get(name)
            if hp_def is None:
                continue
            group = hp_def.get('group', '')
            if group in _ORDER_GROUPS:
                order_params[name] = value

        if not order_params:
            return order_intent

        # Attach HP overrides as metadata on the intent for the strategy
        # to read during order execution.  We do NOT directly modify
        # price/qty here -- the strategy's order logic handles that
        # based on the HP values set on strategy.hp.
        if not hasattr(order_intent, 'hp_overrides'):
            order_intent.hp_overrides = {}
        order_intent.hp_overrides.update(order_params)

        return order_intent

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
        return self._hp_schema is not None and self._n_cycles > self._warmup

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
                self._bandits[group_name][regime_id] = BanditState(
                    arms=arms,
                    alpha=alpha,
                    beta=beta_arr,
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
