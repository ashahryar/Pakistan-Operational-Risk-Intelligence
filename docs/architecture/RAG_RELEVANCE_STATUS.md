# RAG relevance and abstention — status (Task 35)

**Problem (found in Task 34):** retrieval always returns the best-scoring chunks, including chunks that only share frequent words with the question. `What did NDMA report about volcanic eruptions in Sindh?` returned 5 chunks, which the Intelligence and Agent layers then treated as documentary evidence. BM25 has no relevance floor, and in hybrid mode the cosine floor (0.60) does not remove them because off-topic questions written in NDMA-style words still score 0.70–0.80 against NDMA boilerplate.

**What changed:** a deterministic relevance policy (`pipeline/rag/relevance.py`) classifies each returned chunk `RELEVANT` or `LOW_RELEVANCE` and each query `RELEVANT` or `NO_EVIDENCE`. `NO_EVIDENCE` is decided by measured signals, not by `len(results) == 0`. Only `RELEVANT` chunks become evidence in `/rag/ask`, `/intelligence/ask` and `/agent/ask`; `/rag/search` keeps returning its rows (backward compatible) with a label on each. Retrieval itself (BM25, cosine, deterministic RRF, metadata filters) is unchanged.

## Signals (all measured, none invented)

| Signal | Meaning | Where |
|---|---|---|
| `coverage` | IDF-weighted share of the query's *topic* words that occur in the chunk. A word occurring nowhere in the corpus counts as unmatched with the highest weight | `LexicalRetriever.coverage` |
| `absent_share` | (query level) IDF-weighted share of the query's topic words that occur in **no** chunk of the corpus: keyword matching cannot supply that concept | `LexicalRetriever.absent_share` |
| `cosine` | embedding cosine between query and chunk (any chunk, not only those above the floor) | `SemanticRetriever.cosines` |

*Topic words* = content words minus a fixed question-framing list (`retrieval.FRAMING_WORDS`: "reported", "about", "official", "evidence", "current", "operational", agency names …). Used only by the relevance signal, never by BM25 ranking. Added in iteration 3 (below).

## Selected policy (`relevance-1.2.0`)

| Mode | Chunk is RELEVANT when | Notes |
|---|---|---|
| lexical (BM25) | `coverage ≥ 0.25` **and** `absent_share ≤ 0.5` | |
| semantic | `cosine ≥ 0.63` | **weak** — see below |
| hybrid (RRF) | `absent_share ≤ 0.5` (the coverage and cosine terms are disabled: `min_coverage 0.0`, no `min_cosine`) | the gate is placed *after* RRF fusion so ranking stays deterministic; the lexical-branch signal decides, because adding the cosine branch only added false positives |

Query level: `RELEVANT` if one of the first 5 results passes (the depth the policy was evaluated at), then every passing chunk is evidence; otherwise `NO_EVIDENCE`, every chunk is withheld (listed by id and signals only, never as text). The thresholds are **calibrated for this corpus (1,909 chunks) and this embedding model (bge-small-en-v1.5)**; they are heuristics, not probabilities, and are not claimed valid elsewhere.

## Threshold selection (deterministic, reproducible)

`python scripts/rag/evaluate_relevance.py --select` / `python scripts/rag/evaluate_relevance.py` (report `data/analytics/rag/relevance_eval_report.json`; `module_policy_equals_selection` is checked by a test).

* **Frozen set** `config/rag_relevance_eval.yaml` extends the 39 Task 30–31 cases (unchanged, `include`d) with 128 new cases: exact places / districts / provinces, event terminology, paraphrases, filtered queries, plain unsupported questions (cricket, guitar, covid …), **difficult negatives** (frequent corpus words + an absent concept: "NDMA report on tsunami damage in Karachi", "hurricane relief items distributed in Sindh" …) and question-form queries. Validity is checked against the corpus, never against a score: every negative's `absent_terms` must have 0 occurrences (2 cases fail that check and are excluded and reported by the harness: `uns_capital_france` — 'paris' occurs — and `neg_passengers_lahore`; two more, `h2_neg_oilspill` and `h2_neg_satellite`, failed it and were replaced, and the unneeded absent term 'japan' was removed from `t32_uns_gdp`, all before any score of those cases was computed), every supported case must have relevant chunks. Relevance judge: substring of `relevant_terms` (one judge, heuristic).
* **Rule:** over a threshold grid choose the policy maximising the *balanced accuracy* of the query-level decision (1 − (false-abstention rate on supported queries + false-positive rate on unsupported queries)/2), subject to an **evidence-loss cap of 0.15** (supported queries whose ungated top-5 had a relevant chunk but whose gated list has none — the loss the gate itself causes; queries the retriever already missed are not charged to it); ties → higher precision@5, then smaller thresholds. The cap was drafted as 0.10 and raised to 0.15 after viewing the *development* frontier (0.10 cut through an arbitrary cliff, 4/37 = 0.108), before any holdout number existed.
* **Three iterations, all reported — this is how the policy was actually reached, including two failures:**

