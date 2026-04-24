# Dist-Folder Review Agent Design

**Status:** Draft, pending user review
**Date:** 2026-04-24
**Target artefact:** `papers/drafts/dist/`, the IslandPilot dissertation/journal-paper draft split into per-section markdown files.

## 1. Purpose and Scope

The goal is an iterative review workflow that brings the dist-folder draft to a quality bar suitable for (a) dissertation submission now and (b) journal publication later without major rework. The workflow must strengthen the draft along five specific axes the user identified:

1. **Problem formulation is evidence-backed.** The reader should finish Section 1 convinced that the problem exists and is worth solving, with citations supporting every non-obvious claim.
2. **Methodology choices are justifiable.** Every design decision with a plausible alternative should have a recorded reason, ideally cited against prior work.
3. **Academic positioning is complete.** What already exists in journals is stated clearly, and the contribution is discrete and uniquely demonstrated.
4. **WHY explanations accompany results.** The draft must show understanding of causal mechanisms behind the headline numbers, not just report achievements.
5. **No AI-language artefacts.** The draft reads as natural academic prose, without em dashes, stock AI phrasing, robotic cadence, or formulaic structures.

In-scope files (in processing order): `1_introduction.md`, `2_related_work.md`, `0_title_abstract.md`, `3_system_architecture.md`, `4_training_methodology.md`, `5_experimental_setup.md`, `6_results.md`, `7_discussion.md`, `8_conclusion.md`, `appendix.md`, `references.md`, and a final pass on `0_title_abstract.md` after everything else is stable.

Out of scope: `dist.md` (consolidated single-file artefact), `dist.docx`, `island_pilot.*` files, `submit_1_1.md`. Those are downstream build products or separate publication artefacts.

## 2. Quality Bar

- Primary target: applied/systems tier (e.g. *Expert Systems with Applications*, *Applied Soft Computing*, *Engineering Applications of Artificial Intelligence*, *IEEE Access*).
- Additional constraint: strong theoretical grounding retained so the body also serves as a dissertation. Body prose refers to the work as "this research" or "in this research" rather than "this dissertation" or "this paper", to keep the text venue-neutral for later journal adaptation.
- Every CRITICAL citation must survive web verification. Existence-only verification is acceptable for foundational works (Hamilton 1989, Schwarz 1978, Doob 1953, Goldberg 1989, Whitley 1999, Wright 1931); claim-alignment verification is required for citations used to justify specific methodology choices or support specific empirical claims.

## 3. Architecture (Approach C, hybrid orchestration)

The main Claude Code conversation drives the outer loop. Subagents are dispatched only for the two expensive tasks that benefit from isolation and parallelism.

```
main conversation (orchestrator)
  |
  |-- per section N:
  |     1. read section N + cross-reference context
  |     2. dispatch in parallel:
  |          - citation-verifier subagent (web lookups)
  |          - fact-checker subagent (codebase/memory/notebook lookups)
  |     3. inline scan for clarity, AI-artefacts, WHY gaps, methodology gaps
  |     4. merge all findings into critique report
  |     5. present report, collect approval decisions
  |     6. apply approved items; update references.md in same pass
  |     7. re-review edited section
  |     8. loop 5-7 if new CRITICAL items appear (soft cap 3 rounds)
  |     9. ship section, advance
```

### 3.1 Citation-Verifier Subagent

**Dispatched via:** `Agent` with `subagent_type: general-purpose`, parallel across citation batches.

**Input:** list of `(Author, Year, citing-sentence, full-reference-entry)` tuples from the section.

**Process per citation:**
1. Foundational-works allowlist check. If on the allowlist, mark `FOUNDATION-TRUSTED` after existence-only verification.
2. Otherwise, resolve via DOI if present, else via Google Scholar / Semantic Scholar / publisher site.
3. Verify existence: real paper, correct author/year/title/venue.
4. Verify claim alignment: does the paper's abstract or summary support what the draft cites it for?
5. For claims that currently lack a citation but should have one (identified inline by the orchestrator), propose candidate citations found during search.

**Returns per citation:**
```
{
  "citation": "Nystrup et al. (2020)",
  "verdict": "VERIFIED" | "EXISTS-CLAIM-MISMATCH" | "NOT-FOUND" | "FOUNDATION-TRUSTED" | "UNCLEAR",
  "evidence": "short note and URL",
  "url": "https://...",
  "full_reference": "Nystrup, P., Lindstrom, E., & Madsen, H. (2020). Learning hidden Markov models with persistent states by penalizing jumps. Expert Systems with Applications, 150, 113307.",
  "doi": "10.1016/j.eswa.2020.113307"
}
```

**Cache:** `papers/drafts/dist/.citation_cache.json`, keyed by `(author, year, title-slug)`. Re-review passes reuse the cache unless the citing sentence changed. The cache file is human-readable JSON and can be inspected or edited.

### 3.2 Fact-Checker Subagent

**Dispatched via:** `Agent` with `subagent_type: Explore`, single-shot per section.

