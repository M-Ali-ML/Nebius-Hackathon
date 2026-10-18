# Submission

- Team: `nebius-build-week` (`M-Ali-ML`)
- Repository URL and commit: `https://github.com/M-Ali-ML/Nebius-Hackathon` (evaluated at commit `4d85e472b8f403103340da4467e4b01eda402c3e`, recorded in `runs/evaluate.json`)
- Video walkthrough (3 to 5 minutes): run script and prompts recorded in `docs/demo-commands.md`
- Static website URL: `https://huggingface.co/spaces/nebius-build-week/britannica-across-time` (app URL: `https://nebius-build-week-britannica-across-time.static.hf.space`, local path: `site/index.html`)
- Dataset URL: `https://huggingface.co/datasets/nebius-build-week/britannica-wikipedia-drift`
- Compiled LaTeX documents: 100 PDFs in `artifacts/latex/*.pdf` and `site/latex/*.pdf` (build log in `artifacts/latex/build.jsonl`)

### Repository layout

| Path | Content |
| --- | --- |
| `src/nemotron_challenge/` | Pipeline code: `extract`, `segment`, `match`, `vision_expand`, `uncertainty`, `index`, `plates`, `neighbors`, `latex`, `site`, `compare`, `agent_tools`, `agent_runner`, `evaluate` |
| `integrations/hermes/` | Hermes plugin (5 tools: `search_sources`, `get_pair`, `find_drift`, `view_scan`, `view_neighbors`) and skill `britannica-compare` |
| `artifacts/` | Raw Parse output, segmented entries, candidate lists with stage scores, matches, articles, comparisons, plate records, and LaTeX outputs |
| `site/` | Static archive (`index.html`, `explore.html`, `analysis.html`, `how.html`, `pages/<row>.html`, `latex/<row>.pdf`) |
| `docs/cases/` | Six case studies (3 success, 3 failure) and agent retrieval ablation summary |
| `runs/` | Agent transcripts (`runs/agent/`), GPU smoke receipt (`runs/model-service-smoke.json`), and evaluation report (`runs/evaluate.json`) |

## Reproduce the run

Maps: `docs/diagrams/who-runs-what.svg`, `docs/diagrams/pipeline.svg`, `docs/diagrams/hermes.svg`.
Setup, APIs, and package versions: `README.md` and `docs/technical.md`.

### 1. Setup and run commands

Install dependencies and fetch the fixed 100-page Britannica sample:

```sh
uv sync --locked
cp .env.example .env           # set SUPER_API_KEY and RETRIEVAL_BASE_URL
uv run nemotron-challenge data fetch
```

Build and start the embedding and reranking model service on a GPU VM (NVIDIA RTX PRO 6000 Blackwell Server Edition) and forward port 8000:

```sh
# on the GPU VM
docker buildx build --platform linux/amd64 --load -t nemotron-challenge-models:local infra/model-service
docker run -d --name nemotron-models --gpus device=0 --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g \
  --cap-drop ALL --security-opt no-new-privileges -p 127.0.0.1:8000:8000 nemotron-challenge-models:local

# on the workstation
ssh -N -L 8000:127.0.0.1:8000 <user>@<vm-ip>
uv run nemotron-challenge doctor --live
```

Run each pipeline stage and the test suite:

```sh
uv run nemotron-challenge parse          # Parse 3.5; skips a page that already has extract/raw
uv run nemotron-challenge run extract    # entry segmentation and long-s repair
uv run nemotron-challenge run match      # BM25 -> Embed VL -> Rerank VL -> page pass -> LanceDB
uv run nemotron-challenge run compare    # Word frequency + Super VL pair comparisons + drift
uv run nemotron-challenge run site       # Tectonic LaTeX PDFs + static website in site/
uv run nemotron-challenge run agent      # Hermes questions -> runs/agent/
uv run nemotron-challenge run evaluate   # Verify case links and write runs/evaluate.json
uv run pytest -q
```

### 2. Tested Python and package versions

- Python: `>=3.12,<3.14` for the pipeline (`pyproject.toml`); Hermes CLI runs on Python `3.14.7` (`Hermes Agent v0.22.2 (2026.9.24) · stable · local d923a5eb487a`)
- Core packages (`pyproject.toml`):
  - `httpx==0.28.1`
  - `pydantic==2.14.1`
  - `python-dotenv==1.2.4`
  - `lancedb==0.40.0`
  - `pyarrow==21.0.0`
  - `huggingface-hub==2.2.0`
  - `pillow>=13.0.0`
  - `jinja2>=3.1.6`
  - `matplotlib>=3.11.2`
  - `pytest==9.1.1`
