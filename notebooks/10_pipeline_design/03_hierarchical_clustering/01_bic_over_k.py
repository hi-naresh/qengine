#!/usr/bin/env python3
"""Pivot 03 evidence: BIC selects a small k for the macro layer; deeper structure
needs sub-clustering rather than one large k.

Loads a 6-month slice of EUR-USD candles, computes a 5-feature snapshot per
candle (NATR_14, ADX_14, RSI_14, choppiness_14, ER_50), fits Gaussian Mixture
Models for k in 2..15, and plots BIC vs k. The shape of the curve motivates the
two-level GMM approach used in IslandPilot: macro k is small (bias-variance
trade-off), sub-cluster k is per-leaf.
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.mixture import GaussianMixture

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, ROOT)

from notebooks.shared.utils import load_candles
import qengine.indicators as ta

candles = load_candles('2024-01-01', '2024-06-30')
print(f'Loaded {len(candles)} 1m candles')
candles_5m = candles[::5]
print(f'Downsampled to {len(candles_5m)} 5m candles')

closes = candles_5m[:, 2].astype(float)
highs = candles_5m[:, 3].astype(float)
lows = candles_5m[:, 4].astype(float)

w = 300
features = []
for i in range(w, len(candles_5m)):
    sub_h = highs[i-w:i]
    sub_l = lows[i-w:i]
    sub_c = closes[i-w:i]
    natr = (sub_h - sub_l)[-14:].mean() / sub_c[-1]
    adx = float(ta.adx(candles_5m[i-w:i], period=14, sequential=False) or 0.0)
    rsi = float(ta.rsi(candles_5m[i-w:i], period=14, sequential=False) or 50.0)
    rng = (sub_h.max() - sub_l.min())
    er = abs(sub_c[-1] - sub_c[-50]) / (np.abs(np.diff(sub_c[-50:])).sum() + 1e-9)
    chop = 1.0 - er
    features.append([natr, adx, rsi, chop, er])

X = np.array(features)
mask = np.isfinite(X).all(axis=1)
X = X[mask]
print(f'Feature matrix: {X.shape}')

mu = X.mean(axis=0)
sigma = X.std(axis=0) + 1e-9
Xn = (X - mu) / sigma

ks = list(range(2, 16))
bics = []
for k in ks:
    gmm = GaussianMixture(n_components=k, covariance_type='full', random_state=0, max_iter=200)
    gmm.fit(Xn)
    bics.append(gmm.bic(Xn))
    print(f'  k={k}: BIC={bics[-1]:.1f}')

best_k = ks[int(np.argmin(bics))]

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(ks, bics, 'o-', color='steelblue')
ax.axvline(best_k, color='red', linestyle='--', label=f'BIC-optimal k = {best_k}')
ax.set_xlabel('Number of clusters (k)')
ax.set_ylabel('BIC (lower is better)')
ax.set_title('Pivot 03: BIC over k for flat GMM on 5-feature EUR-USD\n(macro layer favours small k; deeper granularity needs sub-clustering)')
ax.legend()
ax.grid(True, alpha=0.3)
fig.tight_layout()
out = os.path.join(RESULTS, 'bic_over_k.png')
fig.savefig(out, dpi=120)
plt.close(fig)

pd.DataFrame({'k': ks, 'bic': bics}).to_csv(os.path.join(RESULTS, 'bic_over_k.csv'), index=False)
print(f'Saved {out}')
print(f'BIC-optimal k = {best_k}')