**Input:** the section text plus pointers to primary sources of truth: `memory/phase6_islandpilot_retrain.md`, `memory/phase2_results.md`, `memory/surefire_v2/RESEARCH.md`, `notebooks/` scripts, `qengine/pipeline/islandpilot/*.py`, `strategies/SurefireHedge*.py`.

**Process per claim:**
1. Classify: `NUMERIC-RESULT`, `ENGINEERING-DETAIL`, `CROSS-SECTION-CONSISTENCY`.
2. Locate primary evidence.
3. Verify match.

**Returns per claim:**
```
{
  "claim": "profit factor of 3.72 on 15-month OOS",
  "type": "NUMERIC-RESULT",
  "verdict": "MATCHES-SOURCE" | "MISMATCH" | "UNSOURCED" | "OUTDATED",
  "source": "memory/phase6_islandpilot_retrain.md",
  "source_value": "PF ~3.72",
  "draft_value": "3.72",
  "note": "consistent; memory note uses approximate tilde"
}
```

### 3.3 Orchestrator (Main Conversation)

The main conversation does the work that requires visibility into the reasoning and user-in-the-loop decisions:

- Reading sections and spotting the cheaper issues (clarity, AI-artefacts, WHY-gaps, methodology-justification gaps, problem-formulation gaps, cross-section inconsistency).
- Merging subagent output into a single critique report.
- Presenting the report to the user and collecting approval decisions.
- Applying approved edits via `Edit` / `Write` tools.
- Updating `references.md` in the same edit pass when citations change.
- Re-reviewing after edits and looping if needed.

## 4. Critique Report Format

Each item:

```
[S{section}-{ID}] {SEVERITY}: {CATEGORY}
Location: {file}:{line-range} ("{quoted-anchor}")
Issue: {what is wrong, weak, unsupported, or AI-toned}
Evidence: {verifier/fact-checker finding, or orchestrator reasoning}
Proposed fix: {specific replacement text or edit description}
Needs reference: {optional, citation to add/verify before applying}
```

**Severity levels:**

- **CRITICAL**: fact errors, citation errors, missing problem evidence, undefended methodology choices, cross-section numeric inconsistencies. Must be resolved (accepted or rejected with reason) before the section ships.
- **MAJOR**: weak WHY explanations, missing theoretical grounding, positioning gaps, unclear contribution framing. Strongly encouraged but not blocking.
- **MINOR**: writing polish, AI-language artefacts, cadence issues. Never blocking; batched for a polish pass.

**Categories:**

- `PROBLEM-FORMULATION`: evidence that the problem is real and worth solving.
- `CITATION-VERIFY`: existence, author/year correctness, claim alignment.
- `FACTUAL-ACCURACY`: numeric and engineering claims match primary sources.
- `METHODOLOGY-JUSTIFICATION`: why this choice over plausible alternatives.
- `WHY-EXPLANATION`: causal reasoning behind results.
- `THEORETICAL-GROUNDING`: connection to established theory.
- `AI-ARTEFACT`: em dashes, stock AI phrasing, robotic cadence, formulaic structures.
- `CROSS-SECTION-CONSISTENCY`: numbers, definitions, or terminology aligned across sections.
- `WRITING-CLARITY`: standard copy-edit concerns.

## 5. Approval Interface

The user responds to a critique report with one or more of:

- `accept all`: apply every item.
- `accept critical` / `accept critical+major`: threshold-based.
- `accept S3-02, S3-05, S3-07`: specific IDs.
- `modify S3-05: <preferred wording>`: override the proposed fix.
- `reject S3-09 because <reason>`: skip, reason recorded so it does not re-surface.
- `defer S3-10`: skip for this pass, revisit later.
- `ship section N` / `done`: advance to next section once CRITICAL items are resolved.

Rejection reasons accumulate in a per-section log so the re-review pass does not re-flag items the user has already declined.

## 6. References Synchronization

Every edit that touches a citation triggers a references update in the same write pass.

- **Add:** if a newly-cited reference is not in `references.md`, insert alphabetically, using the full bibliographic record returned by the citation verifier (including DOI where available).
- **Remove:** if an edit removes the last citation to a reference anywhere in the dist folder, remove the reference from `references.md`.
- **Change:** replacements are treated as remove-plus-add (with orphan check on the old entry).
- **End-of-section sweep:** after applying approved edits, confirm every `(Author, Year)` in the section exists in `references.md`, and no reference is orphaned.
- **Duplicate detection:** same paper with different formatting is merged; the verifier's canonical bibliographic record wins.

## 7. Stopping Criterion (per section)

A section is done when all of these hold:

1. Every CRITICAL item is accepted-and-applied or explicitly rejected with a recorded reason.
2. No CRITICAL item is left unreviewed.
3. The re-review pass after applying fixes surfaces no new CRITICAL issue.
4. `references.md` is consistent with the section's citations (automated end-of-section check).
5. User issues `ship section N` or `done`.

Soft cap: 3 re-review rounds per section. If a fourth round would be needed, the orchestrator escalates to the user rather than continuing to loop. MAJOR and MINOR items never trigger a re-loop; they accumulate in a polish backlog.

## 8. Section Review Order

