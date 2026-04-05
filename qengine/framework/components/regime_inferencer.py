"""
RegimeInferencer — sticky regime classification with hysteresis.

Wraps a RegimeTree (or any classifier with a classify() method) and adds
hysteresis-based switching to prevent whipsaw regime flips.  Tracks transition
history, regime counts, and calibration data.

Part of the IslandPilot pipeline.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class RegimeInferencer:
    """Classifies feature vectors into regimes with sticky hysteresis."""

    def __init__(self, regime_tree: Any, config: Optional[dict] = None):
        config = config or {}
        self._tree = regime_tree
        self.min_confidence = config.get("min_confidence", 0.3)
        self.default_hysteresis = config.get("default_hysteresis", 0.15)
        self.transition_grace_candles = config.get("transition_grace_candles", 5)

        # State
        self._current_regime: Optional[str] = None
        self._current_confidence: float = 0.0
        self._candles_since_switch: int = 0
        self._in_grace: bool = False
        self._classify_count: int = 0

        # Logs
        self._transition_log: List[dict] = []
        self._regime_counts: Dict[str, int] = {}
        self._calibration_data: List[dict] = []

    # -- core API ----------------------------------------------------------

    def classify(
        self,
        feature_vector: np.ndarray,
        hysteresis_override: Optional[float] = None,
    ) -> Tuple[str, float, dict]:
        """
        Classify a feature vector into a regime.

        Returns (regime_id, confidence, all_probs).
        Applies hysteresis: only switches if new regime probability exceeds
        current regime probability by the hysteresis margin.
        """
        result = self._tree.classify(feature_vector)
        # Expect result to be (regime_id, confidence, all_probs) or similar
        if isinstance(result, tuple) and len(result) == 3:
            new_regime, new_confidence, all_probs = result
        else:
            raise ValueError(f"Unexpected classify result format: {result}")

        margin = hysteresis_override if hysteresis_override is not None else self.default_hysteresis
        self._classify_count += 1

        # Track calibration
        self._calibration_data.append({
            "raw_regime": new_regime,
            "raw_confidence": float(new_confidence),
            "all_probs": {k: float(v) for k, v in all_probs.items()} if isinstance(all_probs, dict) else {},
        })

        # First classification — always accept
        if self._current_regime is None:
            self._set_regime(new_regime, new_confidence, all_probs, is_first=True)
            return self._current_regime, self._current_confidence, all_probs

        # Hysteresis check
        current_prob = all_probs.get(self._current_regime, 0.0) if isinstance(all_probs, dict) else 0.0
        new_prob = all_probs.get(new_regime, new_confidence) if isinstance(all_probs, dict) else new_confidence

        if new_regime != self._current_regime and new_prob > current_prob + margin:
            self._set_regime(new_regime, new_confidence, all_probs)
        else:
            # Stay with current regime, update confidence
            self._current_confidence = current_prob if isinstance(all_probs, dict) else self._current_confidence
            self._candles_since_switch += 1
            if self._candles_since_switch >= self.transition_grace_candles:
                self._in_grace = False

        # Update regime counts
        self._regime_counts[self._current_regime] = self._regime_counts.get(self._current_regime, 0) + 1

        return self._current_regime, self._current_confidence, all_probs

    # -- internal ----------------------------------------------------------

    def _set_regime(
        self,
        regime_id: str,
        confidence: float,
        all_probs: dict,
        is_first: bool = False,
    ) -> None:
        old = self._current_regime
        self._current_regime = regime_id
        self._current_confidence = confidence
        self._candles_since_switch = 0
        self._in_grace = True

        if not is_first:
            self._transition_log.append({
                "from": old,
                "to": regime_id,
                "confidence": float(confidence),
                "classify_count": self._classify_count,
            })

        # Count the first classification too
        if is_first:
            self._regime_counts[regime_id] = self._regime_counts.get(regime_id, 0) + 1

    # -- properties --------------------------------------------------------

    @property
    def in_grace_period(self) -> bool:
        return self._in_grace

    # -- stats -------------------------------------------------------------

    def get_regime_counts(self) -> Dict[str, int]:
        return dict(self._regime_counts)

    def get_transition_log(self) -> List[dict]:
        return list(self._transition_log)

    def get_calibration_data(self) -> List[dict]:
        return list(self._calibration_data)

    # -- persistence -------------------------------------------------------

    def save(self, path: str) -> None:
        data = {
            "min_confidence": self.min_confidence,
            "default_hysteresis": self.default_hysteresis,
            "transition_grace_candles": self.transition_grace_candles,
            "current_regime": self._current_regime,
            "current_confidence": self._current_confidence,
            "candles_since_switch": self._candles_since_switch,
            "in_grace": self._in_grace,
            "classify_count": self._classify_count,
            "transition_log": self._transition_log,
            "regime_counts": self._regime_counts,
            "calibration_data": self._calibration_data,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str, regime_tree: Any) -> "RegimeInferencer":
        with open(path) as f:
            data = json.load(f)
        config = {
            "min_confidence": data["min_confidence"],
            "default_hysteresis": data["default_hysteresis"],
            "transition_grace_candles": data["transition_grace_candles"],
        }
        obj = cls(regime_tree, config)
        obj._current_regime = data["current_regime"]
        obj._current_confidence = data["current_confidence"]
        obj._candles_since_switch = data["candles_since_switch"]
        obj._in_grace = data["in_grace"]
        obj._classify_count = data["classify_count"]
        obj._transition_log = data["transition_log"]
        obj._regime_counts = data["regime_counts"]
        obj._calibration_data = data.get("calibration_data", [])
        return obj
