# Technical record

Maps: [who runs what](diagrams/who-runs-what.svg), [steps](diagrams/pipeline.svg), [Hermes](diagrams/hermes.svg). Setup commands: [README](../README.md).

## Models

| Role | Model ID | Revision or host | Called from |
| --- | --- | --- | --- |
| Page extraction | `nvidia/nemotron-3.5-parse` | Shared event endpoint | `parse` |
| Embedding | `nvidia/llama-nemotron-embed-vl-1b-v2` | `582e3bf72aee355e3c59ed89de53543c5b0657ee` | `match`, `search_sources`, plate match |
| Reranking | `nvidia/llama-nemotron-rerank-vl-1b-v2` | `b8a9987b05b75db5ad949c825cbcbf6eb7c48b5a` | `match`, `search_sources`, plate match |
| Compare and agent | `nvidia/Nemotron-3.5-Super-VL` | Nebius Token Factory | `compare`, `plates`, Hermes |

Embed and rerank run in one container: PyTorch `2.8.0+cu128`, CUDA 12.8, Transformers 4.56.2, bfloat16, SDPA, one request at a time. The tested GPU is an NVIDIA RTX PRO 6000 Blackwell (96 GB). Receipt: `runs/model-service-smoke.json`. Build notes: [docs/model-service.md](model-service.md).

Pipeline calls to Super VL use thinking off and temperature 0.2. Entry text is cut at 8,000 characters. Article text is cut at 10,000 characters.

## HTTP APIs

Base URLs come from `.env`. See `.env.example`.

| Client | Method and path | Auth | What the caller sends | What we keep |
| --- | --- | --- | --- | --- |
| Parse | `POST {PARSE_BASE_URL}/chat/completions` | `PARSE_API_KEY` if the host requires it. The event tunnel does not. | Page image as a data URL, temperature 0 | Raw reply in `artifacts/extract/raw/<row>.json` |
| Wikipedia corpus | `GET {WIKIPEDIA_API_URL}/ready`, `GET /v1/corpus` | none |  | Revision check: `417c267bb457fa645c22eb3b5c77764963194c70`, 7,182,883 articles |
| Wikipedia search | `POST /v1/search` | none | `query`, `top_k` 1 to 100, `excerpt_chars` 100 to 2,000 | page id, revision id, title, url, excerpt, sha256 |
| Wikipedia article | `GET /v1/articles/{page_id}?offset=&max_chars=` | none | page id | Full text, followed with `next_offset`, sha256 checked |
| Embeddings | `POST {RETRIEVAL_BASE_URL}/embeddings` | `RETRIEVAL_API_KEY` if set | `input`, `input_type` `query` or `document` | 2,048-d unit vector. `query` is text. `document` may include a PNG or JPEG data URL. |
| Rerank | `POST {RETRIEVAL_BASE_URL}/rerank` | same | text `query`, `documents`, optional `top_n` | `relevance_score` is a raw logit, not a probability |
| Super VL | `POST {SUPER_BASE_URL}/chat/completions` | `SUPER_API_KEY` | messages, optional tools | model id, finish reason, text or tool calls |

Retrieval routes also expose `GET /health`, `GET /ready`, and `GET /v1/models`. The service checks weight hashes before it loads. Input limits are in [docs/model-service.md](model-service.md).

Wikipedia field rules are in [docs/wikipedia-api.md](wikipedia-api.md).

`uv run nemotron-challenge doctor --live` checks the four catalogs. It does not run a match or a comparison.

## Hermes tools

Plugin `integrations/hermes/nemotron-challenge` version 0.4.0. Skill `britannica-compare`. Setup: [docs/hermes.md](hermes.md).

| Tool | Arguments | Returns |
| --- | --- | --- |
| `search_sources` | `query`, `side` (`britannica`, `wikipedia`, `both`), `k` 1 to 10 | Passages, citation ids, rerank logit, `low_confidence`, `side_confidence`. Mode `NEMOTRON_RETRIEVAL_MODE`: `hybrid` (default), `full`, `embed_only`, `bm25_only`. |
| `get_pair` | `entry_id` `B:<row>:<n>` or `P:<row>` | OCR text, normalized text, match record, article excerpt, saved comparison, drift block |
| `find_drift` | `kind` one of `renamed`, `superseded`, `dropped`, `enduring`, `term_pairs`, `wiki_only_topics`; `k` 1 to 20 | Checked items across all pairs, with both citation ids |
| `view_scan` | `page`, optional `bbox` as page fractions | JPEG of the scan or crop, plus page id and checksum |
| `view_neighbors` | `page`, `before` 0 to 2, `after` 0 to 2 | One combined image, Parse text, running heads. Cite a neighbor as `[R:<row>]`. |