Chosen so that upstream framing is settled before downstream details, and so citation-heavy sections populate the verification cache early.

1. `1_introduction.md`: problem formulation first.
2. `2_related_work.md`: literature positioning, contribution framing, citation-heavy.
3. `0_title_abstract.md`: revisit after framing is stable.
4. `3_system_architecture.md`: methodology justification and theoretical grounding.
5. `4_training_methodology.md`: training protocol, hyperparameters, fitness, walk-forward.
6. `5_experimental_setup.md`: baselines, dataset, metrics, factual claims about data and baselines.
7. `6_results.md`: numeric verification against memory notes and notebooks.
8. `7_discussion.md`: WHY explanations, causal reasoning.
9. `8_conclusion.md`: internal consistency with discussion, honest limitations.
10. `appendix.md`: technical completeness, reproducibility.
11. `references.md`: final orphan sweep, alphabetical sort, format consistency, DOIs where available.
12. `0_title_abstract.md` final pass: one read after everything else is stable.

## 9. AI-Artefact and Natural-Tone Policy

The draft must read as natural academic prose. The review flags the following as MINOR / AI-ARTEFACT:

**Punctuation:**
- Em dashes (`—`) in prose. Replace with comma, parenthetical, semicolon, or sentence break depending on context. En-dashes in page ranges are fine.

**Lexical flags (replace or remove):**
- "delve", "leverage" (as verb), "robust" (filler use), "seamlessly", "meticulously", "comprehensive" (filler use), "cutting-edge", "state-of-the-art" (filler).
- "It is important to note that", "It is worth noting that", "It should be noted that".
- "In conclusion", "In summary" when used as formulaic openers.
- "a wide range of", "a variety of" when the range is not enumerated.
- "Furthermore", "Moreover", "Additionally" stacked in consecutive sentences within the same paragraph.
- "revolutionary", "game-changing", "paradigm shift", heavy AI and marketing vocabulary.

**Structural flags:**
- Paragraphs opening with "The" + abstract noun + "of" + abstract noun (AI template opener).
- Sentences ending with "highlighting the importance of X" as a formulaic tail.
- Triadic parallelism ("not X, not Y, but Z") when overused in a section.
- Formulaic trifold lists ("first, second, third") when a prose sentence reads better.
- "On the one hand / on the other hand" template pairs when not genuinely balancing two sides.

**Natural-tone guidance (positive):**
- Prefer concrete nouns and active verbs to abstract nominalisations.
- Vary sentence length; avoid strings of sentences all 20 to 30 words long.
- Prefer "we" (active) when the writer made the choice, "the system" / "the pipeline" when describing mechanism.
- Avoid robotic over-qualification ("significantly", "substantially", "remarkably") unless the qualifier has a measured value behind it.

**Policy:** AI-artefact items are batched as MINOR and applied together via the `cleanse-ai-writing` skill (or equivalent) on the polish pass per section. They do not block section completion; they must be applied before `ship section N`.

## 10. User-Visible Artefacts Produced

- Edited files under `papers/drafts/dist/`.
- Updated `references.md` synchronised with the body.
- `papers/drafts/dist/.citation_cache.json`: verification cache (gitignored or not, user's choice).
- A per-section review log appended to a working file `papers/drafts/dist/.review_log.md` recording: items presented, decisions, rejection reasons, re-review rounds. This log is for audit and to prevent re-flagging deferred items; it is not a publication artefact.

## 11. Risks and Mitigations

- **Risk:** citation verifier hallucinates a "verified" verdict when the paper does not exist or says something different.
  **Mitigation:** the verifier must return a URL for every non-foundational verdict; verdicts without a URL are downgraded to UNCLEAR. The user can spot-check any cited URL.

- **Risk:** fact-checker reports MATCHES-SOURCE when the memory note itself is outdated.
  **Mitigation:** when the source is a memory note, the fact-checker also checks the most recent notebook output or codebase artefact if one is named. Mismatches between memory and primary artefact are flagged as OUTDATED with both values.

- **Risk:** applying approved fixes introduces cross-section inconsistencies (e.g. changing a number in Section 3 without updating the abstract).
  **Mitigation:** end-of-section re-review includes a cross-section consistency scan on any number or definition that was changed. The final abstract pass (step 12 in the section order) catches anything that slipped through.

- **Risk:** review loop on a single section never converges (infinite critical items).
  **Mitigation:** soft cap of 3 re-review rounds per section. After round 3, escalate to the user rather than continue.

- **Risk:** over-aggressive AI-artefact removal strips legitimate em-dashes or valid "Furthermore" usages.
  **Mitigation:** AI-artefacts are always MINOR; user can reject any specific item, and the rejection reason is recorded to prevent re-flagging.

## 12. Out of Scope for This Design

- Rewriting figures, regenerating tables, or modifying the underlying experimental data. If a factual mismatch surfaces, the agent reports it; it does not re-run experiments.
- Building a single consolidated dist.md. That is a downstream build step once per-section work is complete.
- Adding new sections or reorganising the section structure. The review works within the existing 11-file structure.
- Submission formatting (LaTeX conversion, journal-specific templates). Those are post-review concerns.
