# Retrieval ablation: BM25, embedder, reranker

This page shows what each retrieval step adds when we match Britannica entries (1771 to 1797 scans) to Wikipedia articles.
All numbers come from saved candidates. The evaluation makes no new model calls.

## Method

For each entry the match stage keeps every score (`artifacts/match/candidates/<entry_id>.json`):

1. BM25: the shared Wikipedia index returns 30 hits for "headword + distinctive terms", plus 5 hits for the headword alone.
2. Embed: `nvidia/llama-nemotron-embed-vl-1b-v2` embeds the entry (query) and each hit (title + 1,000-char excerpt, document). We keep the top 10 by cosine.
3. Rerank: `nvidia/llama-nemotron-rerank-vl-1b-v2` scores the 10 with the entry text as the query.
   - Long query: headword + entry text, cut to 2,000 chars.
   - Short query: headword (or the cleaned page topic) + the first 600 chars (`artifacts/match/candidates_short/`).

We compare the top-1 of four rankings: BM25, BM25 + embed, + rerank (long query), + rerank (short query).

## Labeled set

`artifacts/match/labels.jsonl` has 40 entries.
One reader (the match worker, Claude Opus 5.5) labeled them by reading the entry text against the candidate excerpts.
This is our own judgment, not a gold standard. There is no second annotator.

- 15 items come from the threshold check in `runs/match-threshold-check.md`. 25 items are a random sample (seed 7) of entries with 40 or more chars.
- 36 items have a real Wikipedia counterpart. 4 items have no clear counterpart (for example, page 452, where Parse produced invented text).
- For 27 of the 36, the right article is somewhere in the saved candidate pool. For 9, it is not (for example, Nazareth, Islay, Laurus, John Hughes (poet)).
- Some labels accept the closest article in the pool when the ideal one is absent (for example, Polydipsia for THIRST). The note on each item says so.

## Results

![Ablation chart](img/retrieval-ablation.png)

Source: `artifacts/match/ablation_summary.json`. Chart copy: `artifacts/match/ablation.png`.

| Method | P@1 (gold in pool, n=27) | P@1 (all 36 positives) | MRR@10 (gold in pool) | Recall@10 (all positives) | No-match accuracy (n=4) |
| --- | --- | --- | --- | --- | --- |
| BM25 | 0.30 | 0.22 | 0.42 | 0.53 | 0.00 (no reject step) |
| BM25 + embed | 0.56 | 0.42 | 0.67 | 0.69 | 0.00 (no reject step) |
| + rerank, long query | 0.70 | 0.53 | 0.79 | 0.69 | 0.75 |
| + rerank, short query | 0.70 | 0.53 | 0.81 | 0.72 | 0.75 |

Candidate pool recall: 27 of 36 (0.75). The reranker cannot fix the other 9 because BM25 never returned the right article.

What the numbers say:

- The embedder almost doubles BM25 top-1 accuracy (0.30 to 0.56). BM25 favors short pages with the same rare words. The embedder favors the page about the same subject.
- The reranker adds another 14 points (0.56 to 0.70). It reads the entry and the excerpt together, so it separates close neighbors such as "Damsel" and "Damsel in distress".
- Recall@10 is the same for embed and long rerank, because the reranker only reorders the embedder's top 10. The short-query pass also adds page-topic hits for continuation entries, so its recall is a little higher.
- Short and long queries give the same P@1. The short query ranks slightly better overall (MRR 0.81 vs 0.79).
- With our accept rules (see `runs/match-threshold-check.md`), the long-query pass accepts 13 of the 40 labeled items. 12 of these are correct. Inference: the rules are strict. They keep false matches low and leave many correct top-1 results unaccepted.
- The weakest step is candidate recall. Main articles for broad topics (Nazareth, Edward III of England) and OCR-garbled headwords (OUNDELE, ENTILADE) never reach the pool.

## Examples

Citation IDs: `[B:<row>:<n>]` for entries and `[W:<page_id>:<revision_id>]` for articles.

Rerank fixed the ranking:

1. LIGHTNING continuation [B:1910:0].
   - BM25 top-1: Ball lightning [W:194422:1353853517].
   - Embed top-1: Thunder house [W:52093675:1186402443].
   - Rerank top-1: Lightning [W:61344:1353843790] (correct).
2. DAMSEL [B:1214:1], a title for young nobles.
   - BM25 top-1: Damsel of Cyprus [W:63642434:1347192054].
   - Embed top-1: Damsel in distress [W:301517:1352628223].
   - Rerank top-1: Damsel [W:51545665:1322363950] (correct).
3. CARPENTRY treatise page, beams and forces [B:1680:0].
   - BM25 top-1: Roberval balance [W:2930612:1148459551].
   - Embed top-1: Truss [W:397263:1352695137]; Carpentry was rank 6.
   - Rerank top-1: Carpentry [W:189274:1352816782] (correct).

Rerank broke the ranking:

4. THIRST [B:1614:1].
   - Embed top-1: Polydipsia [W:600451:1350755259] (correct).
   - Rerank top-1: Thirsty (disambiguation) [W:17985120:1260172013]; Polydipsia dropped to rank 2.
   - The decision step drops disambiguation pages, so the final match is still Polydipsia. The raw rerank top-1 is wrong.

A loss from the embed filter: ENGRAVING continuation [B:1803:0].
BM25 ranked Line engraving [W:4148783:1326288842] first.
The embedder did not keep it in its top 10, so the reranker never saw it and chose Etching revival [W:3083357:1347822839].

## Limits

- 40 items, one reader. One item changes P@1 by about 4 points.
- The 4 no-match items are too few to measure rejection well.
- These checks measure ranking, not OCR quality. Parse errors upstream (page 452) make some entries unmatchable.

## Rerun

```sh
uv run python -c "from pathlib import Path; from nemotron_challenge.ablation_eval import evaluate; evaluate(Path('/Users/aly/repos/Nebius-Hackathon/artifacts'))"
```

To change labels, edit `artifacts/match/labels.jsonl` (keep `gold_titles`, `gold_page_ids`, and `note`) and rerun.
