# Dist-Folder Review Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute a two-phase (critique, then apply) iterative review across every file in `papers/drafts/dist/` so the draft meets an applied/systems-tier journal bar while retaining the theoretical grounding expected of a dissertation. Each section is reviewed until all CRITICAL issues are resolved and the user ships it.

**Architecture:** The orchestrator (main conversation) drives a per-section loop. For each section it dispatches two parallel subagents (citation-verifier and fact-checker), merges findings with an inline scan for writing quality and WHY-gaps, presents a structured critique report, collects user approval decisions, applies approved edits in-place with synchronised `references.md` updates, and re-reviews. A soft cap of 3 re-review rounds per section prevents infinite loops.

**Tech stack:** No new code. This is an execution playbook using `Read`, `Edit`, `Write`, `Bash`, `Agent` (subagents), `WebFetch`, `WebSearch` tools. Working artefacts: `.review_log.md` (decisions audit) and `.citation_cache.json` (verification cache), both inside `papers/drafts/dist/`.

**Referenced spec:** `docs/superpowers/specs/2026-04-24-dist-review-agent-design.md` (commit `ad17629c`).

---

## Task 0: Bootstrap working files and foundational-allowlist

**Files:**
- Create: `papers/drafts/dist/.review_log.md`
- Create: `papers/drafts/dist/.citation_cache.json`
- Create: `papers/drafts/dist/.foundational_allowlist.txt`

- [ ] **Step 1: Create `.review_log.md` with an audit-log header.**

Content:
```markdown
# Dist Review Log

Per-section record of critique items, user decisions, and re-review rounds.
Items use ID format `S{section}-{ID}` matching the critique report.
Severity: CRITICAL | MAJOR | MINOR. Decision: accepted | rejected | deferred | modified.

---
```

- [ ] **Step 2: Create `.citation_cache.json` with empty structure.**

Content:
```json
{
  "version": 1,
  "entries": {}
}
```

Key format when populated: `"author_slug:year:title_slug"` (e.g. `"nystrup:2020:learning_hidden_markov_models"`).

- [ ] **Step 3: Create `.foundational_allowlist.txt` listing works that get existence-only verification.**

Content (one per line, `Author Year`):
```
Hamilton 1989
Schwarz 1978
Doob 1953
Goldberg 1989
Goldberg Deb 1991
Whitley Rana Heckendorn 1999
Wright 1931
Dempster Laird Rubin 1977
Box Jenkins 1976
Cont 2001
Engle 1982
Hurst 1951
McLachlan Peel 2000
Eiben Smith 2015
Wilder 1978
Kaufman 2013
Bollinger 2002
Chande 1997
Lambert 1983
Lane 1984
Syswerda 1989
Lo MacKinlay 1988
Astrom Murray 2008
Bank for International Settlements 2022
```

- [ ] **Step 4: Add the three working files to `.gitignore` so they are not committed as dissertation artefacts.**

Append to `/Users/naresh/Documents/Research/qengine/.gitignore` (read it first, then add):
```
# Dist review tooling (ephemeral working state)
papers/drafts/dist/.review_log.md
papers/drafts/dist/.citation_cache.json
papers/drafts/dist/.foundational_allowlist.txt
```

- [ ] **Step 5: Verify primary sources of truth are accessible.**

Run, expect all paths to resolve:
```bash
ls /Users/naresh/.claude/projects/-Users-naresh-Documents-Research-qengine/memory/phase6_islandpilot_retrain.md \
   /Users/naresh/.claude/projects/-Users-naresh-Documents-Research-qengine/memory/phase2_results.md \
   /Users/naresh/Documents/Research/qengine/notebooks/RESEARCH.md \
   /Users/naresh/Documents/Research/qengine/pipelines/_shared/IslandPilot
```

- [ ] **Step 6: Commit bootstrap.**

```bash
cd /Users/naresh/Documents/Research/qengine
git add .gitignore
git commit -m "chore: ignore dist review working files"
```

The three working files themselves stay untracked.

---

## Task Template: Per-Section Review Loop

Tasks 1 through 12 all follow the same structure. This template is referenced from each section-specific task below to avoid duplication. The section-specific tasks add pointers to primary sources, expected cross-reference targets, and section-specific review emphases.

**Generic per-section steps (expand these under each section task):**

- [ ] **S.1: Read the section file and cross-reference context.**

For section N, read:
- `papers/drafts/dist/<section-file>.md` (full file)
- `papers/drafts/dist/0_title_abstract.md` (for numeric and framing consistency)
- Any previously-shipped sections referenced by this one

- [ ] **S.2: Extract the citation list.**

Scan the section text for every `(Author, Year)` and `(Author, Year; Author, Year)` pattern. Build a list: `[(author, year, sentence_context, line_number)]`. Include all inline citations even if they are well-known.