- GPU container runtime (`runs/model-service-smoke.json`): `torch 2.8.0+cu128`, `cuda 12.8`, `transformers 4.56.2`, `bfloat16`, `sdpa`

### 3. Model IDs, revisions, and serving settings

| Model ID | Revision | Role and serving settings |
| --- | --- | --- |
| `nvidia/nemotron-3.5-parse` | Shared hackathon endpoint | Document parsing of 100 Britannica scans into ordered text and picture blocks with bounding boxes. Two-column crop fallback when a dense page hits the token limit. |
| `nvidia/llama-nemotron-embed-vl-1b-v2` | `582e3bf72aee355e3c59ed89de53543c5b0657ee` | Multimodal embedding (2048-d) served via Docker on NVIDIA RTX PRO 6000 (`bfloat16`, `sdpa`, microbatch size 1). Embeds text queries, Wikipedia chunks, and plate images. |
| `nvidia/llama-nemotron-rerank-vl-1b-v2` | `b8a9987b05b75db5ad949c825cbcbf6eb7c48b5a` | Multimodal reranker served in the same Docker container (`raw_logit` output). Re-ranks top-10 candidates per entry, page topic, and plate image. |
| `nvidia/Nemotron-3.5-Super-VL` | Nebius Token Factory endpoint | Pair comparison (`thinking=off`, `temperature=0.2`, entry cap 8,000 chars, article cap 10,000 chars), plate description (`thinking=off`, max 900 tokens), vision query expansion (`thinking=off`, max 600 tokens), and Hermes agent reasoning with multimodal `view_scan` and `view_neighbors`. |

### 4. Source dataset revisions and hashes

- Britannica dataset: `NationalLibraryOfScotland/encyclopaedia_britannica_illustrated`, git revision `309f765b1ecc83e0a7f7762e44b4a927a7555443` (CC0)
- Britannica sample manifest: `src/nemotron_challenge/resources/britannica-manifest.json`, SHA-256 `779542e078756874f23fa6971d7d8a2d8635ad6d9d9484e1deb607d94a28e396` (100 scans out of 2,573, chosen at random without replacement using seed `20261016`, sorted by `source_row_index`)
- Wikipedia snapshot: `wikimedia/structured-wikipedia` via the shared BM25 API, revision `417c267bb457fa645c22eb3b5c77764963194c70` (7,182,883 articles, CC BY-SA 4.0)

## Results

### Scan coverage, segmentation, and LaTeX compilation

- Scans parsed: 100 of 100 pages (`artifacts/extract/coverage.json`). Two dense pages used the two-column crop fallback. Ten pages are engraving plates (3 blank or near-blank leaves: rows 374, 1615, 2077).
- Segmented entries: 262 entries in `artifacts/extract/entries.jsonl` (176 entries with a detected headword, 76 continuation entries, 10 plate entries). Normalizing text made 723 long-s and ligature repairs while keeping `text_raw` separate from `text_norm`.
- LaTeX archive: 100 of 100 pages compiled to PDF with `tectonic` (`artifacts/latex/*.pdf` and `site/latex/*.pdf`), 0 build failures, 89 two-column documents, 26 cropped figure images. Unrecognized characters from OCR noise render as visible `[U+XXXX]` markers on 11 pages.

### Matching, retrieval ablation, and uncertainty analysis

