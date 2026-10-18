---
license: cc-by-sa-4.0
language:
  - en
pretty_name: Britannica to Wikipedia Drift
size_categories:
  - 1K<n<10K
task_categories:
  - text-retrieval
  - text-classification
  - question-answering
tags:
  - historical-text
  - ocr
  - entity-linking
  - reranking
  - hard-negatives
  - knowledge-drift
  - agents
  - nemotron
  - digital-humanities
  - wikipedia
  - britannica
configs:
  - config_name: entries
    default: true
    data_files:
      - split: train
        path: data/entries.jsonl
  - config_name: matches
    data_files:
      - split: train
        path: data/matches.jsonl
  - config_name: candidates
    data_files:
      - split: train
        path: data/candidates.jsonl
  - config_name: comparisons
    data_files:
      - split: train
        path: data/comparisons.jsonl
  - config_name: claims
    data_files:
      - split: train
        path: data/claims.jsonl
  - config_name: term_pairs
    data_files:
      - split: train
        path: data/term_pairs.jsonl
  - config_name: retrieval_labels
    data_files:
      - split: train
        path: data/retrieval_labels.jsonl
  - config_name: ablation_results
    data_files:
      - split: train
        path: data/ablation_results.jsonl
  - config_name: agent_trajectories
    data_files:
      - split: train
        path: data/agent_trajectories.jsonl
  - config_name: parse_pages
    data_files:
      - split: train
        path: data/parse_pages.jsonl
---

# Britannica to Wikipedia Drift

**How did knowledge change between the 18th-century Encyclopaedia Britannica and today's Wikipedia?**
This dataset links 262 entries from 100 scanned Britannica pages to modern Wikipedia articles, keeps every retrieval score, and splits each difference into claims that endured, were renamed, were superseded, or were dropped.
Each claim has a quote from both sides, and each quote was checked as an exact substring of its source.

- Demo (browse every page, scan, and claim): [${space_id}](${space_url})
- Code (full pipeline): [${github}](${github})

