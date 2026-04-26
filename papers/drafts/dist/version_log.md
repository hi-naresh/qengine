# Version Log — IslandPilot Dissertation

Format: `[date] [file] — change summary`

---

## 2026-04-26 — Three flagged-for-compute gaps closed

- `appendix.md` — added Appendix H (Random-search Control), Appendix I (MI Fallback Ablation, regime-tree topology). Extended Appendix F with empirical baseline-rate paragraph for the pre-flight 10/20 criterion.
- `6_results.md` — added §6.8 "Random-search Control" body summary; added baseline-rate sentence to §6.7.
- Sources in `notebooks/validation_analyses/`:
  - `01_evolutionary_search_contribution.py` + `results/01_evolutionary_search_contribution.json`: N = 80 random genomes vs 63 trained islands, Cohen's d = 5.38, 0 / 80 exceed trained mean.
  - `02_regime_tree_feature_set_sensitivity.py` + `results/02_regime_tree_feature_set_sensitivity.json`: ARI(MI-only, fallback) = 0.034, NMI = 0.168, both trees structurally non-degenerate (CV 0.78 vs 0.68).
  - `03_preflight_criterion_discrimination.py` + `results/03_preflight_criterion_discrimination.json`: K = 60 random genomes, 0 OOS-profitable, Wilson-upper P(≥10/20) ≤ 6.6e-8.
- Reduced (no full GA re-run) for #2 / #3; full performance ablations explicitly deferred to future work.

## Pending / To Do

- [ ]