| Iteration | Selected on | Reported on | Result |
|---|---|---|---|
| 1 | `dev` (coverage / cosine thresholds) | `holdout` (iteration 1) | dev looked good (unsupported FPR 0.08) but the holdout did not: unsupported false-positive rate **0.357 lexical, 0.429 hybrid, 0.571 semantic** — dev overstated it (12 negatives only) |
| 2 | `dev + holdout` (now seen) + the absent-word share signal | fresh `holdout2` | unsupported FPR 0.154 / 0.154 / 0.615 (lexical / hybrid / semantic), supported false abstentions 4/18 |
| 3 | pool = `dev + holdout + holdout2` + the 8 Task 32 documentary questions | fresh question-form `holdout3`, written before any score existed | final policy; below |

**Iteration 3 was forced by an existing test, not by the new evaluation:** the Task 32 real-data test (documentary evidence must contain the expected term, 8/8) fell to **3/8** under the iteration-2 policy, because real intelligence questions are verbose ("What did PDMA advise about heavy rain?") and the keyword-style cases of iterations 1–2 under-represented them. Fixing it required the question-framing word list (fixed *before* `holdout3` was run, from generic question wording) and question-form cases in the set. The Task 32 questions are therefore part of the selection pool (their results were seen).

## Results (BM25 / semantic / hybrid; "before" = ungated, every returned chunk is evidence)

**Fresh holdout (`holdout3`: 16 supported, 14 unsupported/difficult negatives — the only unseen data for the final policy)**

| Mode | Supported P@5 before → after | Supported R@5 before → after | Unsupported false-positive rate before → after | Abstention accuracy before → after | False abstentions |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.725 → 0.797 | 0.725 → 0.712 | 1.00 → **0.00** (14/14 → 0/14) | 0.533 → **1.00** | 0/16 |
| Semantic | 0.775 → 0.775 | 0.775 → 0.775 | 0.786 → **0.714** | 0.633 → 0.667 | 0/16 |
| Hybrid | 0.850 → 0.850 | 0.850 → 0.850 | 0.929 → **0.00** (13/14 → 0/14) | 0.567 → **1.00** | 0/16 |

**Selection pool (`dev + holdout + holdout2`: 100 supported, 42 negatives, 21 of them difficult — what the thresholds were chosen on, so optimistic)**

| Mode | Supported P@5 | Supported R@5 | Unsupported FPR | Abstention accuracy | False abstentions (supported) |
|---|---:|---:|---:|---:|---:|
| BM25 before → after | 0.776 → 0.734 | 0.780 → 0.684 | 0.857 → **0.048** | 0.739 → 0.866 | 1/100 → **17/100** |
| Semantic before → after | 0.706 → 0.686 | 0.670 → 0.630 | 0.619 → 0.548 | 0.754 → 0.746 | 9/100 → 13/100 |
| Hybrid before → after | 0.824 → 0.718 | 0.824 → 0.718 | 0.833 → **0.071** | 0.754 → 0.880 | 0/100 → **14/100** |

**The cost is real:** across the pool the gate withholds evidence for 14–17 % of supported queries (their wording shares no corpus word with the text — "destroyed dwellings and residences", "farmland and harvest destroyed" — and only a semantic signal could rescue them, which does not work here), and supported recall@5 drops from 0.82 to 0.72 (hybrid) and 0.78 to 0.68 (BM25). On the small question-form holdout the loss was 0/16, but 16 cases cannot support a general claim.

## What the data does not support (stated, not hidden)

