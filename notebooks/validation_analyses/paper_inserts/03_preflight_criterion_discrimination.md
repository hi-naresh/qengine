### Pre-flight criterion baseline rate

The pre-flight architectural-validation criterion ("at least 10 of the top
20 genomes are OOS-profitable on the 3-month validation window", §5.6 /
Appendix F) is positioned as a structural-bug detector, not a calibrated
performance test. To bound its discrimination power we estimated the
false-positive rate empirically. K = 60 genomes were sampled uniformly
from the production gene bounds (the same bounds returned by
`build_gene_bounds_from_strategy(Martingale)` that the trainer uses to
seed Iteration 2 island populations) and each was evaluated on the same
2024-04-01 to 2024-06-30 OOS window via the same `qengine.research.backtest`
API and the same profitability rule used by `validate_model.py`
(`n_sessions ≥ 3` AND `net_pnl > 0` AND `bust_rate < 0.40`).

| Metric                                                   | Value                                  |
|----------------------------------------------------------|----------------------------------------|
| Random genomes evaluated (K)                             | 60                                     |
| Profitable                                               | 0 / 60                                 |
| Losing                                                   | 9 / 60                                 |
| Too few sessions (< 3)                                   | 50 / 60                                |
| Flat (zero net P&L)                                      | 1 / 60                                 |
| Errored                                                  | 0 / 60                                 |
| Per-genome profitability rate (p̂)                       | 0.000                                  |
| 95% Wilson confidence interval for p                     | [0.000, 0.060]                         |
| P(≥10 of 20 random genomes profitable), closed form     | 0 (point estimate)                     |
| P(≥10 of 20 random genomes profitable), Wilson upper    | 6.6 × 10⁻⁸ (at p = 0.060)              |
| P(≥10 of 20 random genomes profitable), bootstrap (1000×, n=20) | 0.000                          |
| Verdict on criterion strength                            | Strong (defensible as bug detector)    |

Zero of the 60 random genomes were OOS-profitable. With the observed
upper bound on the random profitability rate (p ≤ 0.060 at 95%
confidence), the probability that 20 random genomes contain ≥10
profitable is bounded above by 6.6 × 10⁻⁸. The 13/20 result reported
for Iteration 2 (Appendix F) therefore reflects genuine training signal
rather than a coin-flip-level threshold: under the null of uniform-random
genome sampling, the criterion is essentially never satisfied. The
criterion is appropriately positioned in the manuscript as an architectural
correctness check rather than a performance test, and the present analysis
substantiates that positioning. The dominant random-genome failure mode
was insufficient activity (50/60 produced fewer than three sessions
across the 64-day window), reflecting the joint feasibility constraints
imposed at gene-bounds construction time (§3.4) — random parameter draws
within those bounds frequently produce strategies that satisfy the
ruin-prevention bounds but rarely fire entries on real EUR-USD candles.

We also note a minor convention discrepancy: `validate_model.py`'s CLI
defaults to `--top-n 10` whereas the paper text in §5.6 specifies
"10 of top 20". Both Iteration 2 production pre-flight runs reported in
Appendix F used the 20-genome convention; the script default has been
left as 10 for backward compatibility with earlier Iteration 1 invocations
and is overridable per-run.

**Limitations.** This baseline was estimated on a single OOS window
(2024 Q2), a single instrument (EUR-USD 5m), and modest K (60). The
estimate measures the criterion's discrimination power *given* the
production sample distribution (the gene bounds are themselves designed
for viability), not against arbitrary parameter chaos. The analysis
nonetheless rules out the most obvious reviewer concern — that the
criterion might be passable by random parameter draws — by a margin of
roughly seven orders of magnitude, and the wide separation between the
random-pass probability (≤ 10⁻⁷) and a naive 50% threshold means the
qualitative conclusion is robust to plausible variation in the profitability
rule (e.g. tightening the bust-rate cap or raising the minimum-session
floor would only further depress the random pass rate).
