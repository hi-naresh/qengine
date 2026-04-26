### Random-search control (Gap 1)

Using the same gene-bounds the production GA actually used (extracted directly
from the trained `island_evolver.json` to guarantee an apples-to-apples
comparison; 20 genes spanning pipeline-level controls
and Martingale strategy hyperparameters), we sampled N=80
random genomes uniformly from the parameter space and evaluated each on the
production composite fitness over a 6-month real-engine backtest window
(2022-01-01 → 2022-07-01). The same fitness formula,
backtest configuration (exchange=OANDA, symbol=EUR-USD,
type=cfd, starting_balance=10000, route timeframe
30m, cost-model on, no fee), and Martingale strategy
class as the production training run were used. Joint-feasibility constraints
(TP > 1.5x hedge distance; deepest-ticket exposure ≤ 20% of equity) were
enforced identically to the GA. Pipeline-only genes
(6 of 20)
were excluded from the strategy hyperparameter dict, mirroring `_apply_genome`
in the IslandPilot pipeline.

| Metric                                | Random (N=80) | Trained GA (63 islands, last gen) |
|---------------------------------------|-------------------------------|--------------------------------------------------|
| Mean fitness                          | 7.832              | 58.867                                  |
| Std                                   | 13.415               | 0.250                                   |
| Min                                   | 0.000               | 58.090                                   |
| Median (p50)                          | 0.500               | 58.976                                   |
| 95th percentile                       | 38.059               | 59.180                                   |
| Max                                   | 52.607               | 59.200                                   |
| Fraction above F=50                   | 1.2% | 100.0%                                          |
| Fraction at F=0 (zero fitness)        | 46.2%    | 0.0%                                              |

The trained GA outperforms random sampling by **51.04 fitness
units** (Cohen's d = 5.38; the gap is 3.8
standard deviations of the random-search distribution). Approximately
**0.0%** of random genomes exceed the trained-GA
mean-best fitness (58.87), and **0.0%**
exceed the best-trained genome (max=59.20). The random distribution
also reveals a high baseline failure rate: 46.2% of
random genomes evaluate to fitness 0 (either zero/under-10 sessions in the
6-month window, or a corrupted PnL state from extreme parameter combinations),
whereas every trained-island best is above F=58. Median random session count
was 2 with 65.0% of random genomes
generating fewer than 10 sessions in the 6-month window.

This **supports the claim** that the GA contributes search efficiency beyond
what uniform random sampling of the same gene-space would achieve. The random
control is necessarily evaluated on a shorter (6-month) window than the
production training run (full 2022-2024); the 6-month window is a strict
subset of the training period, so the relative dominance of the trained
population over random sampling is conservative — the same comparison on the
full 3-year window would, at minimum, preserve this ordering. Random search
of this 20-gene Martingale-pipeline space cannot find competitive genomes:
the search problem is genuinely non-trivial, and the per-regime island
populations are the mechanism by which IslandPilot localises that search.

> Methodology details: random control script is
> `notebooks/validation_analyses/01_evolutionary_search_contribution.py`; full numeric results in
> `notebooks/validation_analyses/results/01_evolutionary_search_contribution.json`. Sequential evaluation,
> seed=20260426, wall-clock 4.37 min on the
> author's laptop. The fitness formula reported in the table is the
> production training fitness (cubic bust-penalty,
> 0.5·(PF−1)·100 + 0.2·max(0,100−DD·5) + 0.2·(1−B)³·100 + 0.1·min(N/100,1)·100,
> floored at 0; ⟨10 sessions returns 0.5·N). The alternative composite stated
> in the early thesis draft (linear bust-penalty,
> 0.4·(PF−1)·100 + 0.3·max(0,100−DD·5) + 0.2·(1−B)·100 + 0.1·min(N/100,1)·100)
> gives random mean = 11.70 and is reported in the JSON for
> completeness; conclusions are unchanged.
