"""Tests for the FeatureSelector component."""

import numpy as np
import pytest

from pipelines._shared.components.feature_selector import (
    FeaturePool,
    compute_feature_matrix,
    select_features,
)


def _make_candles(n: int = 500, seed: int = 42) -> np.ndarray:
    """Generate synthetic OHLCV candles for testing.

    Returns numpy array with columns: [timestamp, open, close, high, low, volume]
    """
    rng = np.random.RandomState(seed)

    # Start from a base price and do a random walk
    base_price = 1.1000
    returns = rng.normal(0, 0.001, size=n)
    close = base_price + np.cumsum(returns)

    # Build OHLCV from close
    spread = rng.uniform(0.0002, 0.001, size=n)
    high = close + rng.uniform(0, 0.002, size=n)
    low = close - rng.uniform(0, 0.002, size=n)
    open_ = close + rng.normal(0, 0.0005, size=n)

    # Ensure high >= max(open, close) and low <= min(open, close)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    timestamps = np.arange(n) * 60_000  # 1-minute candles in ms
    volume = rng.uniform(100, 10000, size=n)

    candles = np.column_stack([timestamps, open_, close, high, low, volume])
    return candles


# ---------------------------------------------------------------------------
# TestFeaturePool
# ---------------------------------------------------------------------------
class TestFeaturePool:
    def test_categories_exist(self):
        pool = FeaturePool()
        cats = pool.categories
        assert isinstance(cats, dict)
        # Must have at least these 5 categories
        for cat in ['volatility', 'trend', 'chop', 'momentum', 'structure']:
            assert cat in cats, f"Missing category: {cat}"
            assert len(cats[cat]) > 0, f"Category {cat} is empty"

    def test_feature_names_returns_list(self):
        pool = FeaturePool()
        names = pool.feature_names
        assert isinstance(names, list)
        assert len(names) >= 20

    def test_compute_returns_correct_shape(self):
        candles = _make_candles(500)
        pool = FeaturePool()
        matrix = pool.compute(candles)
        assert matrix.ndim == 2
        assert matrix.shape[0] == 500
        assert matrix.shape[1] == len(pool.feature_names)

    def test_no_nans_after_warmup(self):
        candles = _make_candles(500)
        pool = FeaturePool()
        matrix = pool.compute(candles)
        # After index 200 (warmup), there should be no NaNs
        after_warmup = matrix[200:, :]
        nan_cols = np.any(np.isnan(after_warmup), axis=0)
        if nan_cols.any():
            bad_features = [pool.feature_names[i] for i in np.where(nan_cols)[0]]
            pytest.fail(f"NaN found after warmup in features: {bad_features}")


# ---------------------------------------------------------------------------
# TestComputeFeatureMatrix
# ---------------------------------------------------------------------------
class TestComputeFeatureMatrix:
    def test_returns_matrix_and_names(self):
        candles = _make_candles(500)
        matrix, names = compute_feature_matrix(candles)
        assert isinstance(matrix, np.ndarray)
        assert isinstance(names, list)
        assert matrix.shape[1] == len(names)

    def test_specific_features_present(self):
        candles = _make_candles(500)
        _, names = compute_feature_matrix(candles)
        for feat in ['natr_14', 'adx_14', 'rsi_14']:
            assert feat in names, f"Expected feature {feat} not in names"


# ---------------------------------------------------------------------------
# TestSelectFeatures
# ---------------------------------------------------------------------------
class TestSelectFeatures:
    def _make_features_and_target(self, n=400, n_feat=10, seed=42):
        """Create features where first 2 are informative, rest are noise."""
        rng = np.random.RandomState(seed)
        features = rng.randn(n, n_feat)
        # Target correlates with first two features
        score = features[:, 0] * 0.7 + features[:, 1] * 0.5
        target = (score > np.median(score)).astype(int)
        return features, target

    def test_selects_top_k(self):
        features, target = self._make_features_and_target()
        indices, scores = select_features(features, target, k=3)
        assert len(indices) == 3
        assert len(scores) == 3
        # Scores should be sorted descending
        assert scores[0] >= scores[1] >= scores[2]
        # The informative features (0, 1) should be among top 3
        assert 0 in indices
        assert 1 in indices

    def test_auto_k_with_threshold(self):
        features, target = self._make_features_and_target()
        indices, scores = select_features(features, target, k='auto', min_score_ratio=0.1)
        assert len(indices) >= 1
        # All kept scores should be >= min_score_ratio * max_score
        max_score = scores[0]
        for s in scores:
            assert s >= 0.1 * max_score - 1e-10  # small epsilon for float

    def test_handles_nan_rows(self):
        features, target = self._make_features_and_target(n=400)
        # Insert some NaNs in first few rows
        features[:5, :] = np.nan
        indices, scores = select_features(features, target, k=2)
        assert len(indices) == 2