- Entry matching: all 262 entries processed (`artifacts/match/matches.jsonl`). Long-query pass matched 67 entries and marked 195 `no_clear_counterpart` (0 call errors). Short-query pass matched 71 entries (`artifacts/match/matches_short.jsonl`); 73 entries matched in either pass.
- Page matching: 52 of 100 pages matched (`artifacts/match/page_matches.jsonl`, `artifacts/match/summary_pages.json`). Text passes matched 45 pages (12 of 23 treatise pages, 32 of 67 dictionary pages, 1 of 10 plate pages: row 270 Hydrostatics). Vision query expansion with `nvidia/Nemotron-3.5-Super-VL` on unmatched non-plate scans added 7 matched pages (rows 217 Farm, 257 Jonathan Swift, 383 Political economy, 473 Conchology, 914 Arabs, 1324 Hedge, 1722 Arsenic).
- LanceDB index: 259 non-blank entries and 1,054 Wikipedia chunks across 91 saved articles (2048-d vectors).
- Retrieval ablation (`docs/retrieval-ablation.md`, `artifacts/match/ablation_summary.json`): on 40 hand-labeled entries (27 with the target article in the BM25 candidate pool), P@1 improved from `0.30` (BM25) to `0.56` (BM25 + Embed VL) to `0.70` (BM25 + Embed VL + Rerank VL). MRR@10 improved from `0.42` to `0.67` to `0.79` (long query) and `0.81` (short query). Candidate pool recall is `0.75`.
- Uncertainty taxonomy (`docs/uncertainty.md`, `artifacts/match/uncertainty.jsonl`, `artifacts/match/uncertainty_summary.json`): every unmatched entry (189) and unmatched page (48) has a recorded cause:
  - `pool_miss`: 47 entries, 16 pages (right article absent from the 30 BM25 candidates)
  - `threshold_miss`: 43 entries, 19 pages (right article ranked top-1 or near top-1, but below decision thresholds)
  - `ocr_failure`: 37 entries, 1 page (garbled headword or invented Parse text on a blank page)
  - `obsolete_or_minor`: 24 entries, 1 page (18th-century cross-reference, minor locality, or obsolete term)
  - `no_text`: 20 entries, 6 pages (blank pages or uncaptioned plates)
  - `other`: 18 entries, 5 pages (multi-topic pages or mismatched granularity)

### Comparison method, text exclusions, and drift decomposition

- Method (`src/nemotron_challenge/compare.py`):
  - Corpus word frequency (`artifacts/compare/wordfreq.json`): content words across 262 Britannica entries (`text_norm`) and 82 matched Wikipedia articles, scored by per-10k share and log-odds z-score with an informative Dirichlet prior. Header/footer blocks, running heads, and stop words are excluded.
  - Pairwise claim comparison: 83 pairs compared with `nvidia/Nemotron-3.5-Super-VL` (67 entry-level pairs `B_<row>_<n>.json` and 16 page-level pairs `P_<row>.json` in `artifacts/compare/pairs/`). Raw model outputs stay in `artifacts/compare/raw/`.
  - Quote verification: every Britannica and Wikipedia quote must be at least 8 characters and match its source text as a substring after whitespace, case, and quote-mark normalization. Across 83 pairs, 1,567 quotes passed verification and 64 failed (`artifacts/compare/failures.jsonl`). Claims with unverified quotes are excluded from drift counts.
  - Term pair noise filter: candidate renamed term pairs whose differing words have character similarity `>= 0.6` are separated into `likely_ocr_or_spelling` so OCR noise is not counted as lexical replacement.
- Drift decomposition across 83 pairs and 476 quote-checked claims (`artifacts/compare/drift_summary.json`, `runs/evaluate.json`):
  - `enduring`: `44.1%` (facts present in both sources)
  - `dropped`: `37.8%` (18th-century claims omitted from the modern Wikipedia article)
  - `superseded`: `13.2%` (claims replaced or corrected by modern science or scholarship)
  - `renamed`: `4.8%` (same concept under a modern term)
- Links to analysis, plots, and source records:
  - Plots: `artifacts/compare/drift.png`, `artifacts/compare/wordfreq_top.png`, `artifacts/compare/wordfreq_distinctive.png`, `artifacts/match/ablation.png`
  - Reports: `docs/retrieval-ablation.md`, `docs/uncertainty.md`, `docs/cases/README.md`, `site/analysis.html`
  - Source records: `artifacts/extract/entries.jsonl`, `artifacts/match/matches.jsonl`, `artifacts/match/page_matches.jsonl`, `artifacts/compare/drift_summary.json`, `runs/evaluate.json`

## Case studies

All six case studies trace to saved Hermes agent runs (`runs/agent/*.json`) using `nvidia/Nemotron-3.5-Super-VL` and are verified by `uv run nemotron-challenge run evaluate` (`runs/evaluate.json`). Overview and agent retrieval ablation: [`docs/cases/README.md`](../docs/cases/README.md).

### Success cases

1. [`docs/cases/success-1.md`](../docs/cases/success-1.md) (`success-1`): Lightning (`B:1910:0` vs `W:17801:1337944042`). Separates orthographic/lexical change from superseded and added knowledge, flags `uncertain_match` (margin `0.72`), and calls `view_scan` to correct OCR errors. Run: `runs/agent/20261018-140114-what-did-the-britannica-say-about-lightn.json`.
2. [`docs/cases/success-2.md`](../docs/cases/success-2.md) (`success-2`): Coinage (`B:2325:0` vs `W:62067164:1322156603`). Lists enduring vs superseded claims about coining money with quotes and citations from both sources. Run: `runs/agent/20261018-140224-which-britannica-claims-about-coining-mo.json`.
3. [`docs/cases/success-3.md`](../docs/cases/success-3.md) (`success-3`): Old terms with modern names (repaired rerun). Adding the corpus-wide `find_drift` tool repaired `failure-1`, cutting token use by 86% (from 435,766 to 62,455 tokens) and verifying candidates on the page scans via `view_scan`. Run: `runs/agent/20261018-140740-which-old-terms-in-the-britannica-have-d.json`.

