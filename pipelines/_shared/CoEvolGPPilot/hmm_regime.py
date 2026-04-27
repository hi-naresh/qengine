"""
HMM regime model for CoEvolGPPilot.

Wraps ``hmmlearn.GMMHMM`` with a sklearn ``GaussianMixture`` fallback. Both
back-ends expose the same interface:

    model.fit(X)               → fit on a (n_samples, n_features) matrix
    model.posteriors(X)        → (n_samples, n_states) posterior probabilities
    model.posterior(x)         → 1-D array of length n_states for a single obs
    model.save(path) / load(...)

Faithful to the paper (Yang et al., 2025) when hmmlearn is available — the
fallback drops temporal structure (GMM treats each obs as independent) but
still yields soft-gated per-state populations, preserving the qualitative
pattern the paper describes.
"""

from __future__ import annotations

import json
import os
import pickle
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

try:  # pragma: no cover — import fan-out
    import hmmlearn  # noqa: F401
    from hmmlearn.hmm import GMMHMM  # type: ignore
    _HMMLEARN_AVAILABLE = True
except Exception:  # pragma: no cover
    _HMMLEARN_AVAILABLE = False
    GMMHMM = None  # type: ignore


def hmmlearn_available() -> bool:
    return _HMMLEARN_AVAILABLE


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class HMMRegimeModel:
    """Three-state HMM (GMM emissions) with sklearn GaussianMixture fallback.

    When ``force_fallback=True`` or hmmlearn is unavailable, we fit a
    sklearn ``GaussianMixture`` with ``n_components = n_states`` and treat the
    component posteriors as state posteriors (i.i.d. assumption — no transition
    matrix). The API remains identical.
    """

    def __init__(
        self,
        n_states: int = 3,
        n_mix: int = 2,
        covariance_type: str = 'diag',
        n_iter: int = 100,
        tol: float = 1e-3,
        random_state: int = 42,
        force_fallback: bool = False,
    ):
        self.n_states = int(n_states)
        self.n_mix = int(n_mix)
        self.covariance_type = covariance_type
        self.n_iter = int(n_iter)
        self.tol = float(tol)
        self.random_state = int(random_state)
        self.force_fallback = bool(force_fallback) or not _HMMLEARN_AVAILABLE
        self.backend: str = 'sklearn_gmm' if self.force_fallback else 'hmmlearn_gmmhmm'
        self._model = None
        self.feature_names: list[str] = []
        self.feature_indices: list[int] = []
        self._fitted: bool = False

    # -- fitting -----------------------------------------------------------

    def fit(self, X: np.ndarray) -> 'HMMRegimeModel':
        X = np.asarray(X, dtype=np.float64)
        X = X[~np.any(np.isnan(X), axis=1)]
        if len(X) < max(20, 2 * self.n_states):
            raise ValueError(f'Too few samples to fit HMM: {len(X)}')

        if not self.force_fallback and GMMHMM is not None:
            model = GMMHMM(
                n_components=self.n_states,
                n_mix=self.n_mix,
                covariance_type=self.covariance_type,
                n_iter=self.n_iter,
                tol=self.tol,
                random_state=self.random_state,
            )
            bad_fit = False
            try:
                model.fit(X)
            except Exception as exc:  # pragma: no cover — robust to EM issues
                bad_fit = True
                fit_err = exc
            else:
                # Validate that EM produced usable parameters. On very small or
                # degenerate windows hmmlearn can emit NaN startprob / transmat.
                try:
                    sp = np.asarray(getattr(model, 'startprob_', []), dtype=np.float64)
                    tm = np.asarray(getattr(model, 'transmat_', []), dtype=np.float64)
                    if sp.size == 0 or not np.all(np.isfinite(sp)) \
                       or abs(sp.sum() - 1.0) > 1e-3:
                        bad_fit = True
                        fit_err = RuntimeError('startprob invalid after fit')
                    if tm.size and (not np.all(np.isfinite(tm))):
                        bad_fit = True
                        fit_err = RuntimeError('transmat invalid after fit')
                except Exception as exc:  # pragma: no cover
                    bad_fit = True
                    fit_err = exc

            if not bad_fit:
                self._model = model
                self.backend = 'hmmlearn_gmmhmm'
                self._fitted = True
                return self

            # Fall back to GaussianMixture silently rather than crashing.
            self.force_fallback = True
            self.backend = 'sklearn_gmm'
            print(
                f'[HMMRegimeModel] hmmlearn fit failed ({fit_err}); '
                'using sklearn GaussianMixture fallback'
            )

        # Fallback path
        from sklearn.mixture import GaussianMixture

        gmm = GaussianMixture(
            n_components=self.n_states,
            covariance_type=self.covariance_type,
            max_iter=self.n_iter,
            tol=self.tol,
            random_state=self.random_state,
        )
        gmm.fit(X)
        self._model = gmm
        self.backend = 'sklearn_gmm'
        self._fitted = True
        return self

    # -- inference ---------------------------------------------------------

    def posteriors(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted or self._model is None:
            raise RuntimeError('HMMRegimeModel is not fitted')
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X[None, :]
        # Replace any residual NaN with 0 — the caller should nan_to_num first,
        # but we defend against misuse so one bad row doesn't kill inference.
        if np.any(np.isnan(X)):
            X = np.nan_to_num(X, nan=0.0)

        if self.backend == 'hmmlearn_gmmhmm':
            # Forward-backward posteriors: p(state_t | obs_1..T)
            try:
                _, posteriors = self._model.score_samples(X)
            except Exception:
                # Fall back to predict_proba if score_samples unavailable
                posteriors = self._model.predict_proba(X)
            return np.asarray(posteriors, dtype=np.float64)
        # sklearn GaussianMixture
        return self._model.predict_proba(X)

    def posterior(self, x: np.ndarray) -> np.ndarray:
        """Return 1-D posterior vector for a single observation."""
        out = self.posteriors(x[None, :] if x.ndim == 1 else x)
        return out[-1]

    # -- persistence -------------------------------------------------------

    def save(self, path: str) -> None:
        if not self._fitted:
            raise RuntimeError('Nothing to save — model not fitted')
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        payload = {
            'backend': self.backend,
            'n_states': self.n_states,
            'n_mix': self.n_mix,
            'covariance_type': self.covariance_type,
            'n_iter': self.n_iter,
            'tol': self.tol,
            'random_state': self.random_state,
            'feature_names': list(self.feature_names),
            'feature_indices': list(self.feature_indices),
            'model': self._model,
        }
        with open(path, 'wb') as f:
            pickle.dump(payload, f)

    @classmethod
    def load(cls, path: str) -> 'HMMRegimeModel':
        with open(path, 'rb') as f:
            payload = pickle.load(f)
        inst = cls(
            n_states=payload['n_states'],
            n_mix=payload['n_mix'],
            covariance_type=payload['covariance_type'],
            n_iter=payload['n_iter'],
            tol=payload['tol'],
            random_state=payload['random_state'],
            force_fallback=(payload['backend'] == 'sklearn_gmm'),
        )
        inst._model = payload['model']
        inst.backend = payload['backend']
        inst.feature_names = list(payload.get('feature_names', []))
        inst.feature_indices = list(payload.get('feature_indices', []))
        inst._fitted = True
        return inst

    # -- sidecar metadata --------------------------------------------------

    def save_metadata_json(self, path: str) -> None:
        """Write human-readable feature metadata alongside the pickle."""
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        meta = {
            'backend': self.backend,
            'n_states': self.n_states,
            'n_mix': self.n_mix,
            'feature_names': self.feature_names,
            'feature_indices': self.feature_indices,
        }
        with open(path, 'w') as f:
            json.dump(meta, f, indent=2)
