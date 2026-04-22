# Anomalies — Unexplained Behaviors

Results with no explanation yet. These are the raw material for `09_synthesis/01_novel_findings.md`.

Format:
```
## [YYYY-MM-DD] <Title>
**Source:** script path that produced this
**What happened:** Description
**What we tried:** Hypotheses tested and ruled out
**Status:** open | resolved (link to explanation)
```

---

## [2026-04-22] Effective bust level inversely correlated with sizing_factor
**Source:** `03_margin_mechanics/02_implicit_forced_close.py`

**What happened:** With max_levels=8 configured and 0 margin calls, busts occur at:
- sf=1.5: level 7 (avg 6.97, max 7)
- sf=2.0: level 6 (avg 6.0, max 6)  
- sf=2.5: level 5 (avg 4.95, max 5)

Effect is consistent across ALL equity levels ($1k–$10k). The configured max_levels=8 appears to not control the actual bust level for sf=2.0 and sf=2.5.

**What we tried:**
- Ruled out margin calls (0/1200 bust events show margin_call or margin_bust outcome)
- Ruled out equity effects (result is identical at $1k and $10k)
- Code inspection: found `_max_affordable_levels()` in `strategies/_admin/Martingale/__init__.py` line 481

**Status:** resolved — The strategy computes `effective_max_levels = min(configured_max, affordable)` at session start. For high sf values, the geometric position sizes grow so fast that the account can only afford ~5-7 levels at the available leverage. sf=2.5 with 0.5% base size at level 6 = 2.5^6 × 0.5% = 15.3% position per level — the margin math caps affordability below the configured 8 levels. This is a designed safety feature (pre-session margin feasibility check) that prevents entering a session the account can't fund to completion. The 0 margin calls is consistent: sessions only start if they can be fully funded, so the effective bust level is capped at the affordable depth, not the configured depth.

---

## [2026-04-22] Conservative config (sf=1.5, ml=4) has 6x higher bust rate than aggressive (sf=2.0, ml=8)
**Source:** `01_finite_capital/03_capital_boundary.py`

**What happened:** "Conservative" parameterization produces bust_rate=0.096 vs "aggressive" at 0.016. This is counter-intuitive — smaller position sizes and fewer maximum levels should mean less risk.

**What we tried:**
- Confirmed it's equity-invariant (same result at all tested equity levels)
- Hypothesis: lower max_levels limits recovery opportunities. At ml=4, cycles that would recover at level 5-7 are counted as busts. Verified: bust_rate decreases monotonically as ml increases (from sizing×levels sweep).

**Status:** resolved — lower max_levels increases bust rate because more potential recovery cycles are classified as busts before recovery can occur. "Conservative" only reduces bust magnitude, not frequency. True risk metric is expected loss per session = N × bust_rate.
