"""Tests for the RegimeTree hierarchical GMM component."""

import os
import tempfile

import numpy as np
import pytest

from pipelines._shared.components.regime_tree import (
    MacroCluster,
    RegimeTree,
    SubCluster,
)


def _make_feature_matrix(n=1000, n_features=7, n_clusters=3, seed=42):
    """Generate synthetic feature matrix with known cluster structure."""
    rng = np.random.RandomState(seed)
    samples_per = n // n_clusters
    chunks = []
    for i in range(n_clusters):
        center = rng.randn(n_features) * 3
        chunk = rng.randn(samples_per, n_features) * 0.5 + center
        chunks.append(chunk)
    # Handle remainder
    remainder = n - samples_per * n_clusters
    if remainder > 0:
        chunks.append(rng.randn(remainder, n_features) * 0.5)
    return np.vstack(chunks)


# ---------------------------------------------------------------------------
# TestMacroCluster
# ---------------------------------------------------------------------------
class TestMacroCluster:
    def test_fit_uses_bic(self):
        X = _make_feature_matrix(n=600, n_features=4, n_clusters=3)
        mc = MacroCluster()
        mc.fit(X, max_k=6, min_k=2)
        # Should discover between 2 and 6 components
        assert 2 <= mc.n_components <= 6

    def test_predict_proba_shape(self):
        X = _make_feature_matrix(n=400, n_features=3, n_clusters=2)
        mc = MacroCluster()
        mc.fit(X, max_k=5, min_k=2)
        proba = mc.predict_proba(X)
        assert proba.shape == (400, mc.n_components)
        # Each row sums to ~1
        np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-6)

    def test_predict_labels(self):
        X = _make_feature_matrix(n=300, n_features=3, n_clusters=2)
        mc = MacroCluster()
        mc.fit(X, max_k=4, min_k=2)
        labels = mc.predict(X)
        assert labels.shape == (300,)
        assert set(labels).issubset(set(range(mc.n_components)))


# ---------------------------------------------------------------------------
# TestSubCluster
# ---------------------------------------------------------------------------
class TestSubCluster:
    def test_small_dataset_single_cluster(self):
        """Datasets < 50 samples should fall back to single cluster."""
        sc = SubCluster(macro_id=0)
        X = np.random.randn(30, 3)
        sc.fit(X, max_k=4, min_k=1)
        assert sc._fitted
        proba = sc.predict_proba(X)
        assert proba.shape == (30, 1)

    def test_unfitted_returns_ones(self):
        sc = SubCluster(macro_id=1)
        proba = sc.predict_proba(np.random.randn(10, 3))
        assert proba.shape == (10, 1)
        np.testing.assert_allclose(proba, 1.0)

    def test_fit_normal(self):
        sc = SubCluster(macro_id=0)
        X = _make_feature_matrix(n=200, n_features=3, n_clusters=2)
        sc.fit(X, max_k=5, min_k=1)
        assert sc._fitted
        proba = sc.predict_proba(X)
        assert proba.shape[0] == 200