- [ ] **S.3: Extract the claim list.**

Scan for claims that need factual verification:
- Numeric results: profit factor, drawdown, win rate, trade counts, durations, percentages, dates, asset identifiers
- Engineering claims: engine behaviour, exchange specifics, execution-model details, strategy internals
- Cross-section claims: anything that must match another section's wording

- [ ] **S.4: Dispatch citation-verifier subagent (parallel with S.5).**

Use `Agent` tool with `subagent_type: general-purpose`. Prompt template:

> You are verifying citations for a journal-paper review. For each citation below, check (a) the paper exists and the author/year are correct, (b) the paper's abstract supports the claim it is being cited for. Use WebSearch and WebFetch as needed.
>
> **Foundational works allowlist** (existence-only check, skip claim-alignment): <paste contents of `.foundational_allowlist.txt`>
>
> **Cache lookup first:** read `papers/drafts/dist/.citation_cache.json`. For each citation, construct the key `author_slug:year:title_slug`. If the key exists and its cached `citing_sentence_hash` matches the current one, reuse the cached verdict. Otherwise verify and update the cache.
>
> **Cache update:** after verifying each non-cached citation, append its verdict to the cache file. Use atomic write (read, modify, write whole file).
>
> **Return per citation (JSON):**
> ```json
> {
>   "citation": "<as cited>",
>   "verdict": "VERIFIED | EXISTS-CLAIM-MISMATCH | NOT-FOUND | FOUNDATION-TRUSTED | UNCLEAR",
>   "evidence": "<short note>",
>   "url": "<source URL or empty>",
>   "full_reference": "<canonical bibliographic record>",
>   "doi": "<DOI if available>",
>   "citing_sentence": "<the sentence from the draft>",
>   "claim_alignment_note": "<does the paper support the claim>"
> }
> ```
>
> **Verdicts without a URL (non-foundational) are downgraded to UNCLEAR.**
>
> Citations to verify: <paste list from S.2>

Run in foreground (need results to compile critique). Token budget: this is the expensive step; let it run.

- [ ] **S.5: Dispatch fact-checker subagent (parallel with S.4).**

Use `Agent` tool with `subagent_type: Explore`. Prompt template:

> You are verifying factual claims for a journal-paper review. Cross-check each claim below against the primary sources. Return a verdict per claim.
>
> **Primary sources (read as needed):**
> - `/Users/naresh/.claude/projects/-Users-naresh-Documents-Research-qengine/memory/phase6_islandpilot_retrain.md`
> - `/Users/naresh/.claude/projects/-Users-naresh-Documents-Research-qengine/memory/phase2_results.md`
> - `/Users/naresh/.claude/projects/-Users-naresh-Documents-Research-qengine/memory/engine_changes.md`
> - `/Users/naresh/.claude/projects/-Users-naresh-Documents-Research-qengine/memory/real_engine_evolution.md`
> - `/Users/naresh/Documents/Research/qengine/notebooks/RESEARCH.md`
> - `/Users/naresh/Documents/Research/qengine/pipelines/_shared/IslandPilot/` (code)
> - `/Users/naresh/Documents/Research/qengine/strategies/` (code)
>
> **Return per claim (JSON):**
> ```json
> {
>   "claim": "<verbatim from draft>",
>   "type": "NUMERIC-RESULT | ENGINEERING-DETAIL | CROSS-SECTION-CONSISTENCY",
>   "verdict": "MATCHES-SOURCE | MISMATCH | UNSOURCED | OUTDATED",
>   "source": "<path>",
>   "source_value": "<what the source says>",
>   "draft_value": "<what the draft says>",
>   "note": "<reconciliation note>"
> }
> ```
>
> If a memory file and a notebook disagree, flag OUTDATED and report both values. Do not guess.
>
> Claims to check: <paste list from S.3>

Run in parallel with S.4 via a single message containing both `Agent` calls.

- [ ] **S.6: Inline scan (while subagents run).**

While waiting, the orchestrator scans the section for the cheaper issues. Produce an inline issue list with the same item format. Look for:

- **PROBLEM-FORMULATION gaps** (Section 1 especially): claims about market non-stationarity, regime existence, Martingale risk profile. Are they backed by citations?
- **METHODOLOGY-JUSTIFICATION gaps**: every design choice where an alternative exists. Examples: why GMM vs HMM, why BIC vs AIC vs cross-validation, why ring topology vs star/random, why mutual information vs correlation for feature selection, why EMA crossover vs other entry signals, why hysteresis over simple threshold, why 5-minute timeframe vs other resolutions, why OANDA vs other brokers, why 36-month training window vs other windows, why sqrt(2) multiplier vs other progressions.
- **WHY-EXPLANATION gaps** (Section 7 especially): each headline number should have a causal explanation. Is "PF 3.72" just asserted or does the text explain what mechanism produced it?
- **THEORETICAL-GROUNDING gaps**: missing connections to Wright 1931 (for island models), Hamilton 1989 (for regime modelling), Cont 2001 (stylised facts), Goldberg 1989 (GA fundamentals), Eiben Smith 2015 (EC textbook framing).
- **AI-ARTEFACT flags** (lexical and structural per spec Section 9): em dashes, "delve", "leverage" as verb, "robust" filler, "seamlessly", "meticulously", "comprehensive" filler, "It is important to note", "a wide range of", stacked "Furthermore/Moreover/Additionally", "On the one hand / on the other hand" templates, "The X of Y" paragraph openers, "highlighting the importance of" tails, formulaic trifold lists, "significantly/substantially/remarkably" without measured values.
- **CROSS-SECTION-CONSISTENCY**: any number or defined term also present in `0_title_abstract.md` or previously shipped sections.
- **WRITING-CLARITY**: long sentences, passive-voice pile-ups, nominalisation, ambiguous antecedents.

- [ ] **S.7: Compile the critique report.**

Merge subagent output with inline scan into a single numbered list per the spec format:

```
[S{N}-{ID}] {SEVERITY}: {CATEGORY}
Location: {file}:{line-range} ("{quoted-anchor}")
Issue: ...
Evidence: ...
Proposed fix: ...
Needs reference: ... (optional)
```

Sort by severity (CRITICAL first), then by line number. Present to user.

- [ ] **S.8: Collect approval decisions.**

Wait for user response. Accept these response formats (per spec Section 5):

- `accept all`
- `accept critical` or `accept critical+major`
- `accept S{N}-02, S{N}-05, S{N}-07`
- `modify S{N}-05: <text>` (overrides proposed fix)
- `reject S{N}-09 because <reason>` (reason recorded)
- `defer S{N}-10`
- `ship section N` or `done` (only valid when all CRITICALs resolved)

- [ ] **S.9: Apply approved edits with synchronised references.md updates.**

For each accepted item:

1. Apply the edit via `Edit` tool (or `Write` for wholesale replacements).
2. If the edit adds a citation: check `references.md` for the reference. If missing, insert alphabetically using the full bibliographic record from the citation verifier.
3. If the edit removes a citation: grep the full dist folder (`grep -l "Author, YYYY" papers/drafts/dist/*.md`). If no other section cites it, remove from `references.md`.
4. If the edit replaces one citation with another: do both 2 and 3.

After all edits, run an end-of-section sweep:

```bash
cd /Users/naresh/Documents/Research/qengine
# List all (Author Year) citations in the section
grep -oE '\([A-Z][a-zA-Z\-]+ (et al\.?,? )?[0-9]{4}' papers/drafts/dist/<section-file>.md | sort -u
# Confirm each appears in references.md
```

Every citation in the section must appear in `references.md`.

- [ ] **S.10: Log decisions to `.review_log.md`.**

Append a section block:

```markdown
## Section {N}: {filename}

### Round {R}

- [S{N}-01] CRITICAL / CITATION-VERIFY / accepted: <brief note>
- [S{N}-02] MAJOR / METHODOLOGY-JUSTIFICATION / rejected because: <user reason>
- [S{N}-03] MINOR / AI-ARTEFACT / deferred
- ...

**Rejection reasons** (to prevent re-flagging on re-review):
- S{N}-02: <reason>
```

- [ ] **S.11: Re-review edited section.**

Re-read the edited section. Run a lighter version of S.6 (inline scan). Check specifically:
- Any new CRITICAL issues introduced by the edits
- Cross-section consistency for numbers/terms that changed
- Approved AI-artefact fixes actually applied
- Rejected items from S.10 do not re-surface

If new CRITICAL items: append them to the critique report with round number incremented, go back to S.8. Soft cap: 3 re-review rounds. If round 4 needed, escalate to user.

MAJOR and MINOR items surfaced on re-review accumulate into a "polish backlog" entry in `.review_log.md` but do not block shipping.

- [ ] **S.12: Ship section and checkpoint commit.**

When user issues `ship section N` or `done`, verify:
1. No unresolved CRITICAL items for the section.
2. `references.md` consistency check passes (grep from S.9).

Then commit:
```bash
cd /Users/naresh/Documents/Research/qengine
git add papers/drafts/dist/<section-file>.md papers/drafts/dist/references.md
git commit -m "research(dist): review pass on section {N} - {filename}"
```

Move to the next section task.

---

## Task 1: Review `1_introduction.md` (problem formulation first)

