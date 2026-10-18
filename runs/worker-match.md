# Worker "match": segmentation, matching, LanceDB index

Work log from the build day. Rerun steps are in `README.md`. The maps are in `docs/diagrams/`.

Branch: `M-Ali-ML/mvp-match` (commits 7bea120, 32f4f2d, 83feaad). Not merged.

## What I built

- `src/nemotron_challenge/segment.py`: page records -> `extract/entries.jsonl`, `extract/coverage.json`.
  - Drops Page-header/Page-footer and running-head Section-header/Title blocks ("H O R [ 664 ] H O R", "HEM"). Keeps the running head as `running_head`.
  - A new entry starts at an uppercase headword followed by `,` `.` or `(`, or at an uppercase Section-header/Title. Roman numerals are not headwords.
  - Text before the first headword is a continuation (`headword: null`, `is_continuation: true`).
  - Extra fields: `plate`, `running_head`, `topic_hint` (a full-word running head such as BLOW-PIPE; used as the query head for continuations), `image_sha256`.
  - `text_norm`: ligature fixes plus long-s repair (f -> s only when the word is not in `/usr/share/dict/words` and the swap is). `text_raw` is unchanged apart from joined hyphens.
- `src/nemotron_challenge/match.py`: BM25 (headword x2 + top TF-IDF terms, top 30, plus a headword-only search top 5) -> embed cosine (keep 10) -> rerank logits. Decision rule, article fetch with checksum check, `why` and `shared_terms` without an LLM, ablation from saved candidates.
- `src/nemotron_challenge/index.py`: LanceDB tables `entries` and `wiki_chunks` at CHALLENGE_DB_PATH. Vectors are cached in `match/vectors/`. Helper `search(query, table, k)` embeds the query with `input_type=query`.
- `tasks.extract` (segmentation only) and `tasks.match` (match + index) are implemented. Tests are in `tests/test_segment_match.py`. `uv run pytest -q`: 66 passed.

## Rerun

```sh
uv run nemotron-challenge run extract --work-dir /Users/aly/repos/Nebius-Hackathon/artifacts
uv run nemotron-challenge run match   --work-dir /Users/aly/repos/Nebius-Hackathon/artifacts
```

The match stage is resumable. It skips entries that have `match/candidates/<entry_id>.json`.
To change the rule, edit TAU/TAU_MARGIN/MIN_MARGIN/TAU_EXACT in match.py and rerun. No new model calls are made.

```python
from nemotron_challenge.index import search
search("ancient Roman epic poet", "wiki_chunks", 5)
```

## Numbers (2026-10-18)

- Segmentation: 100 pages, 262 entries, 176 with a headword, 76 continuations, 10 plate pages (270, 374, 651, 948, 1400, 1615, 1845, 2077, 2209, 2243; blank: 374, 1615, 2077), 723 long-s or ligature edits.
- Matching: all 262 entries processed (the cap of 3 per page was not needed at this size). 67 matched, 195 no_clear_counterpart, 0 errors.
  - Rules that fired: logit > -4.0: 22; margin: 23; exact title: 22.
  - 66 distinct articles saved in `match/articles/`, checksum verified.
  - Rerank top-1 equals BM25 top-1 for 50 of 262 entries (`match/ablation.jsonl`).
- LanceDB: 259 entries (3 blank plates have no text), 622 wiki chunks of about 1,500 chars, 2048-d.
- Time: about 2 s per entry for all model calls. Full run about 8 minutes.
- Threshold reasoning and the 15-pair hand check: `runs/match-threshold-check.md`.

## Known problems

- First run had 16 HTTP 422 errors (14 embed query over 512 tokens, 2 BM25 query with hyphenated heads). Logged in `match/failures-run1.jsonl`. Fixed by retrying the embed query at 1,200 and 600 chars and cleaning the BM25 query. The rerank query still uses 2,000 chars.
- Rerank logits are low (median -6.3) for long OCR queries. The decision uses margin and exact-title rules too. The 15-pair check is our judgment, not a labeled set.
- Known wrong matches: B:452:0 -> Cell counting (Parse produced invented text for page 452), B:651:0 -> Fig (restaurant) (plate caption), B:851:0 -> Ray (optics) (too narrow).
- Long-s repair is word-list based. It can pick the wrong real word ("fleep" -> "sleep", should be "sheep"), and it does not fix f -> st ("frong").
- Segmentation misses headwords that Parse garbles ("HUGO CAvery,"). Margin side notes ("Switectland.") stay inside entry text.
- Topic hints come from running heads; some are OCR noise (PHILLOOGY, UPTICS, WARDS).
- Plate pages with no caption have no searchable text and stay unmatched.

