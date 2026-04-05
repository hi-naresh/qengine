"""
42 — Inference Validation

Tests regime classification accuracy on validation data (2024H2-2025H1).
Evaluates hysteresis settings, confidence calibration, and regime stability.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils import *

import numpy as np
import matplotlib.pyplot as plt

from qengine.framework.components.regime_tree import RegimeTree
from qengine.framework.components.regime_inferencer import RegimeInferencer
from qengine.framework.components.feature_selector import FeaturePool

log = get_logger('42_inference_validation')


# ---------------------------------------------------------------------------
# Tree wrapper for RegimeInferencer compatibility
# ---------------------------------------------------------------------------

class _TreeAdapter:
    """Wraps RegimeTree so classify() returns the 3-tuple that
    RegimeInferencer expects: (regime_id, confidence, all_probs)."""

    def __init__(self, tree: RegimeTree):
        self._tree = tree

    def classify(self, fv: np.ndarray):
        all_probs = self._tree.classify(fv)
        best_lid = max(all_probs, key=all_probs.get)
        return str(best_lid), all_probs[best_lid], {str(k): v for k, v in all_probs.items()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # 1. Load regime tree
    tree_path = MODELS_DIR / 'regime_tree.pkl'
    if not tree_path.exists():
        log.error(f"regime_tree.pkl not found at {tree_path}. Run script 40 first.")
        return
    tree = RegimeTree.load(str(tree_path))
    log.info(f"Loaded regime tree: {tree.n_leaves} leaves, {tree.n_macro} macro clusters")

    # 2. Load validation candles
    log.info("Loading validation candles 2024-07-01 to 2025-06-30 ...")
    warmup, trading = load_candles(start_date='2024-07-01', end_date='2025-06-30')
    candles = concat_candles(warmup, trading)
    log.info(f"Candles: {len(candles)} bars ({len(warmup) if warmup.ndim == 2 else 0} warmup)")

    # 3. Compute features
    log.info("Computing feature pool ...")
    pool = FeaturePool()
    features = pool.compute(candles)
    log.info(f"Feature matrix: {features.shape}")

    # Drop rows where any feature is NaN
    valid_mask = ~np.any(np.isnan(features), axis=1)
    valid_indices = np.where(valid_mask)[0]
    log.info(f"Valid feature rows: {len(valid_indices)} / {len(features)}")

    if len(valid_indices) < 100:
        log.error("Too few valid rows for inference validation")
        return

    adapter = _TreeAdapter(tree)

    # 4. Test different hysteresis values
    hysteresis_values = [0.0, 0.10, 0.15, 0.20]
    hysteresis_results = []

    for hyst in hysteresis_values:
        log.info(f"Testing hysteresis={hyst:.2f} ...")
        inferencer = RegimeInferencer(adapter, config={
            'min_confidence': 0.0,
            'default_hysteresis': hyst,
            'transition_grace_candles': 5,
        })

        regimes = []
        confidences = []
        for idx in valid_indices:
            fv = features[idx]
            regime_id, conf, _probs = inferencer.classify(fv)
            regimes.append(regime_id)
            confidences.append(conf)

        transitions = inferencer.get_transition_log()
        unique_regimes = len(set(regimes))
        avg_conf = float(np.mean(confidences))

        row = {
            'hysteresis': hyst,
            'n_transitions': len(transitions),
            'unique_regimes': unique_regimes,
            'avg_confidence': round(avg_conf, 4),
            'transitions_per_1k': round(len(transitions) / (len(valid_indices) / 1000), 2),
        }
        hysteresis_results.append(row)
        log.info(f"  transitions={len(transitions)}, unique={unique_regimes}, "
                 f"avg_conf={avg_conf:.4f}")

    # 5. Confidence calibration: bin predictions by confidence
    log.info("Running confidence calibration with default hysteresis=0.15 ...")
    inferencer = RegimeInferencer(adapter, config={
        'min_confidence': 0.0,
        'default_hysteresis': 0.15,
        'transition_grace_candles': 5,
    })

    all_regimes = []
    all_confidences = []
    all_timestamps = []

    for idx in valid_indices:
        fv = features[idx]
        regime_id, conf, _probs = inferencer.classify(fv)
        all_regimes.append(regime_id)
        all_confidences.append(conf)
        all_timestamps.append(candles[idx, 0])

    all_confidences = np.array(all_confidences)

    # Bin by confidence
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    bin_labels = ['0.0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0']
    calibration = []

    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        mask = (all_confidences >= lo) & (all_confidences < hi)
        if i == len(bins) - 2:
            mask = (all_confidences >= lo) & (all_confidences <= hi)
        n_in_bin = int(mask.sum())
        if n_in_bin == 0:
            calibration.append({
                'bin': bin_labels[i],
                'count': 0,
                'avg_confidence': 0.0,
                'regime_stability': 0.0,
            })
            continue

        bin_regimes = [all_regimes[j] for j in range(len(all_regimes)) if mask[j]]
        # Regime stability = fraction of consecutive pairs that are the same regime
        same_count = sum(1 for k in range(1, len(bin_regimes))
                         if bin_regimes[k] == bin_regimes[k - 1])
        stability = same_count / max(len(bin_regimes) - 1, 1)

        calibration.append({
            'bin': bin_labels[i],
            'count': n_in_bin,
            'avg_confidence': round(float(all_confidences[mask].mean()), 4),
            'regime_stability': round(stability, 4),
        })

    # 6. Plots
    # 6a. Confidence calibration bar chart
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: calibration bars
    ax = axes[0]
    x_labels = [c['bin'] for c in calibration]
    counts = [c['count'] for c in calibration]
    stabilities = [c['regime_stability'] for c in calibration]

    x = np.arange(len(x_labels))
    width = 0.35
    bars1 = ax.bar(x - width / 2, counts, width, label='Count', color='steelblue', alpha=0.8)
    ax.set_ylabel('Count', color='steelblue')
    ax.set_xlabel('Confidence Bin')
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.set_title('Confidence Calibration')

    ax2 = ax.twinx()
    ax2.bar(x + width / 2, stabilities, width, label='Stability', color='coral', alpha=0.8)
    ax2.set_ylabel('Regime Stability', color='coral')
    ax2.set_ylim(0, 1.05)
    ax.legend(loc='upper left')
    ax2.legend(loc='upper right')

    # Right: regime timeline scatter
    ax = axes[1]
    ts_arr = np.array(all_timestamps)
    regime_arr = np.array([int(r) for r in all_regimes])
    conf_arr = np.array(all_confidences)

    # Subsample for readability
    step = max(1, len(ts_arr) // 5000)
    scatter = ax.scatter(
        ts_arr[::step], regime_arr[::step],
        c=conf_arr[::step], cmap='viridis', s=2, alpha=0.5,
    )
    plt.colorbar(scatter, ax=ax, label='Confidence')
    ax.set_xlabel('Timestamp')
    ax.set_ylabel('Regime ID')
    ax.set_title('Regime Timeline (validation 2024H2-2025H1)')

    savefig('42_inference_validation')
    log.info("Plot saved")

    # 7. Save results
    results = {
        'hysteresis_sweep': hysteresis_results,
        'calibration': calibration,
        'n_valid_bars': len(valid_indices),
        'n_leaves': tree.n_leaves,
        'n_macro': tree.n_macro,
    }
    save_results(results, '42_inference_validation')
    log.info("Results saved")

    # Summary
    log.info("=== Summary ===")
    for row in hysteresis_results:
        log.info(f"  hyst={row['hysteresis']:.2f}: "
                 f"transitions={row['n_transitions']}, "
                 f"per_1k={row['transitions_per_1k']}, "
                 f"avg_conf={row['avg_confidence']:.4f}")


if __name__ == '__main__':
    main()