**Files:**
- Modify: `papers/drafts/dist/1_introduction.md`
- Modify: `papers/drafts/dist/references.md` (as needed)
- Append: `papers/drafts/dist/.review_log.md`

**Primary sources to consult:**
- `memory/phase6_islandpilot_retrain.md`
- `memory/phase2_results.md`
- `notebooks/RESEARCH.md`

**Cross-reference targets:**
- `0_title_abstract.md` (headline numbers and framing)
- `2_related_work.md` (will be reviewed next; flag anything that depends on Section 2 wording)

**Section-specific review emphases:**
- **Problem-formulation density:** every claim about why this is a real problem needs a citation or a pointer to data. The claim that "fixed parameter configurations are structurally inadequate" must cite Hamilton 1989, Nystrup 2020, Ding 2022 (already cited), and the specific claim about Martingale spread accumulation needs author's prior work or a citation.
- **Simulation-to-production gap framing:** the Tobin 2017 analogy is ambitious; the citation-verifier must confirm Tobin's paper supports the analogy strength we claim.
- **Contribution bullet 5:** cross-check the PF 3.72 / 0.77 / 15-month OOS / 2022-2024 training claim against `phase6_islandpilot_retrain.md` via the fact-checker.
- **Author's earlier research 2026 self-citation:** verify it exists in `references.md` and is correctly formatted. If it does not exist, propose a placeholder entry and flag for user.

- [ ] **Execute per-section loop S.1 to S.12 for `1_introduction.md`.**

(Follow the full 12-step template above.)

---

## Task 2: Review `2_related_work.md` (literature positioning, citation-heavy)

**Files:**
- Modify: `papers/drafts/dist/2_related_work.md`
- Modify: `papers/drafts/dist/references.md` (as needed)
- Append: `papers/drafts/dist/.review_log.md`

**Primary sources to consult:** None specific (this is a literature-positioning section); fact-checker workload is minimal. Citation verifier workload is maximum.

**Cross-reference targets:**
- `1_introduction.md` (contribution bullets must align with gap analysis here)
- `0_title_abstract.md` (framing alignment)

**Section-specific review emphases:**
- **Every non-foundational citation must be VERIFIED with URL or FOUNDATION-TRUSTED.** This is the section where the verifier cache gets populated for reuse downstream.
- **Claim alignment on Yang et al. 2025**: the draft identifies this as the "closest prior work". The verifier must confirm Yang 2025 exists (it is cited as SSRN preprint 5614909) and that it actually does per-regime co-evolutionary GP. If not, the "closest prior work" positioning must be revised.
- **Claim alignment on Chideme Chen Lin 2025**: verifier must confirm this paper exists (cited with DOI 10.1080/0305215X.2025.2592030) and that it uses parallel island models for GTSP.
- **Gap claim at end of 2.1:** "This work integrates regime discovery and parameter optimization into a single evolutionary loop" is the uniqueness claim. If Yang 2025 also does this, the gap needs re-framing.
- **Gap claim at end of 2.3:** "first work to use market regimes as the structuring principle for island topology". Verifier should search for prior work on regime-structured island models; if found, the "first work" claim must be weakened to "among the first" or removed.
- **Section 2.4 p*m = 0.80 claim:** fact-checker must verify this against `memory/phase2_results.md` or `notebooks/RESEARCH.md`.

- [ ] **Execute per-section loop S.1 to S.12 for `2_related_work.md`.**

---

## Task 3: Review `0_title_abstract.md` (first pass, post-framing)

**Files:**
- Modify: `papers/drafts/dist/0_title_abstract.md`
- Modify: `papers/drafts/dist/references.md` (as needed; abstracts rarely cite but check)
- Append: `papers/drafts/dist/.review_log.md`

**Cross-reference targets:**
- `1_introduction.md` (framing, contribution, gap statement)
- `2_related_work.md` (positioning)

**Section-specific review emphases:**
- **Numeric consistency:** PF 3.72, baseline 0.77, 840 evals, 7h 46m, 56 leaves, 36 months (2022-2024), 15-month OOS (Jan 2025 to Apr 2026), 30 indicators, 24+6 split, 10 discriminative features. Every number must match the fact-checker's findings on the memory notes.
- **Uniqueness framing:** "The principal architectural contribution is that island topology is derived from the regime structure itself: ...". Must match Section 2.3 contribution claim.
- **Keyword list:** verify every keyword is also prominent in the body.
- **Title length and clarity:** the current title is 21 words. Applied/systems journals typically accept up to ~20 words; flag as MAJOR if over budget.
- **Abstract length:** most applied/systems journals require 150 to 300 words. Count words and flag if over.
- **"This research" convention:** verify the body of the abstract uses "this research" or similar venue-neutral phrasing, not "this dissertation" or "this paper".

