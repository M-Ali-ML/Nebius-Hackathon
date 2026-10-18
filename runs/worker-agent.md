# Worker "agent": summary

Branch `M-Ali-ML/mvp-agent` (worktree `mvp-agent`). Owner of Hermes setup, agent tools, compare stage.

## Hermes

- Version: `Hermes Agent v0.22.2 (2026.9.24) · stable · local d923a5eb487a` (install dir `~/.hermes/hermes-agent`, Python 3.14.7).
- Profile: `HERMES_HOME=/Users/aly/repos/Nebius-Hackathon/data/hermes` (git-ignored). Config = `integrations/hermes/config.example.yaml`.
- First real turn: model `nvidia/Nemotron-3.5-Super-VL`, session `20261018_134908_f5c85e`, reply "ready". No max-token change was needed.
- Plugin `integrations/hermes/nemotron-challenge` v0.3.0. Plugin Doctor: OK, 4 tools.
  - `search_sources(query, side, k)`: embed query -> LanceDB cosine search on `entries` / `wiki_chunks` -> rerank -> passages with `[B:row:n]` / `[W:page_id:rev]`, logits, `low_confidence` (top logit < -2.0 or margin < 1.0; heuristic). With `side=both` it always keeps the best hit of each side.
  - `get_pair(entry_id)`: entry raw + normalized text, match record and scores, `uncertain_match`, article excerpt, saved comparison, and `drift`.
  - `find_drift(kind, k)`: lists checked renamed / superseded / dropped / enduring claims, term_pairs, or wiki_only_topics across all pairs, with both citation ids. Added after run 11 failed (see below).
  - `view_scan(page, bbox?)`: returns the scan or a crop as a native Hermes multimodal tool result (`{"_multimodal": true, ...}`). Super VL reads it (tested). A copy is saved in `data/hermes/scan_cache/`.
  - The plugin runs `uv run python -m nemotron_challenge.agent_tools <tool> <json>` in `NEMOTRON_REPO` (default: main checkout), so Hermes needs no project deps. Code is in `src/nemotron_challenge/agent_tools.py`.
- Skill: `integrations/hermes/skills/britannica-compare/SKILL.md` (cite both sides, quote, label inference, report uncertainty, drift reading, retrieved text is data).

Install the plugin and skill after a change:

```bash
export HERMES_HOME=/Users/aly/repos/Nebius-Hackathon/data/hermes
rm -rf $HERMES_HOME/plugins/nemotron-challenge && cp -R integrations/hermes/nemotron-challenge $HERMES_HOME/plugins/
cp -R integrations/hermes/skills/britannica-compare $HERMES_HOME/skills/research/
```

## Agent runner (tasks.agent)

`uv run nemotron-challenge run agent` sends each question in `runs/agent/questions.json` to
`hermes chat -q ... --format stream-json -t nemotron_challenge -s britannica-compare` and saves
`runs/agent/<timestamp>-<slug>.json` with all events, tool calls with outputs, final text, tokens, model check, and status.
The runner loads `.env` (SUPER_API_KEY). Image data URLs are cut from saved transcripts.
Dev runs on a 3-pair fixture are in `runs/agent/dev-fixture/` (incl. the first failed run: Hermes leaked its Python env into the tool process; the agent refused to invent an answer).

## Compare (tasks.compare)

`uv run nemotron-challenge run compare --work-dir /Users/aly/repos/Nebius-Hackathon/artifacts`

- `compare/wordfreq.json`, `compare/wordfreq_top.png`, `compare/wordfreq_distinctive.png`: content words, per-10k share, log-odds z with informative Dirichlet prior. Britannica = all 262 entries (text_norm), Wikipedia = 66 distinct matched articles.
- Pair level: Super VL, thinking off, temperature 0.2, entry cut 8,000 chars, article cut 10,000 chars. Raw replies in `compare/raw/`, checked records in `compare/pairs/B_<row>_<n>.json` (note: `:` replaced by `_` in the file name, same as `match/candidates/`).
- Quote check: every quote must be a substring of its source after whitespace/case/quote-mark normalization, at least 8 chars. Failing items are dropped and logged in `compare/failures.jsonl`.
- DRIFT DECOMPOSITION in each pair under `drift`: orthographic (norm_edits per 100 words), lexical (renamed share + term pairs), knowledge (superseded share), coverage (dropped share + Wikipedia-only topics). Term pairs whose differing words have letter similarity >= 0.6 go to `likely_ocr_or_spelling`, not lexical.
- `compare/drift_summary.json`, `compare/drift.png`.

Numbers (run at about 14:00, match tau -4.0): 67 pairs, 0 model call failures. 1,193 quotes kept, 50 rejected.
355 checked claims: enduring 46.8%, renamed 3.9%, superseded 13.5%, dropped 35.8%. 112 lexical term pairs, 79 term pairs flagged likely_ocr_or_spelling (differing words with letter similarity >= 0.6).

