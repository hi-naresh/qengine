# Version Log — IslandPilot Dissertation

Format: `[date] [file] — change summary`

---

## v1.0 — 2026-04-22 — Initial split from dist.md

- Split monolithic `dist.md` into per-section files in `papers/drafts/dist/`
- No content changes from the split itself

---

## v0.9 — 2026-04-22 — Pre-split fixes applied to dist.md

### title_abstract.md
- **NEW paragraph**: Extended OOS (2025-2026) multi-system comparison added to abstract
  - GTSBotPilot -47.0% (+32.6pp), FinRLPilot -40.7%, IslandPilot -83.0% (-3.4pp)
  - Temporal decay explanation: positive transfer ≤12 months, negative 12-27 months
  - Quarterly retraining cadence recommendation

### 5_experimental_setup.md
- **Section renumbered**: "5.4 Spread Model" → "5.5 Spread Model" (was duplicate of 5.4 Comparison Systems)
- **Duplicate paragraph removed**: Stale `**Baseline.**` paragraph at end of spread model section removed (now covered in 5.4 Comparison Systems)

### 6_results.md
- **NEW section 6.7**: Extended OOS evaluation (2025-2026), Table 8 with all 4 systems (real backtest results)
  - Baseline: 1,439 sessions, 84.2% win, 228 busts, PF 0.782, -79.6% net
  - IslandPilot: 1,438 sessions, 83.4% win, 238 busts, PF 0.742, -83.0% net
  - GTSBotPilot: 605 sessions, 84.0% win, 84 busts, PF 0.769, -47.0% net
  - FinRLPilot: 1,086 sessions, 55.1% win, 211 busts, PF 0.762, -40.7% net
- **NEW section 6.8**: Session Win Rate Paradox (renumbered from old 6.7)

### 7_discussion.md
- **Section 7.5 expanded**: Real comparison numbers for GTSBotPilot (+32.6pp via 58% session reduction) and FinRLPilot (-40.7% best net, 55.1% win rate), architectural differentiation
- **Section 7.6 expanded**: Table 9 (temporal degradation across all periods), threshold analysis (12-15 months), 33% IS-gain retention rate

### 8_conclusion.md
- **NEW paragraph**: 2025-2026 extended OOS summary (GTSBotPilot, FinRLPilot, IslandPilot negative transfer, quarterly cadence)
- **NEW paragraph**: Three conclusions from combined evidence (retraining constraint, activity vs gating trade-off, evolutionary budget)

### ack_decl_data_useAI.md
- **Fixed**: "5-minute resolution" → "30-minute resolution" in Data Availability Statement

### references.md
- **Added**: Liu et al. (2020) FinRL full citation
- **Added**: Rundo et al. (2019) GTSBot full citation
- **Added**: Zhang et al. (2020) AutoAlpha citation

---

---

## v1.1 — 2026-04-22 — Stats update + WHY justification (training 2022-2024, 5m TF, OOS +1.95%)

### 5_experimental_setup.md
- **Timeframe changed**: 30m → 5m throughout; justification added (105k bars/year, intraday cycle capture)
- **Training period extended**: 2022–2023 (24 months) → 2022–2024 (36 months)
- **Training window rationale rewritten**: updated for 5m bar count, three-phase market cycle coverage, genetic evolution depth
- **Evaluation table updated**: removed 2024 H1/H2/Full as OOS (now training data); primary OOS is 2025-01-01 to 2026-04-01
- **Section 5.2 strategy config rewritten**: updated baseline config (EMA 5/15 capable, hedge=20, tp=50, max_levels=3, sf=1.7, mcb=2); documents the PHASE6 expansion of `_TUNABLE_GROUPS` to include Entry Signal, Filters, Risk Management, Position Management

### 4_training_methodology.md
- **Training period updated**: "2-year window (2022-2023)" → "3-year window (2022-2024)"
- **NEW paragraph**: explains the `_TUNABLE_GROUPS` expansion as the key architectural change enabling positive OOS performance; notes that restricting to sizing/grid prevents expectancy engineering

### 6_results.md
- **Section 6.7 completely rewritten**: new numbers — IslandPilot +1.95% net / PF 3.72 vs baseline -76.52% / PF ~0.77; all comparison systems in PF 0.7–0.85 range; mechanistic context for baseline loss added
- **NEW Section 6.9**: Mechanism Analysis — three-mechanism explanation for PF 3.72 (expectancy engineering via signal selection, depth capping, adaptive sizing); why max DD drastically reduced; why improvement concentrates in PF rather than session count
- Section 6.8 renumbered from previous 6.8 (now 6.8 after inserting 6.9 before it) [note: ordering may need review]

### 7_discussion.md
- **Section 7.1 rewritten**: "modest improvement" narrative replaced with "positive OOS transfer under full-parameter evolution"; references PF 3.72 result and mechanism
- **Section 7.3 rewritten**: "pipeline cannot transform losing strategy" → "pipeline CAN transform via regime-conditioned signal selection"; full mechanistic account of how 2-pip spread is overcome
- **Section 7.6 rewritten**: old negative-transfer degradation table removed; new table shows +78.47pp OOS delta; discussion of why structural features generalise to OOS period

---

## Pending / To Do

- [ ] Verify abstract word count is within journal limits
- [ ] Cross-check all table numbers are sequential after section additions
- [ ] Confirm Rundo et al. (2019) and Liu et al. (2020) DOIs are correct
- [ ] Add Figure captions to figures that are referenced but image files not yet finalised
- [ ] Supervisor review: focus areas → `6_results.md` (new Table 8), `7_discussion.md` (Section 7.5/7.6 additions)