- [ ] **Execute per-section loop S.1 to S.12 for `0_title_abstract.md` (first pass).**

---

## Task 4: Review `3_system_architecture.md` (methodology justification)

**Files:**
- Modify: `papers/drafts/dist/3_system_architecture.md`
- Modify: `papers/drafts/dist/references.md`
- Append: `papers/drafts/dist/.review_log.md`

**Primary sources to consult:**
- `pipelines/_shared/IslandPilot/` (all Python modules)
- `memory/engine_changes.md`
- `memory/real_engine_evolution.md`

**Cross-reference targets:**
- `1_introduction.md`, `2_related_work.md` (contribution claims must match architecture described here)

**Section-specific review emphases:**
- **Every design choice gets a defended alternative.** Fact-checker cross-checks engineering claims against code; orchestrator flags any sentence of the form "We use X" without "because Y" or "following Z (year)".
- Target list of justifications the section should have (flag each missing one as CRITICAL METHODOLOGY-JUSTIFICATION):
  - Why hierarchical two-level GMM vs flat GMM vs HMM
  - Why BIC vs AIC vs cross-validation for mixture-component selection
  - Why ring migration topology vs star vs random vs full mesh
  - Why sibling-only migration across macro-clusters vs free migration
  - Why mutual information vs correlation / Lasso / Random Forest importance for feature selection
  - Why 30 indicators (specific number, budget reasoning)
  - Why hysteresis margin for regime inference vs simpler threshold
  - Why grace period during regime transitions vs immediate switching
  - Why multi-factor position sizing with confidence scaling vs fixed sizing
  - Why 5-minute candles vs other resolutions
  - Why EUR/USD vs broader instrument set (may be OK to defer to Future Work)
- **Algorithm pseudocode blocks:** if present, match line-by-line against the actual code under `pipelines/_shared/IslandPilot/`. Fact-checker.
- **Citations for each theoretical grounding point:** GMM (McLachlan Peel 2000), EM (Dempster Laird Rubin 1977), BIC (Schwarz 1978), mutual information (Kraskov Stogbauer Grassberger 2004), island model (Whitley 1999), shifting-balance theory (Wright 1931), tournament selection (Goldberg Deb 1991), uniform crossover (Syswerda 1989).

- [ ] **Execute per-section loop S.1 to S.12 for `3_system_architecture.md`.**

---

## Task 5: Review `4_training_methodology.md` (training protocol)

**Files:**
- Modify: `papers/drafts/dist/4_training_methodology.md`
- Modify: `papers/drafts/dist/references.md`
- Append: `papers/drafts/dist/.review_log.md`

**Primary sources:**
- `memory/phase6_islandpilot_retrain.md`
- `memory/real_engine_evolution.md`
- `pipelines/_shared/IslandPilot/` (trainer code)

**Cross-reference targets:**
- `3_system_architecture.md` (architecture and training must be internally consistent)
- `5_experimental_setup.md` (will be reviewed next; flag anything that shifts to Section 5)

**Section-specific review emphases:**
- **840 evaluations figure:** fact-checker verifies. Confirm whether this is total across all islands, or per-island x generations, and whether the draft's description matches.
- **7h 46m wall-clock:** fact-checker verifies and checks whether this includes the 56-leaf regime discovery or only evolution.
- **Fitness function definition:** confirm the fitness metric is precisely defined (PF, Sharpe, custom composite?) and matches `phase6` memory note.
- **Walk-forward validation protocol:** if mentioned, verify scheme (expanding vs rolling, fold count).
- **Hyperparameters of the GA itself:** population size, generations, mutation rate, crossover rate, tournament size, migration interval, migration rate. Each needs a justified value, not just a stated value. Methodology-justification review.
- **Real-engine training claim:** critical to the contribution. Fact-checker must confirm the fitness function literally calls the production backtester and not a simplified simulator. Cross-check against code paths.

- [ ] **Execute per-section loop S.1 to S.12 for `4_training_methodology.md`.**

---

## Task 6: Review `5_experimental_setup.md` (baselines, dataset, metrics)

**Files:**
- Modify: `papers/drafts/dist/5_experimental_setup.md`
- Modify: `papers/drafts/dist/references.md`
- Append: `papers/drafts/dist/.review_log.md`

**Primary sources:**
- `memory/phase6_islandpilot_retrain.md` (baseline and pipeline results)
- `pipelines/_shared/GTSBotPilot/`, `pipelines/_shared/FinRLPilot/` (baseline code)
- `memory/MEMORY.md` (dataset: 2006-01-02 to 2025-12-30, 10.4M 1m candles)

**Cross-reference targets:**
- `3_system_architecture.md`, `4_training_methodology.md`

