# Team contracts

These files connect the stages. Each stage reads the files above it and writes its own.
All paths are under `artifacts/` unless stated. JSON uses UTF-8. Bboxes are page fractions `[x1, y1, x2, y2]`.

## Shared resources (not in git)

- `.env`: service URLs and keys. Never commit.
- `data/raw/britannica/*.jpg`: the 100 scans.
- Worktrees: symlink `.env`, `data`, and `artifacts` from the main checkout.

## Extract (owner: lead, done)

- `extract/raw/<row>.json`: full Parse 3.5 response plus `_run` (seconds, attempt, page_id, image_sha256). Do not edit.
- `extract/pages/<row>.json`: page record:
  `page_id, row_index, volume_id, filename, image_sha256, image_bytes, scan_path, width, height, parse_model, finish_reason, usage, blocks[]`
  Each block: `{order, cls, bbox, text}`. `cls` is a Parse class such as `Text`, `Page-header`, `Page-footer`, `Section-header`, `Picture`, `Caption`.
- `extract/failures.jsonl`: failed Parse calls.

## Segment (owner: worker "match")

- `extract/entries.jsonl`: one line per entry:
  `entry_id` (`B:<row>:<n>`), `page_id`, `row_index`, `headword` (or null for a continuation), `is_continuation`,
  `block_orders` (list), `bboxes` (list), `text_raw` (Parse text, hyphenation joined), `text_norm` (long-s and ligature fixes), `norm_edits` (count), `chars`.
- `extract/coverage.json`: pages, entries per page, blank pages, failures.

## Match (owner: worker "match")

- `match/candidates/<entry_id>.json`: BM25 hits, embed cosine, rerank logits, all kept.
- `match/matches.jsonl`: one line per processed entry:
  `entry_id, status` (`matched` | `no_clear_counterpart` | `error`), `wiki_page_id, wiki_title, wiki_revision_id, wiki_url, text_sha256`,
  `bm25_rank, embed_cos, rerank_logit, rerank_margin, method` (`bm25` | `bm25+embed` | `bm25+embed+rerank`), `reason`.
- `match/articles/<wiki_page_id>.json`: full article text with provenance, checksum verified.
- LanceDB at `data/team.lancedb`: tables `entries` and `wiki_chunks` (vector 2048-d, ids as above).

## Site (owner: worker "site")

- `latex/<row>.tex` and `latex/<row>.pdf` (tectonic), `latex/build.jsonl` (compile status per page).
- `site/` static HTML. It reads page records, entries, and matches when present.

## Compare (owner: worker "agent")

- `compare/pairs/<entry_id>.json`: Super VL output with quoted evidence from both sides; claim tags `enduring | renamed | superseded | dropped`.
- `compare/wordfreq.json` and `compare/*.png`.

## Agent (owner: worker "agent")

- `integrations/hermes/nemotron-challenge/`: tools `search_sources`, `get_pair`, `view_scan`.
- `runs/agent/<timestamp>-<slug>.json`: saved transcripts for the six cases.

Citation IDs in all answers: `[B:<row>:<n>]` for Britannica entries, `[W:<page_id>:<revision_id>]` for Wikipedia.