## Update 2: page-level pass (after merge of main)

New in match.py: `collect_short` (model calls, resumable), `finalize_short` (decisions, no calls except article fetch),
`run_page_match` (both + ablation). `tasks.match` now runs entry match -> page pass -> LanceDB index.

Outputs (nothing earlier is overwritten):
- `match/topics.json`: running head -> cleaned topic, with the BM25 hits used.
- `match/candidates_short/<entry_id>.json`, `match/matches_short.jsonl`: method `bm25+embed+rerank_short`.
  Same top-10 candidates as the long pass (continuations also get the topic hits), rerank query = head + 600 chars.
- `match/pages/<row>.json`: page rerank records for 23 pages with a full-word running head.
- `match/page_matches.jsonl`: one line per page. Fields as matches.jsonl plus `page_topic`, `entry_ids`,
  `page_kind` (treatise | dictionary | plate), `articles` (all accepted articles on the page with their source).
  Plates use `artifacts/plates/<row>.json` from the site worker.
- `match/summary_pages.json`, and `match_coverage` in `extract/coverage.json`.
- `match/ablation.jsonl` now also has the `bm25+embed+rerank_short` top-1.

Page coverage:
- Before (entry-level long query only): 31 of 100 pages have an accepted match.
- After: 45 of 100. By kind: treatise 12 of 23, dictionary 32 of 67, plate 1 of 10.
  10 pages by page-topic rerank, 10 by the guide-word rule, the rest through entries.
- Entries: long 67 matched, short 71, either 73. Continuations: long 9 of 76, short 11 of 76.
  Short-only matches: B:2464:1 Kabbalah, B:2524:0 Hindustan, B:258:3 Thomas Willis, B:403:0 Philology,
  B:499:0 India (Herodotus), B:523:12 Engine.
- 84 articles saved (2 no longer referenced after the exact-title fix). LanceDB: 259 entries, 871 wiki chunks.

Rerun only the page pass (no new calls if caches exist):

```sh
uv run python -c "from pathlib import Path; from nemotron_challenge.config import Settings; from nemotron_challenge.match import run_page_match; print(run_page_match(Settings.from_env(), Path('/Users/aly/repos/Nebius-Hackathon/artifacts')))"
```

Known problems (page pass):
- Short queries did not raise logits; the gain comes from cleaned topics, exact-title checks, and the guide word.
- Guide-word matches are weaker evidence: 5 of 10 correct, 4 partial, 1 wrong (1678 -> Harry Billinge).
- Treatise pages still unmatched: 13 Shipbuilding, 104 Weights and measures, 115 Bleaching, 1942 Conserves,
  1945 Optics (index pages win), 2087 Britain, 2402 Anatomy, 2424 Agriculture, 2446 Chemistry, 1298 Wards.
  Main articles for broad topics often do not reach the BM25 candidate set.
- Junk running heads (THROXEN, THOTHR) give wrong topics; those pages match only through entries.
- 55 pages stay no_clear_counterpart with the best candidate and reason in page_matches.jsonl.

## Update 3: retrieval ablation (Feature 1)

- Module `src/nemotron_challenge/ablation_eval.py` (`build_labels`, `evaluate`). No model calls.
- Labels: `artifacts/match/labels.jsonl`, 40 entries (15 from the threshold check + 25 random, seed 7). Own judgment, one reader.
  36 have a counterpart (27 with the right article in the pool, 9 not), 4 have none.