# ---------------------------------------------------------------------------
# TestRegimeTree
# ---------------------------------------------------------------------------
class TestRegimeTree:
    def test_fit_discovers_macro_regimes(self):
        X = _make_feature_matrix(n=1500, n_features=7, n_clusters=3, seed=99)
        tree = RegimeTree(min_leaf_samples=50, max_macro=10, max_sub=8)
        tree.fit(X, macro_features=[0, 1, 2], sub_features=[3, 4, 5, 6])
        assert 2 <= tree.n_macro <= 10

    def test_creates_sub_clusters(self):
        X = _make_feature_matrix(n=1200, n_features=6, n_clusters=3, seed=77)
        tree = RegimeTree(min_leaf_samples=50, max_macro=6, max_sub=4)
        tree.fit(X, macro_features=[0, 1, 2], sub_features=[3, 4, 5])
        assert tree.n_leaves >= tree.n_macro  # at least 1 sub per macro

    def test_classify_probabilities_sum_to_one(self):
        X = _make_feature_matrix(n=1000, n_features=5, n_clusters=2, seed=11)
        tree = RegimeTree(min_leaf_samples=50, max_macro=6, max_sub=4)
        tree.fit(X, macro_features=[0, 1], sub_features=[2, 3, 4])
        probs = tree.classify(X[0])
        total = sum(probs.values())
        assert abs(total - 1.0) < 1e-6

    def test_classify_best_returns_id_and_confidence(self):
        X = _make_feature_matrix(n=1000, n_features=5, n_clusters=2, seed=22)
        tree = RegimeTree(min_leaf_samples=50, max_macro=6, max_sub=4)
        tree.fit(X, macro_features=[0, 1], sub_features=[2, 3, 4])
        leaf_id, confidence = tree.classify_best(X[0])
        assert leaf_id in tree.leaf_ids
        assert 0.0 < confidence <= 1.0

    def test_sparse_leaves_merged(self):
        """With high min_leaf_samples, sparse leaves should be merged."""
        X = _make_feature_matrix(n=600, n_features=5, n_clusters=3, seed=33)
        tree = RegimeTree(min_leaf_samples=200, max_macro=6, max_sub=4)
        tree.fit(X, macro_features=[0, 1], sub_features=[2, 3, 4])
        # After merging, all remaining leaves should have >= min_leaf_samples
        # (or be the only leaf for their macro — can't merge further)
        for lid in tree.leaf_ids:
            macro_id, sub_id = tree._leaf_map[lid]
            # Count leaves sharing this macro
            siblings = [l for l, (m, s) in tree._leaf_map.items() if m == macro_id]
            if len(siblings) > 1:
                assert tree.leaf_sample_counts[lid] >= tree.min_leaf_samples

    def test_classify_batch_matches_single(self):
        """Vectorized classify_batch should match per-sample classify_best."""
        X = _make_feature_matrix(n=1000, n_features=5, n_clusters=2, seed=66)
        tree = RegimeTree(min_leaf_samples=50, max_macro=6, max_sub=4)
        tree.fit(X, macro_features=[0, 1], sub_features=[2, 3, 4])

        # Single classification
        single_labels = []
        single_confs = []
        for i in range(len(X)):
            lid, conf = tree.classify_best(X[i])
            single_labels.append(lid)
            single_confs.append(conf)

        # Batch classification
        batch_labels, batch_confs = tree.classify_batch(X)

        np.testing.assert_array_equal(batch_labels, single_labels)
        np.testing.assert_allclose(batch_confs, single_confs, atol=1e-10)

    def test_leaf_map_consistent(self):
        X = _make_feature_matrix(n=800, n_features=5, n_clusters=2, seed=44)
        tree = RegimeTree(min_leaf_samples=50, max_macro=6, max_sub=4)
        tree.fit(X, macro_features=[0, 1], sub_features=[2, 3, 4])
        assert set(tree.leaf_ids) == set(tree._leaf_map.keys())
        assert set(tree.leaf_ids) == set(tree.leaf_sample_counts.keys())

    def test_save_load_roundtrip(self):
        X = _make_feature_matrix(n=800, n_features=5, n_clusters=2, seed=55)
        tree = RegimeTree(min_leaf_samples=50, max_macro=6, max_sub=4)
        tree.fit(X, macro_features=[0, 1], sub_features=[2, 3, 4])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "tree.pkl")
            tree.save(path)
            loaded = RegimeTree.load(path)

        assert loaded.n_macro == tree.n_macro
        assert loaded.n_leaves == tree.n_leaves
        assert loaded.leaf_ids == tree.leaf_ids
        # Classify should give same result
        probs_orig = tree.classify(X[0])
        probs_loaded = loaded.classify(X[0])
        for lid in probs_orig:
            assert abs(probs_orig[lid] - probs_loaded[lid]) < 1e-10
