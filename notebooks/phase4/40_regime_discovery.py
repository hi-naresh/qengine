"""
Script 40 — Regime Discovery
=============================
Discovers market regimes via hierarchical GMM clustering on automatically
selected features.  Outputs: regime tree model, feature selector metadata,
diagnostic plots (feature importance, regime profiles, t-SNE map).

Part of Phase 4 (IslandPilot) research.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils import (
    load_candles, concat_candles, save_results, savefig,
    get_logger, MODELS_DIR, PLOTS_DIR,
)

import json
import numpy as np
import matplotlib.pyplot as plt

from qengine.framework.components.feature_selector import (
    FeaturePool, compute_feature_matrix, select_features,
)
from qengine.framework.components.regime_tree import RegimeTree

log = get_logger('40_regime_discovery')


# ── helpers ──────────────────────────────────────────────────────────────────

def _proxy_target(feature_matrix: np.ndarray, feature_names: list) -> np.ndarray:
    """Create a binary proxy target: top-20% NATR = positive class (1).

    If NATR is not in the feature set, fall back to ATR or the first
    volatility-like feature.
    """
    # Try to find natr_14 column
    natr_idx = None
    for i, name in enumerate(feature_names):
        if name == 'natr_14':
            natr_idx = i
            break
    if natr_idx is None:
        # Fallback: first feature with 'natr' or 'atr' in name
        for i, name in enumerate(feature_names):
            if 'natr' in name or 'atr' in name:
                natr_idx = i
                break
    if natr_idx is None:
        natr_idx = 0  # last resort

    vals = feature_matrix[:, natr_idx].copy()
    # Replace NaN with median so percentile works
    median_val = np.nanmedian(vals)
    vals[np.isnan(vals)] = median_val

    threshold = np.percentile(vals, 80)
    target = (vals >= threshold).astype(int)
    log.info(f"Proxy target built from '{feature_names[natr_idx]}', "
             f"threshold={threshold:.6f}, positive rate={target.mean():.2%}")
    return target


def _split_macro_sub(selected_indices, scores, feature_names, pool):
    """Split selected features into macro (volatility/trend/chop) and
    sub (momentum/structure) groups, picking top 5 of each."""
    categories = pool.categories
    macro_cats = {'volatility', 'trend', 'chop'}
    sub_cats = {'momentum', 'structure'}

    # Build category lookup: feature_name -> category
    name_to_cat = {}
    for cat, names in categories.items():
        for n in names:
            name_to_cat[n] = cat

    macro_indices = []
    sub_indices = []
    macro_scores = []
    sub_scores = []

    for idx, score in zip(selected_indices, scores):
        fname = feature_names[idx]
        cat = name_to_cat.get(fname, 'unknown')
        if cat in macro_cats:
            macro_indices.append(idx)
            macro_scores.append(score)
        elif cat in sub_cats:
            sub_indices.append(idx)
            sub_scores.append(score)

    # Take top 5 each
    macro_indices = macro_indices[:5]
    macro_scores = macro_scores[:5]
    sub_indices = sub_indices[:5]
    sub_scores = sub_scores[:5]

    # If either group is empty, fill from the other
    if not macro_indices:
        macro_indices = selected_indices[:5]
        macro_scores = scores[:5]
    if not sub_indices:
        sub_indices = selected_indices[:5]
        sub_scores = scores[:5]

    return macro_indices, macro_scores, sub_indices, sub_scores


# ── plots ────────────────────────────────────────────────────────────────────

def plot_feature_importance(feature_names, selected_indices, scores):
    """Bar chart of selected feature MI scores."""
    names = [feature_names[i] for i in selected_indices]
    fig, ax = plt.subplots(figsize=(10, 5))
    y_pos = np.arange(len(names))
    ax.barh(y_pos, scores, color='steelblue', edgecolor='navy', linewidth=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel('Mutual Information Score')
    ax.set_title('Feature Importance (MI with NATR proxy target)')
    savefig('40_feature_importance')
    log.info("Saved feature importance plot")


def plot_regime_profiles(profiles, feature_names, selected_indices):
    """Heatmap of regime mean feature values (z-scored)."""
    regime_ids = sorted(profiles.keys())
    sel_names = [feature_names[i] for i in selected_indices]
    n_regimes = len(regime_ids)
    n_feats = len(sel_names)

    mat = np.zeros((n_regimes, n_feats))
    for r_idx, rid in enumerate(regime_ids):
        prof = profiles[rid]
        for f_idx, fname in enumerate(sel_names):
            mat[r_idx, f_idx] = prof.get(fname, 0.0)

    # Z-score columns for better visual contrast
    col_mean = mat.mean(axis=0)
    col_std = mat.std(axis=0)
    col_std[col_std < 1e-12] = 1.0
    mat_z = (mat - col_mean) / col_std

    fig, ax = plt.subplots(figsize=(12, max(4, n_regimes * 0.6)))
    im = ax.imshow(mat_z, aspect='auto', cmap='RdYlBu_r')
    ax.set_xticks(range(n_feats))
    ax.set_xticklabels(sel_names, rotation=45, ha='right', fontsize=8)
    ax.set_yticks(range(n_regimes))
    ax.set_yticklabels([f"Regime {rid}" for rid in regime_ids], fontsize=9)
    ax.set_title('Regime Profiles (z-scored feature means)')
    plt.colorbar(im, ax=ax, label='z-score')
    savefig('40_regime_profiles')
    log.info("Saved regime profiles heatmap")


def plot_tsne(feature_matrix, labels, selected_indices, n_samples=5000):
    """t-SNE scatter plot of regime assignments, subsampled for speed."""
    try:
        from sklearn.manifold import TSNE
    except ImportError:
        log.info("sklearn not available, skipping t-SNE plot")
        return

    # Use only selected features, drop NaN rows
    X = feature_matrix[:, selected_indices]
    mask = ~np.any(np.isnan(X), axis=1)
    X_clean = X[mask]
    labels_clean = labels[mask]

    n = len(X_clean)
    if n < 50:
        log.info("Too few valid samples for t-SNE, skipping")
        return

    # Subsample
    if n > n_samples:
        rng = np.random.RandomState(42)
        idx = rng.choice(n, size=n_samples, replace=False)
        X_clean = X_clean[idx]
        labels_clean = labels_clean[idx]

    log.info(f"Running t-SNE on {len(X_clean)} samples...")
    tsne = TSNE(n_components=2, random_state=42, perplexity=30, n_iter=1000)
    embedding = tsne.fit_transform(X_clean)

    unique_labels = np.unique(labels_clean)
    fig, ax = plt.subplots(figsize=(10, 8))
    cmap = plt.cm.get_cmap('tab10', len(unique_labels))
    for i, lid in enumerate(unique_labels):
        mask_l = labels_clean == lid
        ax.scatter(embedding[mask_l, 0], embedding[mask_l, 1],
                   c=[cmap(i)], label=f"Regime {int(lid)}", alpha=0.5, s=8)
    ax.set_title('t-SNE Regime Map')
    ax.set_xlabel('t-SNE 1')
    ax.set_ylabel('t-SNE 2')
    ax.legend(fontsize=7, ncol=2, loc='best')
    savefig('40_tsne_regime_map')
    log.info("Saved t-SNE regime map")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("="*60)
    log.info("Script 40 — Regime Discovery")
    log.info("="*60)

    # 1. Load train candles (2020-2024H1)
    log.info("Loading EUR-USD 5m train candles (2020-2024H1)...")
    warmup, trading = load_candles(
        start_date='2020-01-01', end_date='2024-06-30',
        warmup_candles_num=500,
    )
    candles = concat_candles(warmup, trading)
    log.info(f"Candles shape: {candles.shape}")

    # 2. Compute full feature pool
    log.info("Computing feature matrix...")
    pool = FeaturePool()
    feature_matrix, feature_names = compute_feature_matrix(candles, pool)
    log.info(f"Feature matrix: {feature_matrix.shape}, features: {feature_names}")

    # 3. Create proxy target (top 20% NATR = positive class)
    target = _proxy_target(feature_matrix, feature_names)

    # 4. Select top features via mutual information
    log.info("Running feature selection (MI)...")
    selected_indices, scores = select_features(feature_matrix, target, k=10)
    log.info(f"Selected {len(selected_indices)} features:")
    for idx, score in zip(selected_indices, scores):
        log.info(f"  {feature_names[idx]:25s}  MI={score:.4f}")

    # 5. Split into macro and sub features
    macro_idx, macro_scores, sub_idx, sub_scores = _split_macro_sub(
        selected_indices, scores, feature_names, pool,
    )
    log.info(f"Macro features ({len(macro_idx)}): "
             f"{[feature_names[i] for i in macro_idx]}")
    log.info(f"Sub features   ({len(sub_idx)}): "
             f"{[feature_names[i] for i in sub_idx]}")

    # Save feature selector metadata
    selector_info = {
        'all_feature_names': feature_names,
        'selected_indices': selected_indices,
        'selected_names': [feature_names[i] for i in selected_indices],
        'scores': scores,
        'macro_indices': macro_idx,
        'macro_names': [feature_names[i] for i in macro_idx],
        'macro_scores': macro_scores,
        'sub_indices': sub_idx,
        'sub_names': [feature_names[i] for i in sub_idx],
        'sub_scores': sub_scores,
    }
    selector_path = save_results(selector_info, 'feature_selector', subdir='models')
    log.info(f"Feature selector saved to {selector_path}")

    # 6. Build hierarchical RegimeTree
    log.info("Fitting RegimeTree (macro + sub GMM)...")
    # Drop NaN rows for tree fitting
    valid_mask = ~np.any(np.isnan(feature_matrix[:, selected_indices]), axis=1)
    X_valid = feature_matrix[valid_mask]
    log.info(f"Valid samples for tree fitting: {valid_mask.sum()} / {len(feature_matrix)}")

    tree = RegimeTree(min_leaf_samples=200, max_macro=10, max_sub=8)
    tree.fit(X_valid, macro_features=macro_idx, sub_features=sub_idx)
    log.info(f"RegimeTree: {tree.n_macro} macro clusters, {tree.n_leaves} leaves")
    log.info(f"Leaf IDs: {tree.leaf_ids}")
    log.info(f"Leaf sample counts: {tree.leaf_sample_counts}")

    # Save tree
    tree_path = str(MODELS_DIR / 'regime_tree.pkl')
    tree.save(tree_path)
    log.info(f"Regime tree saved to {tree_path}")

    # 7. Classify all samples — build regime profiles
    log.info("Classifying all samples and building regime profiles...")
    all_labels = np.full(len(feature_matrix), -1, dtype=int)
    for i in range(len(feature_matrix)):
        if not valid_mask[i]:
            continue
        lid, conf = tree.classify_best(feature_matrix[i])
        all_labels[i] = lid

    # Build profiles: mean feature value per regime per selected feature
    profiles = {}
    for lid in tree.leaf_ids:
        mask_lid = all_labels == lid
        if mask_lid.sum() == 0:
            profiles[lid] = {feature_names[si]: 0.0 for si in selected_indices}
            continue
        prof = {}
        for si in selected_indices:
            vals = feature_matrix[mask_lid, si]
            vals_clean = vals[~np.isnan(vals)]
            prof[feature_names[si]] = float(np.mean(vals_clean)) if len(vals_clean) > 0 else 0.0
        profiles[lid] = prof

    for lid in tree.leaf_ids:
        count = int((all_labels == lid).sum())
        log.info(f"  Regime {lid}: {count} samples "
                 f"({count/valid_mask.sum()*100:.1f}%)")

    # 8. Plots
    log.info("Generating plots...")
    plot_feature_importance(feature_names, selected_indices, scores)
    plot_regime_profiles(profiles, feature_names, selected_indices)
    plot_tsne(feature_matrix, all_labels, selected_indices, n_samples=5000)

    # 9. Save results
    results = {
        'n_candles': int(candles.shape[0]),
        'n_valid': int(valid_mask.sum()),
        'n_features_total': len(feature_names),
        'n_features_selected': len(selected_indices),
        'selected_features': [feature_names[i] for i in selected_indices],
        'mi_scores': {feature_names[i]: s for i, s in zip(selected_indices, scores)},
        'macro_features': [feature_names[i] for i in macro_idx],
        'sub_features': [feature_names[i] for i in sub_idx],
        'n_macro_clusters': tree.n_macro,
        'n_leaves': tree.n_leaves,
        'leaf_ids': tree.leaf_ids,
        'leaf_sample_counts': {str(k): v for k, v in tree.leaf_sample_counts.items()},
        'leaf_map': {str(k): list(v) for k, v in tree._leaf_map.items()},
        'regime_profiles': {str(k): v for k, v in profiles.items()},
    }
    save_results(results, '40_regime_discovery')
    log.info("Results saved to 40_regime_discovery.json")
    log.info("Done.")


if __name__ == '__main__':
    main()