![Page view in the demo: scan with Parse 3.5 boxes, LaTeX rebuild, and the Wikipedia match with drift claims](https://huggingface.co/spaces/${space_id}/resolve/main/img_card/page.png)

## Quick start

```python
from datasets import load_dataset

claims = load_dataset("${dataset_id}", "claims", split="train")
superseded = claims.filter(lambda c: c["tag"] == "superseded" and c["quote_check"] == "passed")
print(superseded[0]["quote_britannica"], "->", superseded[0]["quote_wikipedia"])

# hard negatives for a reranker: every candidate the pipeline scored for each entry
cands = load_dataset("${dataset_id}", "candidates", split="train")
```

## Configs

| Config | Rows | One row is |
| --- | --- | --- |
| `entries` | ${n_entries} | A Britannica entry segmented from Parse 3.5 output |
| `matches` | ${n_matches} | A match decision for one entry (`level=entry`) or one page (`level=page`) |
| `candidates` | ${n_candidates} | One Wikipedia candidate scored for one entry (BM25, embed, rerank) |
| `comparisons` | ${n_comparisons} | One matched pair compared by Super VL, with similarities, differences, and drift shares |
| `claims` | ${n_claims} | One claim tagged `enduring`, `renamed`, `superseded`, or `dropped`, with quotes |
| `term_pairs` | ${n_term_pairs} | One old -> new term pair, with a `likely_ocr` flag |
| `retrieval_labels` | ${n_retrieval_labels} | A hand label for one entry, with the top-1 of each retrieval method |
| `ablation_results` | ${n_ablation_results} | Metrics for one retrieval method or one agent search mode |
| `agent_trajectories` | ${n_agent_trajectories} | One Hermes agent run: question, tool calls, answer, tokens |
| `parse_pages` | ${n_parse_pages} | One Parse 3.5 page record with ordered blocks and bboxes |

Citation ids join the configs: `B:<row>:<n>` is a Britannica entry (`entry_id`), `W:<page_id>:<revision_id>` is a Wikipedia revision.
Bboxes are page fractions `[x1, y1, x2, y2]`.

### Fields

**entries**: `entry_id`, `page_id`, `row_index`, `image_sha256`, `headword` (null for a continuation), `is_continuation`, `plate`, `running_head`, `topic_hint`, `block_orders`, `bboxes`, `text_raw` (Parse text, hyphenation joined), `text_norm` (long-s and ligature repairs), `norm_edits` (repair count), `chars`.

**matches**: `id` (`B:row:n` or `P:row`), `level` (`entry` | `page`), `row_index`, `page_id`, `entry_ids`, `headword`, `page_kind`, `page_topic`, `status` (`matched` | `no_clear_counterpart` | `error`), `wiki_page_id`, `wiki_title`, `wiki_revision_id`, `wiki_url`, `text_sha256`, `bm25_rank`, `embed_cos`, `rerank_logit`, `rerank_margin`, `method`, `tau` (logit threshold), `rule` (accept rule that fired), `title_relation`, `shared_terms`, `reason`, `why` (plain-language explanation), `uncertainty_cause`, `uncertainty_label`, `uncertainty_note`, `likely_article` (our guess at the right article when unmatched), `vision_expand_json` (Super VL query expansion from the page image, pages only). For unmatched rows the Wikipedia fields hold the best rejected candidate.

**candidates**: `entry_id`, `headword`, `plate`, `bm25_query`, `wiki_page_id`, `wiki_revision_id`, `wiki_title`, `wiki_url`, `text_sha256`, `bm25_rank`, `bm25_score`, `headword_rank`, `embed_cos`, `rerank_logit` (top 10 by embed only, else null), `excerpt` (the 1,000-char Wikipedia excerpt the models saw), `excerpt_offset`, `article_chars`.

**comparisons**: pair ids and citations, `model`, `finish_reason`, `prompt_version`, `rerank_logit`, `rerank_margin`, `similarities`, `differences`, `wiki_only_topics` (each with quotes), `quotes_kept`, `quotes_rejected`, `orthographic_edits_per_100_words`, `enduring_share`, `renamed_share`, `superseded_share`, `dropped_share`, `claim_counts`.

**claims**: pair ids and citations, `claim`, `tag`, `quote_britannica`, `quote_wikipedia` (empty for `dropped`), `quote_check` (`passed` | `failed`), `reject_reason`. Drift shares count only `passed` claims.

**term_pairs**: pair ids and citations, `old`, `new`, `likely_ocr` (the pipeline flagged the pair as OCR or spelling noise), `quote_britannica`, `quote_wikipedia`.

**retrieval_labels**: `entry_id`, `has_counterpart`, `gold_titles`, `gold_page_ids`, `gold_in_pool`, `note`, `origin`, `labeler`, then `top1_<method>` and `correct_<method>` for `bm25`, `bm25_embed`, `bm25_embed_rerank`, `bm25_embed_rerank_short`.

**ablation_results**: `study` (`match_retrieval` | `agent_search_mode`), `method`, `n_labels`, `metrics_json`.

**agent_trajectories**: `run_id` (path in the GitHub repo), `question`, `started`, `case_id` (`success-1` ... `failure-3`, or null), `case_class` (`success` | `failure`), `case_primary_run`, `ablation_mode` (`bm25_only` | `embed_only` | `full` | `hybrid`, or null), `model`, `model_ok`, `status`, `completed`, `exit_code`, `session_id`, `tool_calls` (name, input as JSON, output), `n_tool_calls`, `final_text`, `tokens_input`, `tokens_output`, `tokens_total`, `seconds`, `tool_log_json`, `events_json` (raw Hermes stream). Image data is removed; tool calls are kept.

**parse_pages**: `page_id`, `row_index`, `volume_id`, `filename`, `image_sha256`, `width`, `height`, `parse_model`, `finish_reason`, `usage_json`, `blocks` (`order`, `cls`, `bbox`, `text`).

## How it was built

1. **Sample.** 100 of 2,573 scans from the National Library of Scotland Britannica dataset, random without replacement, seed `20261016`. The choice does not depend on extraction or match quality.
2. **Parse.** `nvidia/nemotron-3.5-parse` reads each scan into ordered blocks with class and bbox. Two dense pages needed a per-column fallback.
3. **Segment.** Blocks become 262 entries. We repair the long s and ligatures (723 edits) and keep the raw text next to the repaired text.
4. **Retrieve.** BM25 over 7.18M Wikipedia articles returns 30 + 5 candidates. `nvidia/llama-nemotron-embed-vl-1b-v2` re-scores them. `nvidia/llama-nemotron-rerank-vl-1b-v2` re-ranks the top 10. The rerank logit, the margin, and exact title rules decide `matched` or `no_clear_counterpart`. Plates are matched from the image, and Super VL expands page queries from the scan.
5. **Compare.** `nvidia/Nemotron-3.5-Super-VL` writes similarities, differences, tagged claims, and term pairs, each with quotes. A substring check drops any quote not found in its source (${quotes_kept} kept, ${quotes_rejected} rejected).
6. **Agent.** A Hermes agent on Super VL answers questions with the tools `search_sources`, `get_pair`, `find_drift`, and `view_scan`. All runs are saved.

## Headline results

- Retrieval P@1 on the 40 labeled entries (gold in pool, n=27): BM25 ${p1_bm25}, + Embed VL ${p1_embed}, + Rerank VL ${p1_rerank}.
- Matches: ${pages_matched} of 100 pages, ${entries_matched} of 262 entries. Every unmatched item has a cause.
- Drift over ${claims_checked} quote-checked claims in ${pairs} pairs: enduring ${enduring}, renamed ${renamed}, superseded ${superseded}, dropped ${dropped}.
- Agent: 3 success and 3 failure cases. A corpus-wide question failed with 35 tool calls; after we added `find_drift`, the same question succeeded with 86% fewer tokens.

## Intended uses

- **Benchmark for historical-to-modern entity linking.** Noisy 18th-century OCR text, with candidates and labels, is a hard test for retrieval.
- **Hard negatives for rerankers.** `candidates` keeps every scored candidate. Many top candidates are close but wrong (for example "Ball lightning" for a LIGHTNING entry).
- **Agent failure analysis.** `agent_trajectories` keeps full tool-call traces for successes and failures, plus a search-mode ablation.
- **Knowledge drift studies.** `claims` and `term_pairs` give paired quotes for changed and unchanged facts.

## Limitations

- **OCR noise.** Parse output has long-s errors, broken words, and on one blank cover (row 452) invented text. Noise inflates the `renamed` and `superseded` shares. `likely_ocr` flags some noisy term pairs, not all.
- **One annotator.** The 40 retrieval labels and the uncertainty causes are our own judgment, from one reader (an AI coding agent working with the team). There is no second annotator and no gold standard.
- **The quote check proves presence, not support.** A passed quote exists in its source. It does not prove that the quote supports the claim.
- **Small sample.** 100 pages and one run per agent question. No variance estimate.
- **Model outputs.** Claims and tags are model output (Super VL), not human judgments.
- **Candidate pool ceiling.** If BM25 never returned the right article, embed and rerank could not recover it (pool recall 0.75 on the labeled set).

## Licenses and attribution

- This dataset: **CC BY-SA 4.0**, because it contains Wikipedia excerpts and quotes.
- Britannica scans and text: CC0, National Library of Scotland, [NationalLibraryOfScotland/encyclopaedia_britannica_illustrated](https://huggingface.co/datasets/NationalLibraryOfScotland/encyclopaedia_britannica_illustrated), revision `309f765b1ecc83e0a7f7762e44b4a927a7555443`.
- Wikipedia text: CC BY-SA 4.0, from `wikimedia/structured-wikipedia` revision `417c267b`. Every row keeps `wiki_page_id`, `wiki_revision_id`, and `wiki_url` for attribution. We store only the excerpts and quotes the pipeline used, not full articles.

## Citation

```bibtex
@misc{britannica_wikipedia_drift_2026,
  title        = {Britannica to Wikipedia Drift: entity links, retrieval scores, and quote-checked claims for 18th-century Encyclopaedia Britannica pages},
  author       = {M-Ali-ML and team},
  year         = {2026},
  howpublished = {\url{${dataset_url}}},
  note         = {Built with NVIDIA Nemotron models for Nebius Build Week. Code: ${github}}
}
```