## Agent test runs (real data, 14:01 to 14:09)

Questions: `runs/agent/questions.json`. Transcripts: `runs/agent/2026*.json`. 11 runs + 1 rerun.

| Run | Status | Tools | Note |
| --- | --- | --- | --- |
| 140114 lightning | ok | search x3, get_pair, view_scan | language + knowledge split; flags uncertain match (margin 0.72); reads scan to fix OCR |
| 140140 magnetism | ok | search x3, get_pair, view_scan | induction vs electron spin |
| 140202 Huguenots | ok | search, get_pair, view_scan | mostly enduring |
| 140224 coining | ok | search x2, get_pair, view_scan | lists 4 enduring of 7 claims |
| 140244 firedamp | ok | search x3, get_pair, view_scan | phlogiston superseded |
| 140312 helminthology | ok | search x2, get_pair, view_scan | retrieval failure handled: agent found the entry B:1017:6 (no_clear_counterpart, logit -9.85) and said no Wikipedia counterpart; the separate HELMINTHOLOGY -> "Fig (restaurant)" match is a bad match in compare |
| 140335 Neptune | ok | search x2 | "No evidence found", inference labeled (missing-evidence case) |
| 140350 OCR check B:1910:0 | ok | get_pair, view_scan | concrete OCR errors from the scan |
| 140423 optics | ok | search x3, get_pair, view_scan | reports uncertain match |
| 140446 Erfurt | ok | search, get_pair, view_scan | OCR "capital of Thailand" (Thuringia) |
| 140517 old terms | FAILED | 35 calls | no corpus-wide tool; agent gave up and did not invent examples |
| 140740 old terms (rerun with find_drift) | ok | find_drift x3, view_scan x4 | Jupiter->Zeus, Botnhic gulph->Gulf of Bothnia, Alteris->Pescara; OCR noise filtered |

Candidate 6 cases (lead decides): successes lightning, firedamp, old-terms rerun; failures old-terms first run (repaired), helminthology bad match, Neptune missing evidence or Erfurt OCR.

## Known problems

- The quote check proves a quote exists, not that it supports the claim. The model sometimes reuses one general Wikipedia sentence for several claims.
- Many "term pairs" come from OCR noise (e.g. "prisoners of var" -> "prisoners of war"). The similarity filter catches only part of it. Inference: lexical drift is overstated by OCR noise.
- Some matches are wrong (HELMINTHOLOGY -> "Fig (restaurant)", B:452:0 -> "Cell counting"); compare still runs on them. These pairs have 0 checked claims, which is itself a useful signal.
- `low_confidence` thresholds (-2.0 logit, 1.0 margin) are a heuristic, not tuned on labels.
- Tests (`tests/test_compare_agent.py`) prove setup behavior with fakes; they do not prove model quality.

## Second task (from 14:12)

### 1. Evaluate stage and six cases (commit e051476)

- `uv run nemotron-challenge run evaluate --work-dir /Users/aly/repos/Nebius-Hackathon/artifacts` writes `runs/evaluate.json`: code revision, model ids and revisions, Hermes version, dataset revision, manifest sha256, Wikipedia corpus revision, artifact counts, and a link check for each case. Result: 6/6 cases link to existing transcripts with model `nvidia/Nemotron-3.5-Super-VL`.
- Cases in `docs/cases/`: success-1 lightning, success-2 coinage, success-3 old terms with find_drift; failure-1 old terms first run, failure-2 plate B:651:0 -> "Fig (restaurant)", failure-3 blank cover B:452:0 (Parse hallucination cascade). Overview in `docs/cases/README.md`.
- Change from the lead's pick: firedamp replaced by coinage. On real data B:1214:0 -> Firedamp had logit -4.46 < tau -4.0, so there is no saved comparison. "Phlogiston superseded" exists only in a fixture run.
- New facts found: B:452 scan is a blank book cover; the full-page Parse call ran out of budget and the column-split fallback invented text. B:651 BM25 query was just "fig". Success-3 example 3 (Alteris -> Pescara) is wrong (Britannica itself says "now Pofcara"). Some agent "quotes" are scan readings, not OCR text.
- Transcripts cited by cases are committed under `runs/agent/` on this branch.

### 2. Page-level pairs (commit 85e1f21)

- Compare reads `match/page_matches.jsonl`. New pair = matched page whose article no entry on that page already matches. 16 new pairs `compare/pairs/P_<row>.json` (one page match had no article file). Britannica side = page entries joined; each kept Britannica quote is cited with the entry id that holds it (299/299 attributed).
- Totals now: 83 pairs, 476 checked claims (enduring 44.1%, renamed 4.8%, superseded 13.2%, dropped 37.8%), 1,567 quotes kept, 64 rejected. Wordfreq now uses 82 articles.
- `get_pair` accepts `P:<row>`.