**Section-specific review emphases:**
- **Baseline strategies:** verify each baseline is correctly attributed (GTSBot: Rundo et al. 2019; FinRL: Liu et al. 2020; DempsterJones: Dempster & Jones 2001). Verify each baseline was actually run over the same 15-month OOS window.
- **Dataset description:** EUR-USD 5m, 2022-2024 train, 2025-2026/04 OOS. Exact counts: memory says 2.1M 5m candles total across the 2006-2025 span; fact-checker confirms the training and OOS candle counts.
- **Spread model:** 2 pips OANDA default plus per-candle real bid-ask. Fact-checker confirms whether "real per-candle bid-ask" is a live-data feature or a fixed 2-pip simulation.
- **Metrics defined:** Profit Factor, Max Drawdown, Net Return. Each formula given? Cite standard sources for each (e.g. Kaufman 2013 for PF definition).
- **Statistical significance:** is there any test of whether PF 3.72 vs 0.77 is statistically significant, or is it a single-run comparison? Flag as CRITICAL MAJOR if no statistical test is shown; this is a common reviewer request for applied/systems journals.

- [ ] **Execute per-section loop S.1 to S.12 for `5_experimental_setup.md`.**

---

## Task 7: Review `6_results.md` (numeric verification)

**Files:**
- Modify: `papers/drafts/dist/6_results.md`
- Modify: `papers/drafts/dist/references.md`
- Append: `papers/drafts/dist/.review_log.md`

**Primary sources:**
- `memory/phase6_islandpilot_retrain.md`
- Any tables or CSVs referenced inside the file

**Cross-reference targets:**
- `0_title_abstract.md`, `1_introduction.md`, `5_experimental_setup.md`

**Section-specific review emphases:**
- **Every number in every table, paragraph, and figure caption is fact-checked.** The fact-checker subagent is called on this section with the highest claim density.
- **Per-regime breakdown:** if tables present per-regime PF or drawdown, verify the totals aggregate correctly.
- **Figure references:** if figures are referenced (Fig. 1, Fig. 2), confirm they exist in `papers/drafts/figures/` or `papers/drafts/`.
- **Comparison table (IslandPilot vs baselines):** IslandPilot PF 3.72, GTSBot and FinRL PF 0.7 to 0.85, all with negative net returns per memory. Fact-checker verifies exact numbers.
- **Drawdown language:** "substantially reduced" flagged as AI-ARTEFACT (unmeasured qualifier); propose replacement with the exact percentage.

- [ ] **Execute per-section loop S.1 to S.12 for `6_results.md`.**

---

## Task 8: Review `7_discussion.md` (WHY explanations)

**Files:**
- Modify: `papers/drafts/dist/7_discussion.md`
- Modify: `papers/drafts/dist/references.md`
- Append: `papers/drafts/dist/.review_log.md`

**Primary sources:**
- `memory/phase6_islandpilot_retrain.md` (key architectural change: per-regime signal selection as PF 3.72 driver)
- `memory/MEMORY.md` IslandPilot section (spread/baseline mechanics)

**Cross-reference targets:** `6_results.md`

**Section-specific review emphases:**
- **This is the primary WHY section.** Every headline number needs a causal explanation. Required WHY claims to be covered (flag each missing one as CRITICAL WHY-EXPLANATION):
  - Why does regime-specialised evolution produce PF 3.72 when global evolution produces lower? Expected answer: per-regime populations avoid the averaging effect; signal selection per regime picks directional vs mean-reverting entry logic for the regime's statistical profile. This is documented in memory: "per-regime signal selection (EMA cross vs random) which is the primary source of PF 3.72".
  - Why does the baseline get 0.77? Expected answer: OANDA EUR-USD default spread is 2 pips; random entry plus spread is structurally negative-expectancy per memory. Needs to be stated with the underlying math.
  - Why does sibling migration help vs free migration vs no migration? Expected answer: sub-regimes within a macro-cluster share statistical structure so beneficial genes transfer; distinct macro-clusters have structurally different optima so cross-cluster migration hurts.
  - Why does BIC converge on 56 leaves? Expected answer: the BIC penalty on extra mixture components dominates for smaller cluster counts when features carry diminishing discriminative value.
  - Why does max drawdown drop even when the strategy is still Martingale? Expected answer: regime-conditioned depth and multiplier parameters make bust paths shorter and less severe per regime; position sizing layer caps exposure during high-confidence regimes.
- **Limitations discussed honestly:** single instrument (EUR/USD), single timeframe (5m), single strategy family (grid-hedged Martingale), no live deployment validation, computational cost (33 s per evaluation), potential overfit despite walk-forward. Each must be named and cited against related work.

- [ ] **Execute per-section loop S.1 to S.12 for `7_discussion.md`.**

