"""
Integration test for the full IslandPilot training and inference pipeline.

End-to-end test: synthetic candles -> features -> regime tree -> evolution
-> inference -> adaptive sizing -> save/load roundtrip -> IslandPilot class.
"""

import os
import shutil
import tempfile
from types import SimpleNamespace

import numpy as np
import pytest

from pipelines._shared.components.feature_selector import FeaturePool, select_features
from pipelines._shared.components.regime_tree import RegimeTree
from pipelines._shared.components.island_evolver import IslandEvolver, Genome
from pipelines._shared.components.regime_inferencer import RegimeInferencer
from pipelines._shared.components.adaptive_sizer import AdaptiveSizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_synthetic_candles(n: int = 2000, seed: int = 42) -> np.ndarray:
    """Create synthetic candles with regime shifts.

    Regimes:
        0-500:    low vol ranging
        500-1000: high vol trending up
        1000-1500: low vol ranging
        1500-2000: high vol trending down
    """
    rng = np.random.RandomState(seed)
    candles = np.zeros((n, 6))  # timestamp, open, close, high, low, volume

    # Timestamps: 5-minute bars starting 2020-01-01
    base_ts = 1577836800000  # 2020-01-01 00:00:00 UTC in ms
    candles[:, 0] = base_ts + np.arange(n) * 300_000

    price = 1.1000
    for i in range(n):
        if i < 500:
            # Low vol ranging
            drift = 0.0
            vol = 0.0002
        elif i < 1000:
            # High vol trending up
            drift = 0.0003
            vol = 0.0015
        elif i < 1500:
            # Low vol ranging
            drift = 0.0
            vol = 0.0002
        else:
            # High vol trending down
            drift = -0.0003
            vol = 0.0015

        change = drift + vol * rng.randn()
        new_price = price + change

        o = price
        c = new_price
        h = max(o, c) + abs(vol * rng.randn())
        l = min(o, c) - abs(vol * rng.randn())

        candles[i, 1] = o
        candles[i, 2] = c
        candles[i, 3] = h
        candles[i, 4] = l
        candles[i, 5] = rng.uniform(100, 10000)

        price = new_price

    return candles


