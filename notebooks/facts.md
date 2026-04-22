# Known Facts — Research Firewall

Any result listed here is established in academic literature. Do NOT re-derive or re-validate these. If an experiment would only confirm a fact below, skip it and design a deeper question.

## Martingale / Gambler's Ruin

- **Infinite capital convergence**: With unlimited capital and a positive edge, a martingale strategy wins with probability 1 (classical gambler's ruin result).
- **Finite capital ruin**: With finite capital B and a fair or negative game, ruin probability = 1 as number of rounds → ∞.
- **Ruin probability formula** (unfair game, finite capital): P(ruin) = (1 - (p/q)^B) / (1 - (p/q)^(B+G)) where p=win prob, q=1-p, B=current capital, G=goal.
- **Expected duration to ruin/goal**: Finite and computable under IID assumptions.
- **Geometric sizing exposure**: With sizing factor f and N levels, total exposure = f^0 + f^1 + ... + f^(N-1) = (f^N - 1)/(f - 1). At f=2, N=8: 255x base.
- **Kelly criterion**: Optimal bet fraction = (bp - q) / b where b = payout ratio. Over-betting Kelly leads to long-run ruin.

## Cost Model (abstract)

- **Spread reduces edge**: Each round trip costs 2×spread. Net edge = gross edge - 2×spread.
- **Compounding cost**: In a multi-level system, spread is paid at each level entry. Total spread cost = sum of position sizes × spread per unit.
- **Negative swap** (carry cost): Holding positions overnight incurs swap charges. Longer hold time = higher total swap cost.

## General Strategy Properties

- **Busts are rare but large**: In a positive-edge martingale, most cycles win small; rare cycles hit max depth and produce large losses. The asymmetry is structural.
- **Win rate vs payout asymmetry**: High win rate with catastrophic tail loss is the fundamental shape of martingale P&L distribution.
- **N-to-1 abstract ratio**: 1 bust at level N erases approximately (bust_loss / avg_win) wins. Exact value depends on configuration — NOT studied as a function of HPs in literature.