---

## Task 9: Review `8_conclusion.md` (synthesis and future work)

**Files:**
- Modify: `papers/drafts/dist/8_conclusion.md`
- Modify: `papers/drafts/dist/references.md`
- Append: `papers/drafts/dist/.review_log.md`

**Cross-reference targets:** `1_introduction.md` (contributions match), `7_discussion.md` (limitations match)

**Section-specific review emphases:**
- **Contribution summary:** each contribution listed in Section 1 appears in the conclusion, phrased consistently.
- **Limitations listed honestly:** every limitation in Section 7 is acknowledged in the conclusion.
- **Future work specificity:** vague ("extend to other markets") is flagged MAJOR; specific ("multi-instrument diversification with correlated-regime islands across EUR/USD, GBP/USD, USD/JPY, testing whether shared macro-clusters transfer across currency pairs") is good.
- **No new claims:** the conclusion must not introduce results or citations not previously supported in the body.
- **"This research" convention check.**

- [ ] **Execute per-section loop S.1 to S.12 for `8_conclusion.md`.**

---

## Task 10: Review `appendix.md` (reproducibility and technical completeness)

**Files:**
- Modify: `papers/drafts/dist/appendix.md`
- Modify: `papers/drafts/dist/references.md`
- Append: `papers/drafts/dist/.review_log.md`

**Primary sources:**
- `pipelines/_shared/IslandPilot/` (full code tree)
- `memory/engine_changes.md`, `memory/real_engine_evolution.md`
- `qengine/research/candles.py`

**Section-specific review emphases:**
- **Reproducibility checklist:** code repository URL (if public), dataset access path, hyperparameter values, random seeds, hardware used, wall-clock times, dependency versions.
- **Indicator list:** the 30 indicators must be enumerated or pointed to a specific module path. Fact-checker verifies count and names against `qengine/indicators/__init__.py`.
- **Hyperparameter table:** if present, every value cross-checked against `phase6` memory.
- **Pseudocode or algorithm listings:** line-by-line cross-checked against code.

- [ ] **Execute per-section loop S.1 to S.12 for `appendix.md`.**

---

## Task 11: Final pass on `references.md` (orphan sweep, format, DOIs)

**Files:**
- Modify: `papers/drafts/dist/references.md`
- Append: `papers/drafts/dist/.review_log.md`

**No subagents needed for this task unless individual references fail verification.**

- [ ] **Step 1: Orphan sweep.**

Build a set of all `(Author Year)` citations appearing anywhere in `papers/drafts/dist/*.md` except `references.md` and working files. Compare against entries in `references.md`.

```bash
cd /Users/naresh/Documents/Research/qengine
# Citations present in body
grep -rhoE '\([A-Z][a-zA-Z\-]+[^)]*[0-9]{4}[a-z]?\)' papers/drafts/dist/[0-9]_*.md papers/drafts/dist/appendix.md | sort -u > /tmp/dist_citations.txt
# Entries present in references
grep -E '^[A-Z][a-zA-Z\-]+' papers/drafts/dist/references.md | sort -u > /tmp/dist_refs.txt
# Manual comparison: cat both and reconcile
```

Flag orphans (references without citation) and missing references (citation without entry).

- [ ] **Step 2: DOI pass.**

For every reference without a DOI where the cache has one, inject the DOI into the entry.

- [ ] **Step 3: Alphabetisation.**

Verify alphabetical order by first-author last name. Fix any misordered entries.

- [ ] **Step 4: Format consistency.**

Verify consistent style across all entries: author formatting (initials vs full names), year placement, journal italicisation, volume and issue formatting, page-range dash consistency.

- [ ] **Step 5: Log decisions and commit.**

Append round to `.review_log.md`. Commit `references.md` alone.

```bash
cd /Users/naresh/Documents/Research/qengine
git add papers/drafts/dist/references.md
git commit -m "research(dist): final references pass - orphan sweep, DOIs, formatting"
```

---

## Task 12: Final pass on `0_title_abstract.md` (post-body-stable)

**Files:**
- Modify: `papers/drafts/dist/0_title_abstract.md`
- Append: `papers/drafts/dist/.review_log.md`

**Cross-reference targets:** every now-stable section.

**Section-specific review emphases:**
- **Abstract reflects final body.** Now that every downstream section has been reviewed, the abstract should be re-checked for:
  - Every numeric claim matches the (now-final) Results section verbatim
  - Every architectural claim matches the (now-final) Architecture section
  - The contribution framing is consistent with Introduction and Conclusion
  - Keywords all appear prominently in body headings or first sentences
- **Length check:** word count of abstract under the target journal limit (typically 200-250 for applied/systems).