- Results (`artifacts/match/ablation_summary.json`, `artifacts/match/ablation.png`, doc `docs/retrieval-ablation.md`):
  P@1 with gold in pool: BM25 0.30, +embed 0.56, +rerank long 0.70, +rerank short 0.70.
  MRR@10: 0.42, 0.67, 0.79, 0.81. Candidate pool recall 0.75. No-match accuracy (n=4): 0.75 for both rerank passes.
  Long-query decisions accept 13 of 40, 12 correct.
- Examples: rerank fixed B:1910:0 (Lightning), B:1214:1 (Damsel), B:1680:0 (Carpentry); broke B:1614:1 (Thirsty (disambiguation) over Polydipsia; the decision step recovers it).
- Rerun: `uv run python -c "from pathlib import Path; from nemotron_challenge.ablation_eval import evaluate; evaluate(Path('/Users/aly/repos/Nebius-Hackathon/artifacts'))"`
- Limits: 40 items, one reader, only 4 negatives. Candidate recall is the main bottleneck.

## Update 4: vision query expansion

- Module `src/nemotron_challenge/vision_expand.py`: `run_vision` (Super VL + BM25 + Embed VL + Rerank VL, resumable, 3 threads), `apply_vision` (decisions, page table), `vision_recall`.
- `run_page_match` now writes `page_matches_v1.jsonl` (text passes only) and then applies vision results to `page_matches.jsonl` when `match/vision_expand/` exists.
- Super VL gets the scan (JPEG, longest side 1,600 px) + running head, thinking off, max 600 tokens; it returns subject + 3 to 5 phrases. It never decides a match.
- 46 non-plate unmatched pages: 45 answered, 1 failed (546: Super VL reports a blank page, so the Parse text for 546 is invented). Logged in `match/vision_failures.jsonl`.
- 7 accepted: 217 Farm, 257 Jonathan Swift, 383 Political economy, 473 Conchology, 914 Arabs, 1324 Hedge, 1722 Arsenic.
- Page coverage: 45 -> 52 of 100. `extract/coverage.json` -> `match_coverage.vision_expand`, `pages_matched_final`.
- Labeled set (6 positives on expanded pages): gold in pool 4 -> 6, gold in top 10 3 -> 5, top 1 after 2.
- Cost: 45 calls, 28,321 prompt + 1,808 completion tokens, 1.4 s per call.
- LanceDB rebuilt: 259 entries, 1,054 wiki chunks, 91 articles.
- Rerun: `uv run python -c "from pathlib import Path; from nemotron_challenge.config import Settings; from nemotron_challenge.vision_expand import run_vision; run_vision(Settings.from_env(), Path('/Users/aly/repos/Nebius-Hackathon/artifacts'))"` then `run_page_match` (see Update 2).
- Known: correct top-1 but rejected by the rules: 13 Shipbuilding, 247 Mount Etna, 268 Laurus.

## Update 5: uncertainty report

FOR THE SITE WORKER: show these fields.
- Pages: `artifacts/match/page_matches.jsonl`, rows with `status: no_clear_counterpart` now have
  `uncertainty_cause` (one of `no_text`, `ocr_failure`, `obsolete_or_minor`, `pool_miss`, `threshold_miss`, `other`)
  and `uncertainty_note` (short text, with "likely article: X" when we can name it).
- Entries: `artifacts/match/uncertainty.jsonl`, key `id` (`B:<row>:<n>` or `P:<row>`), fields `cause`, `cause_label`
  (human-readable), `right_article`, `note`, `evidence`, `best_long` / `best_short` / `best`.
- Labels for the six causes: `causes` in `artifacts/match/uncertainty_summary.json`.

What: `src/nemotron_challenge/uncertainty.py` + `uncertainty_causes.tsv` (one reader's cause per item). `run_page_match` reapplies it.
Counts (entries / pages): no_text 20/6, ocr_failure 37/1, obsolete_or_minor 24/1, pool_miss 47/16, threshold_miss 43/19, other 18/5. Totals 189/48.
Doc: `docs/uncertainty.md` (counts, 2 examples per cause, fixes).
Rerun: `uv run python -c "from pathlib import Path; from nemotron_challenge.uncertainty import run_uncertainty; print(run_uncertainty(Path('/Users/aly/repos/Nebius-Hackathon/artifacts')))"`
