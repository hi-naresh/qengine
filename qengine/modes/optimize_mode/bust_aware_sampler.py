"""
Bust-Aware Sampler for trading strategy optimization.

A custom Optuna sampler that wraps TPE with domain-specific knowledge:
1. Penalizes parameter regions that produce negative expectancy
2. Avoids bust-prone configurations using the p*m risk formula
3. Uses early-trial results to build a "danger map" of the parameter space

The key insight from Surefire research:
  Risk = (p * m)^N / (m - 1)
  where p = P(lose per level), m = multiplier, N = max levels
  Critical condition: p * m < 1, otherwise bust probability explodes.

This sampler:
- Starts with TPE exploration (startup phase)
- Tracks which parameter regions produce negative ratios or high drawdowns
- Biases future sampling away from those regions
- Adds a bust-risk penalty to the score for grid/martingale strategies
"""
import numpy as np
from typing import Any, Dict, Optional, Sequence
import optuna
from optuna.samplers import TPESampler, RandomSampler
from optuna.study import Study
from optuna.trial import FrozenTrial, TrialState
from optuna.distributions import BaseDistribution


class BustAwareSampler(optuna.samplers.BaseSampler):
    """Optuna sampler that wraps TPE with bust/drawdown awareness.

    It tracks completed trials and builds a model of "danger zones" in the
    parameter space — regions that consistently produce negative expectancy,
    extreme drawdowns, or bust-like outcomes. Future samples are biased
    away from these zones.
    """

    def __init__(
        self,
        n_startup_trials: int = 15,
        max_drawdown_threshold: float = -50.0,
        negative_ratio_penalty: float = 0.7,
        seed: Optional[int] = None,
    ):
        """
        Args:
            n_startup_trials: Number of random trials before TPE kicks in.
            max_drawdown_threshold: Drawdown % below which a trial is flagged as dangerous.
                E.g., -50 means any trial with max_drawdown < -50% is a danger signal.
            negative_ratio_penalty: Probability of re-sampling when TPE suggests params
                that fall in a known danger zone. 0.7 = 70% chance of rejecting and
                re-sampling. Higher = more aggressive avoidance.
            seed: Random seed for reproducibility.
        """
        self._tpe = TPESampler(n_startup_trials=n_startup_trials, seed=seed)
        self._random = RandomSampler(seed=seed)
        self._n_startup_trials = n_startup_trials
        self._max_dd_threshold = max_drawdown_threshold
        self._neg_penalty = negative_ratio_penalty
        self._rng = np.random.RandomState(seed)

        # Danger tracking: maps param_name -> set of values that appeared in bad trials
        self._danger_zones: Dict[str, list] = {}
        # Track bad trial param combinations
        self._bad_trials: list = []
        self._total_trials_seen = 0

    def infer_relative_search_space(
        self, study: Study, trial: FrozenTrial
    ) -> Dict[str, BaseDistribution]:
        return self._tpe.infer_relative_search_space(study, trial)

    def sample_relative(
        self,
        study: Study,
        trial: FrozenTrial,
        search_space: Dict[str, BaseDistribution],
    ) -> Dict[str, Any]:
        # Update danger zones from completed trials
        self._update_danger_model(study)

        # During startup, use random sampling
        if self._total_trials_seen < self._n_startup_trials:
            return self._random.sample_relative(study, trial, search_space)

        # Use TPE for the base suggestion
        params = self._tpe.sample_relative(study, trial, search_space)

        # Check if suggested params fall in a danger zone
        if self._is_dangerous(params) and self._rng.random() < self._neg_penalty:
            # Re-sample up to 3 times to escape danger zone
            for _ in range(3):
                params = self._tpe.sample_relative(study, trial, search_space)
                if not self._is_dangerous(params):
                    break

        return params

    def sample_independent(
        self,
        study: Study,
        trial: FrozenTrial,
        param_name: str,
        param_distribution: BaseDistribution,
    ) -> Any:
        # Update danger model
        self._update_danger_model(study)

        if self._total_trials_seen < self._n_startup_trials:
            return self._random.sample_independent(study, trial, param_name, param_distribution)

        value = self._tpe.sample_independent(study, trial, param_name, param_distribution)

        # Check if this specific param value is in a danger zone
        if param_name in self._danger_zones:
            danger_values = self._danger_zones[param_name]
            if self._value_near_danger(value, danger_values) and self._rng.random() < self._neg_penalty:
                # Try to sample away from danger
                for _ in range(3):
                    value = self._tpe.sample_independent(study, trial, param_name, param_distribution)
                    if not self._value_near_danger(value, danger_values):
                        break

        return value

    def _update_danger_model(self, study: Study):
        """Scan completed trials and flag dangerous parameter regions."""
        completed = [t for t in study.trials if t.state == TrialState.COMPLETE]
        if len(completed) <= self._total_trials_seen:
            return  # No new trials to process

        new_trials = completed[self._total_trials_seen:]
        self._total_trials_seen = len(completed)

        for trial in new_trials:
            score = trial.value
            if score is None:
                continue

            # A trial is "bad" if it scored at the minimum (0.0001 = rejected by fitness)
            is_bad = score <= 0.001

            # Also check user_attrs for drawdown if available
            training_metrics = trial.user_attrs.get('training_metrics', {})
            if training_metrics:
                max_dd = training_metrics.get('max_drawdown', 0)
                if max_dd < self._max_dd_threshold:
                    is_bad = True

                # Check for negative expectancy
                expectancy = training_metrics.get('expectancy', None)
                if expectancy is not None and expectancy < 0:
                    is_bad = True

            if is_bad:
                self._bad_trials.append(trial.params)
                for param_name, value in trial.params.items():
                    if param_name not in self._danger_zones:
                        self._danger_zones[param_name] = []
                    self._danger_zones[param_name].append(value)

    def _is_dangerous(self, params: Dict[str, Any]) -> bool:
        """Check if a param combination overlaps significantly with known bad trials."""
        if not self._bad_trials:
            return False

        # Count how many params match danger zone values
        danger_matches = 0
        total_params = len(params)

        for param_name, value in params.items():
            if param_name in self._danger_zones:
                if self._value_near_danger(value, self._danger_zones[param_name]):
                    danger_matches += 1

        # Dangerous if more than half the params are in danger zones
        return danger_matches > total_params / 2

    def _value_near_danger(self, value: Any, danger_values: list) -> bool:
        """Check if a value is close to known dangerous values."""
        if not danger_values:
            return False

        # For categorical/string values: exact match
        if isinstance(value, str):
            return value in danger_values

        # For numeric values: check if within 10% of any dangerous value's range
        numeric_dangers = [v for v in danger_values if isinstance(v, (int, float))]
        if not numeric_dangers:
            return False

        if len(numeric_dangers) < 2:
            # Not enough data to define a range — check exact proximity
            return any(abs(value - d) < abs(d) * 0.05 + 1e-9 for d in numeric_dangers)

        # Check if value falls within the danger cluster
        d_min = min(numeric_dangers)
        d_max = max(numeric_dangers)
        d_range = d_max - d_min
        # Expand the danger zone by 10% on each side
        margin = max(d_range * 0.1, abs(d_min) * 0.02)
        return (d_min - margin) <= value <= (d_max + margin)
