# Operational risk score v2 — foundation and evidence audit (Task 36)

**Outcome B: a defensible numeric score is NOT yet possible. `risk_score` stays NULL for all 1,586 rows.** What shipped is the auditable framework (evidence contract, eligibility matrix, contribution and provenance contracts, an aggregation path that refuses to run without evidence-based weights) and the audit that proves the conclusion. The existing engine (`risk-engine-1.0.0`: status, basis, confidence) is untouched.

**Update (Task 39, current numbers).** After the Task 38 gauge mappings the audit assesses 1,771 cells (equal to the rows of `risk.operational_risk`): 1,287 with no eligible signal group, 476 with one, **8 with two**; 0 scored. Eligible observations: air quality 320, rainfall 46, gauge 126 (Mianwali and Jhang), weather 0. Abstention reasons: `SCORE_V2_DISABLED` 1,771 · `NO_ELIGIBLE_SIGNAL` 1,287 · `TOO_FEW_INDEPENDENT_SIGNAL_GROUPS` 476 · `NO_EVIDENCE_BASED_WEIGHTS` 484. The rest of this page is the Task 36 record (1,586 cells, gauge 0 % resolved) and is kept as history. Served abstention blocks now also carry `evidence_available`, `evidence_missing`, `evidence_required` and an `interpretation`. See [FINAL_SYSTEM_STATUS.md](FINAL_SYSTEM_STATUS.md).


Machine-readable audit: `data/analytics/risk/score_v2_audit.json` (`python scripts/risk/audit_score_v2.py`, deterministic and idempotent, no database writes).

## Why no score (measured, not assumed)

1. **No evidence-based weights exist.** Aggregating domains requires weights; the repository has none and no calibration data (no labelled outcomes). An unweighted mean or max would be an arbitrary choice (the max already *is* the status, with provisional thresholds). So the aggregate is refused: `NO_EVIDENCE_BASED_WEIGHTS`.
2. **The data contract is also almost never met.** A cell needs ≥ 2 *independent* eligible signal groups. Of 1,586 cells: 1,228 have none, 350 have one, **8 have two**.
3. **Thresholds are provisional.** Status cut points are the engine authors' choices, not validated; they are not treated as ground truth.

Cell outcomes: 1,586 assessed, 0 scored, 1,586 abstained (reasons are not exclusive: `SCORE_V2_DISABLED` 1,586 · `NO_ELIGIBLE_SIGNAL` 1,228 · `TOO_FEW_INDEPENDENT_SIGNAL_GROUPS` 350 · `NO_EVIDENCE_BASED_WEIGHTS` 358). Provenance coverage of assessed signals: 100 % (2,616 signals carry source record ids).

## Domain eligibility matrix (real Gold data)

| Domain | Rows | Resolved | Geographies | Dates (span, longest gap) | Longest per-unit history | Eligible observations | Decision |
|---|---:|---:|---:|---|---:|---|---|
| rainfall | 869 | 76 % | 42 | 2025-03-03 → 2026-07-14 (78 dates, gap 129 d) | 47 | 46 eligible · 570 insufficient history · 253 unresolved geography | normalizable, but ≥ 30 prior observations only for a few units; event-driven series |
| weather | 39 | 69 % | 27 | **1 date** (2026-08-12) | 1 | 0 · 27 insufficient · 12 unresolved | no history ⇒ no normalization |
| gauge | 3,686 | **0 %** | **0** | 93 dates | 0 | 0 · 3,499 `UNRESOLVED_GEOGRAPHY` | no authoritative station→district mapping (Task 24); never inferred from river/gauge names |
| air quality | 352 | 100 % | **1 (Lahore)** | 2025-10-01 → 2026-09-16 (351 dates, gap 1 d) | 350 | 320 eligible · 30 insufficient | the only continuous series; one geography |
| hazard alert | 38 | 95 % | 7 | 5 dates | — | all `OUT_OF_SCOPE` | **contextual**: severity labels map through provisional cut points; no normalization reference |
| disaster event | 1,543 | 100 % | 7 | 80 dates | — | all `OUT_OF_SCOPE` | **contextual**: routine sitrep counts, no baseline; overlaps the hydromet group |

Excluded inputs by design: documents/RAG (never numeric), RAG relevance, ML predictions (Task 33 baselines are `BASELINE_ONLY`, not validated ML — contextual only), reservoirs (not attributable to an admin unit), secondary gauge candidates (no eligible mapping), the provisional thresholds as ground truth.

## The contract (`pipeline/risk/scoring_v2.py`, `config/risk_score_v2.yaml`, version `operational-score-v2-foundation-1.0.0`)

* **Observation → normalization:** only the engine's `percentile_rank_strict_prior` (the observation's percentile against the same unit's strictly earlier observations). No other normalization is invented.
* **Eligibility per signal:** `ELIGIBLE | INSUFFICIENT_DATA | UNRESOLVED_GEOGRAPHY | INVALID | OUT_OF_SCOPE`, each with a reason. Eligible needs: numeric domain, resolved and non-caveated geography, a finite non-negative value, an observation dated exactly on the cell date (no carry-forward), a normalized value in [0, 1], and ≥ 30 prior observations. Missing is never zero; invalid values are never clipped.
* **Independence groups:** `hydromet_event` = {rainfall, gauge, hazard alert, disaster event} (may describe the same event), `temperature` = {weather}, `air_quality`. A group contributes at most one signal (the largest eligible); correlated domains are never summed.
* **Aggregation (only if possible):** weighted mean of group contributions × 100 (0–100, higher = higher signal intensity relative to the unit's own history; *not* a probability, not calibrated, not a loss estimate). Requires ≥ 2 contributing groups **and** a positive weight with a non-empty `evidence_reference` for each. `enabled: false` and `weights: {}` ship, so the shipped behaviour is always abstention.
* **Output per cell:** `risk_score`, `score_status` (`SCORED | ABSTAINED`), `score_version`, `eligible_signal_count`, `required_signal_count`, `contributing_signals`, `excluded_signals` (each with domain, source, observation date, geography, value, normalization method/reference/history, contribution, eligibility, reason, source record ids), `abstention_reason(s)`, `score_provenance`.

## API / layers (read-only, backward compatible, no migration)

Risk rows (`/api/v1/risk*`, and therefore the intelligence `risk_context.record` and the agent's risk tools, provenance `RISK_ENGINE`) gain an optional `score_v2` block: `score_status ABSTAINED`, `score_version`, `abstention_reason NO_EVIDENCE_BASED_WEIGHTS`, `abstention_text`, `required_signal_count`, `contributing_signals []`, `excluded_signals` (the contextual domains). It is derived from the stored row and the shipped contract; stored rows carry no per-signal history counts, so per-cell eligibility lives in the audit, not in the API. If scores are ever stored, the block passes them through as `SCORED`. All existing fields are unchanged; write verbs still answer 405. The Intelligence and Agent pages show `Operational score: not computed - <reason>` beside the status (never a fake zero); ML forecasts and documentary evidence remain separate blocks.

## What would be needed for Outcome A

Outcome labels or validated reference thresholds; evidence-based weights per independence group (an `evidence_reference` is mandatory); more than one geography with a continuous series (today only Lahore AQI is long enough); resolved gauge geography; a second year of data for seasonal normalization. Until then the correct output is NULL with a reason.

## Limitations

The audit's eligibility counts depend on the engine's own percentile normalization and the provisional history bar (30). The 8 two-group cells are a data fact, not a score. Independence groups are a documented conservative judgement, not an estimated correlation. No real LLM was involved.