The handler shells out to `python -m nemotron_challenge.agent_tools` so the Hermes runtime does not import LanceDB. Set `NEMOTRON_REPO` to this checkout.

## Frameworks and packages

| Piece | Version in this run | Role |
| --- | --- | --- |
| Python | `>=3.12,<3.14` | Pipeline |
| uv | lockfile `uv.lock` | Install and run |
| httpx | 0.28.1 | HTTP clients |
| pydantic | 2.14.1 | Response checks |
| python-dotenv | 1.2.4 | `.env` |
| lancedb | 0.40.0 | Evidence index |
| pyarrow | 21.0.0 | Source Parquet and LanceDB |
| huggingface-hub | 2.2.0 | Scan download and publish |
| pillow | `>=13` | Scan crops |
| jinja2 | `>=3.1.6` | Static site |
| matplotlib | `>=3.11` | Drift and word-frequency plots |
| pytest | 9.1.1 | Contract tests |
| tectonic | on `PATH` | LaTeX to PDF |
| Hermes Agent | v0.22.2 | Agent runtime |
| Docker | linux/amd64, NVIDIA Container Toolkit | Embed and rerank |

Code license: MIT. See [ATTRIBUTION.md](../ATTRIBUTION.md).

## Commands

Run from the repository root.

| Command | Calls | Writes |
| --- | --- | --- |
| `nemotron-challenge data fetch` | Hugging Face, no token | `data/raw/britannica/` |
| `nemotron-challenge parse` | Parse 3.5, skipped when `extract/raw/<row>.json` exists | `artifacts/extract/raw`, `artifacts/extract/pages` |
| `nemotron-challenge run extract` | local rules | `artifacts/extract/entries.jsonl` |
| `nemotron-challenge run match` | Wikipedia, Embed VL, Rerank VL | candidates, matches, articles, LanceDB |
| `nemotron-challenge run compare` | Super VL | `artifacts/compare/` |
| `nemotron-challenge run site` | tectonic | `artifacts/latex/`, `site/` |
| `nemotron-challenge plates` | Super VL, Embed VL, Rerank VL | `artifacts/plates/` |
| `nemotron-challenge run agent` | Hermes and Super VL | `runs/agent/*.json` |
| `nemotron-challenge run evaluate` | local files | `runs/evaluate.json` |
| `pytest` | local fakes | no model calls |

`run extract` segments page records that already exist. It does not call Parse. Use `parse` first on a checkout that has no `artifacts/extract/pages`.

## Files a jury can open without a key

| Path | Content |
| --- | --- |
| `site/index.html` | Archive: scan, LaTeX, match, drift |
| `site/how.html` | The three maps |
| `site/analysis.html` | Coverage, drift bar, word frequencies |
| `docs/cases/` | 3 success and 3 failure studies |
| `docs/retrieval-ablation.md` | BM25, embed, rerank on 40 labels |
| `docs/uncertainty.md` | Why an item stayed unmatched |
| `artifacts/extract/` | Raw Parse replies and entries |
| `artifacts/match/` | Candidates, scores, decisions |
| `artifacts/compare/` | Quote-checked pairs and drift |
| `runs/agent/` | Hermes transcripts |
| `runs/evaluate.json` | Model ids, revisions, case link check |

These are not in git: `data/raw/` (scans), `data/team.lancedb`, `data/hermes`, `artifacts/match/vectors/`, `.env`.

## Sources

| Source | Pin |
| --- | --- |
| Britannica `NationalLibraryOfScotland/encyclopaedia_britannica_illustrated` | revision `309f765b1ecc83e0a7f7762e44b4a927a7555443`, CC0 |
| Sample manifest | `src/nemotron_challenge/resources/britannica-manifest.json`, sha256 `779542e078756874f23fa6971d7d8a2d8635ad6d9d9484e1deb607d94a28e396`, 100 of 2,573, seed `20261016` |
| Wikipedia `wikimedia/structured-wikipedia` | revision `417c267bb457fa645c22eb3b5c77764963194c70`, CC BY-SA 4.0 |

Stage file layouts: [docs/team-contracts.md](team-contracts.md).