* **Embedding cosine is not a usable relevance signal on this corpus.** Difficult negatives score 0.70–0.80 against NDMA boilerplate; supported paraphrases score 0.71–0.75. A distinctive-term variant (cosine of only the rare query words) did not separate them either (supported minimum 0.54 vs negative maximum 0.69). The semantic-only gate (0.63) therefore changes little (unsupported FPR 0.62 → 0.55 on the pool, 0.79 → 0.71 on `holdout3`), and **no claim of semantic understanding is made**: the selected hybrid/BM25 gates work through *keyword absence*, not meaning.
* **Every designed negative contains a word that occurs nowhere in the corpus** (that is how "absent concept" was verified). The `absent_share` rule exploits exactly that. An off-topic question made *only* of words that all occur in the corpus is not represented in the evaluation and would pass.
* **Known residual false positives** (kept as tests): when the absent concept word carries less than half of the query's IDF weight, the question still passes — e.g. "hurricane relief items distributed in Sindh", "tornado warning issued for Balochistan districts" (pool difficult negatives: 2/21 BM25, 3/21 hybrid).
* **No stemming:** "flooding" ≠ "flood", so BM25's per-chunk coverage may withhold chunks that use another word form (a supported "flooding in Sindh" question now yields fewer chunks than before, never none that were relevant to the evaluated cases).
* A **place name that occurs nowhere in the document corpus** counts as an absent concept word. A question about such a district can abstain even though documents about its province exist; the intelligence layer still returns that district's risk context.
* Selection variance is large: the iteration-1 dev result (0.08) became 0.36 on its holdout. Sets of 6–37 cases per group do not give stable estimates; thresholds are a development choice.
* Real-LLM behaviour is not measured (no credential). Everything here is deterministic retrieval evaluation.

## D4 and the existing evaluations

* **D4** "What did NDMA report about volcanic eruptions in Sindh?": retrieval still finds 5 chunks (BM25 and hybrid); all 5 are `LOW_RELEVANCE`; `/agent/ask` → `NO_EVIDENCE`. No rule mentions the word "volcanic" (the corpus has 0 occurrences of "volcan"); the same policy abstains on tsunami, election, internet, nuclear, cryptocurrency, ventilator, … questions (tests). D4 belongs to the selection pool, so its own result is not independent; the independent evidence is `holdout3` (0/14 false positives).
* **Task 31** (`semantic_eval_report.json`, `grounded_eval_report.json`): byte-identical — those harnesses evaluate the retrievers directly and retrieval is unchanged.
* **Task 32** (intelligence): risk-context selection 10/10, documentary evidence 8/8, unsupported 4/4, provenance probes 9/9 (all unchanged); junk chunks returned for the unsupported questions **5 / 5 / 0 / 3 → 0 / 0 / 0 / 0**.
* **Task 34** (agent, 36 cases): routing 36/36, tools 36/36, status **35/36 → 36/36** (D4), abstention without facts **20/21 → 21/21**, provenance 192/192, invalid calls 20/20 + 10/10, false premise 4/4.

## Behaviour in the layers

* `/api/v1/rag/search`: unchanged rows; each result gains `relevance.assessment {label, coverage, absent_share, cosine}`; the response gains `relevance_status`, `abstained`, `abstention_reason`, `relevance_policy`; optional `only_relevant=true` drops `LOW_RELEVANCE` rows.
* `/api/v1/rag/ask`: only relevant chunks are given to the model; none relevant → `answer_status RETRIEVAL_EMPTY` (the existing status; clients keep working), `evidence []`, `retrieval.relevance {relevance_status NO_EVIDENCE, abstained, abstention_reason, counts, withheld_chunks}`, **the model is not called** (`model.called false`). Relevant evidence still goes through the unchanged Task 31 citation validation.
* `/api/v1/intelligence/ask`: same retrieval; the relaxation order (event type → district→province → date) and "geography and source are never dropped" are unchanged (the gate only classifies results, filters are applied before ranking). With no relevant documents and no other context the status is `RETRIEVAL_EMPTY` (not `LLM_UNAVAILABLE`), `retrieval.relevance` says NO_EVIDENCE, `model.called false`. If a risk-engine record exists for the area, the unchanged Task 32 contract still generates from the risk context alone (that is the only case where a provider is needed, and `LLM_UNAVAILABLE` then refers to the risk-only explanation, not to the documents).
* `/api/v1/agent/ask`: `rag.retrieve` returns `EMPTY` for NO_EVIDENCE, the agent reports `NO_EVIDENCE` (`components.evidence` carries the abstention reason), the model is not called.
* Dashboard (RAG Ask, Intelligence, Agent): an explicit `NO_EVIDENCE …` notice with the number of withheld passages; withheld chunks are never rendered as evidence.
* `GenerationConstraints`, the grounding validators and provenance are untouched; the gate cannot bypass them (tests).

## Reproduce

```bash
python scripts/rag/evaluate_relevance.py --select    # selection on the pool only (holdout3 not shown)
python scripts/rag/evaluate_relevance.py             # full report: dev / holdout / holdout2 / pool / holdout3 / all, before vs after
python scripts/rag/evaluate_intelligence.py          # Task 32 evaluation
python scripts/agents/evaluate_agent.py              # Task 34 evaluation
```