### Failure cases

1. [`docs/cases/failure-1.md`](../docs/cases/failure-1.md) (`failure-1`): Old terms with modern names (first run, before `find_drift`). Without a corpus-wide aggregation tool, the agent made 35 `search_sources` and `get_pair` calls (435,766 tokens), hit its iteration limit, and stopped without inventing examples. Run: `runs/agent/20261018-140517-which-old-terms-in-the-britannica-have-d.json`.
2. [`docs/cases/failure-2.md`](../docs/cases/failure-2.md) (`failure-2`): Helminthology engraving plate (`B:651:0`). Parse extracted only figure labels (`Fig. 1..7`), BM25 searched `"fig"`, and the entry matched `"Fig (restaurant)"` (`W:63206954:1287271235`). Run: `runs/agent/20261018-141132-what-is-britannica-entry-b-651-0-about-a.json`. A later run with `view_neighbors` (`runs/agent/20261018-143919-britannica-page-651-is-a-plate-what-does.json`) located the companion text on neighbor page `[R:649]` (`HELMINTHOLOGY. Chap. II.`).
3. [`docs/cases/failure-3.md`](../docs/cases/failure-3.md) (`failure-3`): Blank cover page (`B:452:0`). The full-page Parse call hit its token limit on a blank cover scan, and the two-column fallback hallucinated fluent text that matched `"Cell counting"` (`W:2530553:1314887075`). Run: `runs/agent/20261018-141143-what-does-britannica-entry-b-452-0-say-a.json`. A rerun after updating the skill to inspect the scan when content looks impossible (`runs/agent/20261018-143836-what-does-britannica-entry-b-452-0-say-a.json`) identified the blank scan via `view_scan` and `view_neighbors`.

## Limits

### What was tested and what remains uncertain

- Tested: all 100 sample scans through Parse 3.5, entry segmentation, tectonic LaTeX compilation, multi-stage retrieval (BM25, Embed VL, Rerank VL, and Super VL vision query expansion), quote-checked pairwise comparison on 83 pairs, and 47 saved Hermes agent runs (14 primary runs and 33 retrieval ablation runs). Automated unit and contract tests (`uv run pytest -q`) pass.
- Uncertain: our 40-entry retrieval label set and 6-cause uncertainty labels reflect one annotator's judgment. Agent runs were executed once per question per configuration without multi-run variance estimates. The dataset spans multiple Britannica editions (1768 to 1860), and individual page rows do not carry edition dates.

### Known failure modes and next steps

- OCR noise inflates lexical and knowledge drift: garbled 18th-century words (such as `"Thailand"` for `"Thuringia"` on the Erfurt scan or `"fitteenth"` for `"ſixteenth"`) can pass substring checks because the garbled string is present in the Parse output. Character-similarity filtering catches 112 of 254 term pairs, but vision verification with `view_scan` is needed to filter the rest.
- Parse hallucination on blank scans: when a blank page (such as page 452 or page 546) causes Parse to loop and trigger the column-split fallback, the model can invent text. Checking image variance or asking Super VL for `is_blank` before segmentation would block this error at the start.
- BM25 candidate pool ceiling: when BM25 misses the general Wikipedia article (for example, returning short titles containing `"Midwifery"` instead of the main `"Midwifery"` article, or missing `"Shipbuilding"`), Embed VL and Rerank VL cannot recover it. Adding title-prefix lookup and broader query expansion would raise pool recall above `0.75`.
- Rerank logit calibration on noisy text and images: raw logits for long OCR queries and image-to-text pairs are negative (typically `-6.5` to `-1.5`), so a single logit threshold either rejects valid matches (such as `"Firedamp"` at `-4.46`) or accepts weak candidates on noisy queries. Combining logit, margin, and exact-title checks reduced errors, and calibrating thresholds on a larger labeled set is the next step.
- Sparse volume sampling for neighbors: the source dataset holds about 13 scans per volume and rows are not consecutive printed pages. `view_neighbors` helps when a plate sits 1 or 2 rows from its treatise text (such as plates 651 and 2077), but continuation entries rarely have their preceding printed page in the dataset.