class _RegimeTreeAdapter:
    """Adapter that makes RegimeTree.classify return a 3-tuple
    (regime_id, confidence, all_probs) as expected by RegimeInferencer."""

    def __init__(self, tree: RegimeTree):
        self._tree = tree

    def classify(self, feature_vector: np.ndarray):
        all_probs = self._tree.classify(feature_vector)
        # Convert int keys to str for inferencer
        all_probs_str = {str(k): v for k, v in all_probs.items()}
        best_lid = max(all_probs_str, key=all_probs_str.get)
        confidence = all_probs_str[best_lid]
        return best_lid, confidence, all_probs_str


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIslandPilotIntegration:

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up synthetic candles and temp dir."""
        self.candles = _make_synthetic_candles(2000, seed=42)
        self.tmpdir = tempfile.mkdtemp(prefix='island_pilot_test_')
        yield
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # -- Step 1-2: Features ------------------------------------------------

    def test_01_feature_pool_compute(self):
        """FeaturePool computes features without errors."""
        pool = FeaturePool()
        matrix = pool.compute(self.candles)

        assert matrix.shape[0] == len(self.candles)
        assert matrix.shape[1] == len(pool.feature_names)
        assert matrix.shape[1] > 10  # expect ~25 features

        # At least some features should have valid (non-NaN) values
        # in the latter half (after warmup)
        valid_cols = np.sum(~np.isnan(matrix[500:]), axis=0)
        assert np.any(valid_cols > 0), "All features are NaN"

    def test_02_feature_selection(self):
        """Feature selection picks features with nonzero MI scores."""
        pool = FeaturePool()
        matrix = pool.compute(self.candles)

        # Create a target: 0 for low-vol, 1 for high-vol regimes
        target = np.zeros(len(self.candles))
        target[500:1000] = 1
        target[1500:] = 1

        selected_idx, scores = select_features(matrix, target, k=5)

        assert len(selected_idx) == 5
        assert len(scores) == 5
        assert all(s >= 0 for s in scores)

    # -- Step 3-4: RegimeTree ----------------------------------------------

    def test_03_regime_tree_fit_classify(self):
        """RegimeTree fits and classifies into multiple regimes."""
        pool = FeaturePool()
        matrix = pool.compute(self.candles)

        # Use a subset of features (first 5 as macro, next 5 as sub)
        # Drop rows with NaN
        valid_mask = ~np.any(np.isnan(matrix[:, :10]), axis=1)
        clean_matrix = matrix[valid_mask]

        assert len(clean_matrix) > 200, "Not enough valid rows for tree fitting"

        tree = RegimeTree(min_leaf_samples=50, max_macro=5, max_sub=4)
        tree.fit(
            clean_matrix,
            macro_features=list(range(5)),
            sub_features=list(range(5, 10)),
        )

        assert tree.n_macro >= 2, "Expected at least 2 macro clusters"
        assert tree.n_leaves >= 2, "Expected at least 2 leaves"

        # Classify a single feature vector
        test_fv = clean_matrix[len(clean_matrix) // 2]
        probs = tree.classify(test_fv)
        assert len(probs) > 0
        assert abs(sum(probs.values()) - 1.0) < 0.01

        best_lid, confidence = tree.classify_best(test_fv)
        assert best_lid in tree.leaf_ids
        assert 0.0 < confidence <= 1.0

    # -- Step 5-6: IslandEvolver -------------------------------------------

    def test_04_island_evolver_evolve(self):
        """IslandEvolver runs evolution for 5 generations."""
        leaf_ids = ['0', '1', '2']
        config = {'pop_size': 10, 'seed': 42}
        evolver = IslandEvolver(leaf_ids, config=config)

        # Fake fitness: prefer higher base_size_pct and lower max_levels
        def fake_fitness(genes: dict) -> float:
            return genes.get('base_size_pct', 1.0) - genes.get('max_levels', 6)

        for gen in range(5):
            evolver.evolve_all(fake_fitness, generation=gen)

        summary = evolver.get_fitness_summary()
        for lid in leaf_ids:
            assert summary[lid]['n'] > 0
            assert summary[lid]['best'] is not None

        # Best genome should be retrievable
        best = evolver.get_best_genome('0')
        assert 'genes' in best
        assert best['fitness'] is not None

    # -- Step 7: RegimeInferencer ------------------------------------------

    def test_05_regime_inferencer_classifies(self):
        """RegimeInferencer classifies via tree and detects multiple regimes."""
        pool = FeaturePool()
        matrix = pool.compute(self.candles)

        # Fit tree
        valid_mask = ~np.any(np.isnan(matrix[:, :10]), axis=1)
        clean_matrix = matrix[valid_mask]
        clean_indices = np.where(valid_mask)[0]

        tree = RegimeTree(min_leaf_samples=50, max_macro=5, max_sub=4)
        tree.fit(clean_matrix, macro_features=list(range(5)),
                 sub_features=list(range(5, 10)))

        # Wrap tree for inferencer
        adapted = _RegimeTreeAdapter(tree)
        inferencer = RegimeInferencer(adapted, config={
            'min_confidence': 0.1,
            'default_hysteresis': 0.10,
            'transition_grace_candles': 3,
        })

        seen_regimes = set()
        for i in range(0, len(clean_matrix), 10):
            fv = clean_matrix[i]
            regime_id, conf, probs = inferencer.classify(fv)
            seen_regimes.add(regime_id)
            assert conf >= 0.0

        assert len(seen_regimes) >= 2, \
            f"Expected multiple regimes, only saw {seen_regimes}"

        counts = inferencer.get_regime_counts()
        assert len(counts) >= 2

    # -- Step 8: AdaptiveSizer ---------------------------------------------

    def test_06_adaptive_sizer_increasing_confidence(self):
        """AdaptiveSizer returns larger sizes for higher confidence."""
        sizer = AdaptiveSizer()

        sizes = []
        for conf in [0.1, 0.3, 0.5, 0.7, 0.9]:
            sz = sizer.compute(
                base_pct=1.0,
                confidence=conf,
                sensitivity=1.0,
                drawdown_pct=0.0,
                recovery_aggression=0.5,
                balance=10000.0,
                qty=1000.0,
            )
            sizes.append(sz)

        # Each successive size should be >= previous (higher confidence -> larger)
        for i in range(1, len(sizes)):
            assert sizes[i] >= sizes[i - 1], \
                f"Size did not increase: {sizes[i]} < {sizes[i - 1]} for conf step {i}"

        stats = sizer.get_stats()
        assert stats['calls'] == 5

    # -- Step 9: Save/Load roundtrip ---------------------------------------

    def test_07_save_load_roundtrip(self):
        """All components survive save/load."""
        pool = FeaturePool()
        matrix = pool.compute(self.candles)
        valid_mask = ~np.any(np.isnan(matrix[:, :10]), axis=1)
        clean_matrix = matrix[valid_mask]

        # Fit tree
        tree = RegimeTree(min_leaf_samples=50, max_macro=5, max_sub=4)
        tree.fit(clean_matrix, macro_features=list(range(5)),
                 sub_features=list(range(5, 10)))
        tree_path = os.path.join(self.tmpdir, 'tree.pkl')
        tree.save(tree_path)

        loaded_tree = RegimeTree.load(tree_path)
        assert loaded_tree.n_leaves == tree.n_leaves
        assert loaded_tree.leaf_ids == tree.leaf_ids

        # Evolver
        leaf_ids = [str(lid) for lid in tree.leaf_ids]
        evolver = IslandEvolver(leaf_ids, config={'pop_size': 5, 'seed': 42})

        def ff(genes):
            return genes.get('base_size_pct', 1.0)

        evolver.evolve_all(ff)
        evolver_path = os.path.join(self.tmpdir, 'evolver.json')
        evolver.save(evolver_path)

        loaded_evolver = IslandEvolver.load(evolver_path)
        assert set(loaded_evolver.leaf_ids) == set(leaf_ids)
        for lid in leaf_ids:
            assert len(loaded_evolver.populations[lid].individuals) == 5

        # Inferencer
        adapted = _RegimeTreeAdapter(tree)
        inferencer = RegimeInferencer(adapted, config={
            'min_confidence': 0.2,
            'default_hysteresis': 0.1,
            'transition_grace_candles': 3,
        })
        # Classify a few vectors to build state
        for i in range(0, min(50, len(clean_matrix)), 5):
            inferencer.classify(clean_matrix[i])

        inf_path = os.path.join(self.tmpdir, 'inferencer.json')
        inferencer.save(inf_path)

        loaded_inf = RegimeInferencer.load(inf_path, adapted)
        assert loaded_inf._classify_count == inferencer._classify_count
        assert loaded_inf.get_regime_counts() == inferencer.get_regime_counts()

        # AdaptiveSizer
        sizer = AdaptiveSizer({'drawdown_threshold_pct': 3.0})
        sizer.compute(1.0, 0.8, 1.0, 0.0, 0.5, 10000.0, 1000.0)
        sizer_path = os.path.join(self.tmpdir, 'sizer.json')
        sizer.save(sizer_path)

        loaded_sizer = AdaptiveSizer.load(sizer_path)
        assert loaded_sizer._calls == 1
        assert loaded_sizer.drawdown_threshold_pct == 3.0

    # -- Step 10: IslandPilot end-to-end -----------------------------------

    def test_08_island_pilot_end_to_end(self):
        """IslandPilot class works end-to-end with mock strategy."""
        from pipelines._shared.IslandPilot import IslandPilot

        # Pre-train components
        pool = FeaturePool()
        matrix = pool.compute(self.candles)
        valid_mask = ~np.any(np.isnan(matrix[:, :10]), axis=1)
        clean_matrix = matrix[valid_mask]

        tree = RegimeTree(min_leaf_samples=50, max_macro=5, max_sub=4)
        tree.fit(clean_matrix, macro_features=list(range(5)),
                 sub_features=list(range(5, 10)))

        leaf_ids = [str(lid) for lid in tree.leaf_ids]
        evolver = IslandEvolver(leaf_ids, config={'pop_size': 10, 'seed': 42})

        def fake_fitness(genes):
            return genes.get('base_size_pct', 1.0)
        for gen in range(5):
            evolver.evolve_all(fake_fitness, generation=gen)

        adapted = _RegimeTreeAdapter(tree)
        inferencer = RegimeInferencer(adapted, config={
            'min_confidence': 0.1,
            'default_hysteresis': 0.05,
            'transition_grace_candles': 2,
        })

        # Create IslandPilot and inject pre-trained components
        pilot = IslandPilot(config={'warmup': 50})
        pilot.regime_tree = tree
        pilot.evolver = evolver
        pilot.inferencer = inferencer

        # Create mock strategy
        mock_portfolio = SimpleNamespace(
            current_drawdown_pct=1.5,
            max_drawdown=2.0,
            equity=10000.0,
        )
        mock_strategy = SimpleNamespace(
            candles=self.candles,
            hp={
                'max_levels': 6,
                'tp_distance_atr_mult': 2.0,
                'hedge_distance_atr_mult': 1.0,
                'base_size_pct': 1.0,
                'sizing_curve': 'geometric',
            },
            balance=10000.0,
            portfolio=mock_portfolio,
        )

        # Run pipeline hooks
        # 1. on_before
        pilot.on_before(mock_strategy)
        assert pilot._candle_count == 1

        # Run enough candles to get past warmup
        for _ in range(60):
            pilot.on_before(mock_strategy)
        assert pilot._candle_count >= 50

        # 2. gate_entry — may or may not allow depending on regime confidence
        gate_result = pilot.gate_entry(mock_strategy)
        assert isinstance(gate_result, bool)

        # 3. adjust_size
        adjusted = pilot.adjust_size(mock_strategy, 1000.0, 'long')
        assert adjusted > 0

        # 4. suggest_exit
        exit_suggestion = pilot.suggest_exit(mock_strategy)
        assert exit_suggestion is None or isinstance(exit_suggestion, dict)

        # 5. on_cycle_end
        pilot.on_cycle_end(50.0, mock_strategy)
        assert pilot._cycle_count == 1

        # 6. get_stats
        stats = pilot.get_stats()
        assert 'candle_count' in stats
        assert 'cycle_count' in stats
        assert stats['cycle_count'] == 1

        # 7. save_state / load_state roundtrip
        state_dir = os.path.join(self.tmpdir, 'pilot_state')
        pilot.save_state(state_dir)
        assert os.path.exists(os.path.join(state_dir, 'regime_tree.pkl'))
        assert os.path.exists(os.path.join(state_dir, 'evolver.json'))
        assert os.path.exists(os.path.join(state_dir, 'inferencer.json'))
        assert os.path.exists(os.path.join(state_dir, 'sizer.json'))
        assert os.path.exists(os.path.join(state_dir, 'runtime.json'))

        # Load into a fresh pilot
        pilot2 = IslandPilot(config={'warmup': 50})
        pilot2.load_state(state_dir)

        assert pilot2.regime_tree is not None
        assert pilot2.regime_tree.n_leaves == tree.n_leaves
        assert pilot2.evolver is not None
        assert pilot2._cycle_count == 1
        assert pilot2._candle_count == pilot._candle_count

        # The loaded pilot should also be able to run on_before
        pilot2.on_before(mock_strategy)
        stats2 = pilot2.get_stats()
        assert stats2['candle_count'] == pilot._candle_count + 1


# Allow running standalone
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