- [ ] **Execute per-section loop S.1 to S.12 for `0_title_abstract.md` (final pass).**

---

## Task 13: Cross-section consistency final sweep

**Files:**
- Read: all `papers/drafts/dist/*.md`
- Modify: any section with residual inconsistency
- Append: `papers/drafts/dist/.review_log.md`

- [ ] **Step 1: Build a defined-term glossary.**

Scan for terms that appear with definitions (`X is defined as ...`, `we call this X`, `the X refers to ...`). List with the section where defined.

- [ ] **Step 2: Verify each defined term is used consistently across sections.**

Pick the canonical form from the earliest defining section. Flag any section using a variant (e.g. "regime leaf" vs "sub-regime" vs "leaf cluster") as a MAJOR inconsistency.

- [ ] **Step 3: Build a numeric claim index.**

List every numeric claim (figure, percentage, count, duration) with the sections it appears in. Flag any number that appears with different values in different sections as CRITICAL.

- [ ] **Step 4: Build a citation-coverage matrix.**

For each core claim in the Introduction (the contribution bullets), verify it is supported by an explicitly-cited paper in Related Work, elaborated by the Architecture/Methodology, demonstrated by Results, and discussed in Discussion.

- [ ] **Step 5: If any inconsistencies found, loop back to the relevant section task.**

Per the soft-cap rule, if the inconsistency is a CRITICAL issue in a section that was already shipped, reopen that section with a fresh re-review round.

- [ ] **Step 6: Commit the consistency pass.**

```bash
cd /Users/naresh/Documents/Research/qengine
git add papers/drafts/dist/
git commit -m "research(dist): final cross-section consistency sweep"
```

---

## Task 14: Final checkpoint and hand-back to user

- [ ] **Step 1: Regenerate `dist.md` if the user's build process concatenates sections.**

Check whether there is a build script:
```bash
find /Users/naresh/Documents/Research/qengine/papers -name "build*" -o -name "concat*" -o -name "Makefile" 2>/dev/null
```

If a build script exists, run it. If not, regenerate `dist.md` with a simple concatenation in section order (0, 1, 2, 3, 4, 5, 6, 7, 8, ack_decl_data_useAI, appendix, references):

```bash
cd /Users/naresh/Documents/Research/qengine/papers/drafts/dist
cat 0_title_abstract.md 1_introduction.md 2_related_work.md \
    3_system_architecture.md 4_training_methodology.md 5_experimental_setup.md \
    6_results.md 7_discussion.md 8_conclusion.md ack_decl_data_useAI.md \
    appendix.md references.md > ../dist.md
```

Flag: ask the user before overwriting `dist.md`; the existing file may represent a different build pipeline.

- [ ] **Step 2: Generate a summary report for the user.**

Summarise from `.review_log.md`:
- Sections shipped
- Total items presented / accepted / rejected / deferred
- Citations added / removed / replaced
- Polish backlog items (MAJOR/MINOR that were never applied because they surfaced on re-review)
- Any CRITICAL items that were rejected with user reasons

Save to `papers/drafts/dist/.review_summary.md` (also gitignored) and present inline to the user.

- [ ] **Step 3: Final commit marker.**

```bash
cd /Users/naresh/Documents/Research/qengine
git log --oneline papers/drafts/dist/ | head -20
```

Confirm the commit trail is clean and each section has its own commit.

---

## Self-Review

**Spec coverage:** Every requirement in the spec maps to a task:
- Spec Section 1 (Purpose and Scope): Tasks 1-12 cover every in-scope file.
- Spec Section 2 (Quality Bar): Applied/systems tier framing drives inline review emphases in every task.
- Spec Section 3 (Architecture): Task template S.1-S.12 implements the orchestrator workflow; S.4 and S.5 implement the citation-verifier and fact-checker subagents.
- Spec Section 4 (Critique Report Format): Defined in S.7.
- Spec Section 5 (Approval Interface): Defined in S.8.
- Spec Section 6 (References Sync): Defined in S.9 plus Task 11.
- Spec Section 7 (Stopping Criterion): Defined in S.11 and S.12.
- Spec Section 8 (Section Review Order): Tasks 1-12 follow the spec's ordering.
- Spec Section 9 (AI-Artefact Policy): Flag list in S.6.
- Spec Section 10 (Artefacts): Bootstrap task creates working files.
- Spec Section 11 (Risks): Soft cap and URL-downgrade rules embedded in S.8, S.11.

**Placeholder scan:** Every step contains concrete content. Subagent prompt templates include all fields. No "TBD" remains.

**Type consistency:** Severity labels (CRITICAL, MAJOR, MINOR), category labels, and verdict labels are identical across spec and plan. Item ID format `S{N}-{ID}` is consistent from critique format through approval interface through log format.
