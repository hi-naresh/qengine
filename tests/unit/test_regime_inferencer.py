"""Tests for the RegimeInferencer with hysteresis."""

import os
import tempfile
from unittest.mock import MagicMock

import numpy as np
import pytest

from qengine.framework.components.regime_inferencer import RegimeInferencer


def _make_mock_tree(regime_sequence):
    """
    Create a mock regime tree that returns regimes from a sequence.
    Each call to classify() returns (regime_id, confidence, all_probs).
    """
    tree = MagicMock()
    tree.classify = MagicMock(side_effect=regime_sequence)
    return tree


# ---------------------------------------------------------------------------
# Basic classification
# ---------------------------------------------------------------------------

class TestRegimeInferencer:
    def test_returns_regime_and_confidence(self):
        seq = [
            ("R0", 0.8, {"R0": 0.8, "R1": 0.2}),
        ]
        tree = _make_mock_tree(seq)
        ri = RegimeInferencer(tree)
        fv = np.array([1.0, 2.0, 3.0])
        regime, conf, probs = ri.classify(fv)
        assert regime == "R0"
        assert conf == 0.8
        assert "R0" in probs

    def test_hysteresis_prevents_whipsaw(self):
        """Small probability advantage should NOT cause a switch."""
        seq = [
            ("R0", 0.6, {"R0": 0.6, "R1": 0.4}),
            # R1 is slightly better but not by hysteresis margin (0.15)
            ("R1", 0.55, {"R0": 0.45, "R1": 0.55}),
            # Still not enough
            ("R1", 0.56, {"R0": 0.44, "R1": 0.56}),
        ]
        tree = _make_mock_tree(seq)
        ri = RegimeInferencer(tree, config={"default_hysteresis": 0.15})
        fv = np.zeros(3)

        r1, _, _ = ri.classify(fv)  # R0
        assert r1 == "R0"

        r2, _, _ = ri.classify(fv)  # should stay R0 (0.55 < 0.45 + 0.15)
        assert r2 == "R0"

        r3, _, _ = ri.classify(fv)  # still R0
        assert r3 == "R0"

    def test_switches_when_margin_exceeded(self):
        """Large probability advantage should cause a switch."""
        seq = [
            ("R0", 0.7, {"R0": 0.7, "R1": 0.3}),
            # R1 now dominant enough: 0.85 > 0.15 + 0.15
            ("R1", 0.85, {"R0": 0.15, "R1": 0.85}),
        ]
        tree = _make_mock_tree(seq)
        ri = RegimeInferencer(tree, config={"default_hysteresis": 0.15})
        fv = np.zeros(3)

        r1, _, _ = ri.classify(fv)
        assert r1 == "R0"

        r2, _, _ = ri.classify(fv)
        assert r2 == "R1"

    def test_transition_log_records_switches(self):
        seq = [
            ("R0", 0.9, {"R0": 0.9, "R1": 0.1}),
            ("R1", 0.95, {"R0": 0.05, "R1": 0.95}),
        ]
        tree = _make_mock_tree(seq)
        ri = RegimeInferencer(tree, config={"default_hysteresis": 0.1})
        fv = np.zeros(3)

        ri.classify(fv)  # R0
        ri.classify(fv)  # R1

        log = ri.get_transition_log()
        assert len(log) == 1
        assert log[0]["from"] == "R0"
        assert log[0]["to"] == "R1"

    def test_regime_counts_tracks_distribution(self):
        seq = [
            ("R0", 0.8, {"R0": 0.8, "R1": 0.2}),
            ("R0", 0.75, {"R0": 0.75, "R1": 0.25}),
            ("R0", 0.7, {"R0": 0.7, "R1": 0.3}),
        ]
        tree = _make_mock_tree(seq)
        ri = RegimeInferencer(tree)
        fv = np.zeros(3)

        for _ in range(3):
            ri.classify(fv)

        counts = ri.get_regime_counts()
        assert counts["R0"] == 3

    def test_grace_period_after_switch(self):
        seq = [
            ("R0", 0.9, {"R0": 0.9, "R1": 0.1}),
        ]
        tree = _make_mock_tree(seq)
        ri = RegimeInferencer(tree, config={"transition_grace_candles": 5})
        fv = np.zeros(3)

        ri.classify(fv)
        assert ri.in_grace_period is True

    def test_save_load_roundtrip(self):
        seq = [
            ("R0", 0.8, {"R0": 0.8, "R1": 0.2}),
            ("R0", 0.7, {"R0": 0.7, "R1": 0.3}),
        ]
        tree = _make_mock_tree(seq)
        ri = RegimeInferencer(tree, config={"default_hysteresis": 0.2})
        fv = np.zeros(3)
        ri.classify(fv)
        ri.classify(fv)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ri.save(path)
            # Load with a fresh mock tree
            loaded = RegimeInferencer.load(path, MagicMock())
            assert loaded._current_regime == ri._current_regime
            assert loaded.default_hysteresis == 0.2
            assert loaded.get_regime_counts() == ri.get_regime_counts()
            assert len(loaded.get_calibration_data()) == 2
        finally:
            os.unlink(path)

    def test_hysteresis_override(self):
        """Override hysteresis margin per call."""
        seq = [
            ("R0", 0.6, {"R0": 0.6, "R1": 0.4}),
            # With override=0.0, any advantage should switch
            ("R1", 0.55, {"R0": 0.45, "R1": 0.55}),
        ]
        tree = _make_mock_tree(seq)
        ri = RegimeInferencer(tree, config={"default_hysteresis": 0.5})
        fv = np.zeros(3)

        ri.classify(fv)  # R0
        r, _, _ = ri.classify(fv, hysteresis_override=0.0)
        assert r == "R1"
