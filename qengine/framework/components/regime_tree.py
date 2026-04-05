"""
RegimeTree — hierarchical GMM clustering for market regime discovery.

Two-level hierarchy: macro-level clusters on primary features (e.g. volatility,
trend), then sub-level clusters per macro on secondary features (e.g. momentum,
structure).  Sparse leaves are merged into the closest sibling.

Part of the IslandPilot pipeline.
"""

import pickle
from typing import Dict, List, Tuple

import numpy as np
from sklearn.mixture import GaussianMixture


# ---------------------------------------------------------------------------
# MacroCluster
# ---------------------------------------------------------------------------

class MacroCluster:
    """Top-level GMM with BIC-based model selection."""

    def __init__(self):
        self._model: GaussianMixture | None = None

    def fit(self, X: np.ndarray, max_k: int = 10, min_k: int = 2) -> "MacroCluster":
        best_bic = np.inf
        best_model = None
        for k in range(min_k, max_k + 1):
            gmm = GaussianMixture(n_components=k, covariance_type="full",
                                  n_init=3, random_state=42)
            gmm.fit(X)
            bic = gmm.bic(X)
            if bic < best_bic:
                best_bic = bic
                best_model = gmm
        self._model = best_model
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict_proba(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict(X)

    @property
    def n_components(self) -> int:
        return self._model.n_components


# ---------------------------------------------------------------------------
# SubCluster
# ---------------------------------------------------------------------------

class SubCluster:
    """Per-macro sub-level GMM.  Falls back to single cluster for tiny data."""

    def __init__(self, macro_id: int):
        self.macro_id = macro_id
        self._model: GaussianMixture | None = None
        self._fitted: bool = False

    def fit(self, X: np.ndarray, max_k: int = 8, min_k: int = 1) -> "SubCluster":
        if len(X) < 50:
            # Too few samples — single cluster
            gmm = GaussianMixture(n_components=1, covariance_type="full",
                                  random_state=42)
            gmm.fit(X)
            self._model = gmm
            self._fitted = True
            return self

        best_bic = np.inf
        best_model = None
        for k in range(min_k, max_k + 1):
            if k > len(X):
                break
            gmm = GaussianMixture(n_components=k, covariance_type="full",
                                  n_init=3, random_state=42)
            gmm.fit(X)
            bic = gmm.bic(X)
            if bic < best_bic:
                best_bic = bic
                best_model = gmm
        self._model = best_model
        self._fitted = True
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted:
            return np.ones((len(X), 1))
        return self._model.predict_proba(X)

    @property
    def n_components(self) -> int:
        if not self._fitted or self._model is None:
            return 1
        return self._model.n_components


# ---------------------------------------------------------------------------
# RegimeTree
# ---------------------------------------------------------------------------

class RegimeTree:
    """Hierarchical macro → sub GMM regime tree with sparse leaf merging."""

    def __init__(self, min_leaf_samples: int = 200, max_macro: int = 10,
                 max_sub: int = 8):
        self.min_leaf_samples = min_leaf_samples
        self.max_macro = max_macro
        self.max_sub = max_sub

        self._macro: MacroCluster | None = None
        self._subs: Dict[int, SubCluster] = {}
        self._leaf_map: Dict[int, Tuple[int, int]] = {}  # leaf_id → (macro, sub)
        self.leaf_sample_counts: Dict[int, int] = {}
        self._macro_features: List[int] = []
        self._sub_features: List[int] = []

    # -- fit ----------------------------------------------------------------

    def fit(self, X: np.ndarray, macro_features: List[int],
            sub_features: List[int]) -> "RegimeTree":
        self._macro_features = macro_features
        self._sub_features = sub_features

        X_macro = X[:, macro_features]
        X_sub = X[:, sub_features]

        # 1. Fit macro level
        self._macro = MacroCluster()
        self._macro.fit(X_macro, max_k=self.max_macro, min_k=2)
        macro_labels = self._macro.predict(X_macro)

        # 2. Fit sub level per macro cluster
        self._subs = {}
        leaf_id = 0
        leaf_map: Dict[int, Tuple[int, int]] = {}
        leaf_counts: Dict[int, int] = {}

        for m in range(self._macro.n_components):
            mask = macro_labels == m
            X_sub_m = X_sub[mask]

            sc = SubCluster(macro_id=m)
            if len(X_sub_m) > 0:
                sc.fit(X_sub_m, max_k=self.max_sub, min_k=1)
            self._subs[m] = sc

            if len(X_sub_m) == 0:
                # Empty macro cluster — single virtual leaf
                leaf_map[leaf_id] = (m, 0)
                leaf_counts[leaf_id] = 0
                leaf_id += 1
            else:
                sub_labels = sc._model.predict(X_sub_m) if sc._fitted else np.zeros(len(X_sub_m), dtype=int)
                for s in range(sc.n_components):
                    count = int((sub_labels == s).sum())
                    leaf_map[leaf_id] = (m, s)
                    leaf_counts[leaf_id] = count
                    leaf_id += 1

        self._leaf_map = leaf_map
        self.leaf_sample_counts = leaf_counts

        # 3. Merge sparse leaves
        self._merge_sparse_leaves()

        return self

    def _merge_sparse_leaves(self):
        """Merge leaves with < min_leaf_samples into closest sibling."""
        changed = True
        while changed:
            changed = False
            for lid in list(self._leaf_map.keys()):
                if lid not in self._leaf_map:
                    continue
                count = self.leaf_sample_counts[lid]
                if count >= self.min_leaf_samples:
                    continue
                macro_id, sub_id = self._leaf_map[lid]
                # Find siblings (same macro, different leaf)
                siblings = [(l, s) for l, (m, s) in self._leaf_map.items()
                            if m == macro_id and l != lid]
                if not siblings:
                    continue  # Only leaf in this macro — can't merge

                # Merge into the sibling with the most samples
                best_sib = max(siblings, key=lambda x: self.leaf_sample_counts[x[0]])
                sib_lid = best_sib[0]
                self.leaf_sample_counts[sib_lid] += count
                del self._leaf_map[lid]
                del self.leaf_sample_counts[lid]
                changed = True

    # -- classify -----------------------------------------------------------

    def classify(self, feature_vector: np.ndarray) -> Dict[int, float]:
        """Return probability distribution over all leaves."""
        fv = np.asarray(feature_vector)
        x_macro = fv[self._macro_features].reshape(1, -1)
        x_sub = fv[self._sub_features].reshape(1, -1)

        macro_proba = self._macro.predict_proba(x_macro)[0]  # (n_macro,)

        result: Dict[int, float] = {}
        for lid, (m, s) in self._leaf_map.items():
            sc = self._subs[m]
            sub_proba = sc.predict_proba(x_sub)[0]  # (n_sub_components,)
            # s might be >= len(sub_proba) if leaves were merged — clamp
            if s < len(sub_proba):
                p_sub = sub_proba[s]
            else:
                # Merged leaf — accumulate probability from all merged sub ids
                p_sub = 1.0

            # Normalise sub probabilities within the active sub-ids for this macro
            # to account for merged leaves
            result[lid] = macro_proba[m] * p_sub

        # Renormalize so probabilities sum to 1
        total = sum(result.values())
        if total > 0:
            result = {k: v / total for k, v in result.items()}

        return result

    def classify_best(self, feature_vector: np.ndarray) -> Tuple[int, float]:
        """Return (best_leaf_id, confidence)."""
        probs = self.classify(feature_vector)
        best_lid = max(probs, key=probs.get)
        return best_lid, probs[best_lid]

    # -- properties ---------------------------------------------------------

    @property
    def n_macro(self) -> int:
        return self._macro.n_components if self._macro else 0

    @property
    def n_leaves(self) -> int:
        return len(self._leaf_map)

    @property
    def leaf_ids(self) -> List[int]:
        return sorted(self._leaf_map.keys())

    # -- persistence --------------------------------------------------------

    def save(self, path: str):
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str) -> "RegimeTree":
        with open(path, "rb") as f:
            return pickle.load(f)
