# Case study

Case ID: failure-3 (blank cover: Parse invents text, the error cascades to match and compare)
Classification: failure
Run record: `runs/agent/20261018-141143-what-does-britannica-entry-b-452-0-say-a.json`
Code revision: f324728; Hermes session 20261018_141145_d718e0

## Question

"What does Britannica entry B:452:0 say, and how does it compare with its matched Wikipedia article?"

## Evidence

- Scan `data/raw/britannica/page-0452-233256cb3c3c.jpg`, image sha256 `233256cb3c3c25e03e847aa65e26f3e82cd05f8ef6e302c7ce69fe42a042f2cf`. We looked at it: it is a blank cloth book cover with a leather spine. There is no printed text.
- Parse raw reply `artifacts/extract/raw/452.json`: the full-page call failed with `full_page_error: "ProtocolError: chat response is incomplete; inspect the token budget and finish_reason"`. The extract stage then used `strategy: column_split`. The left half returned one Text block (bbox [0.0, 0.0, 0.4995, 0.9992]) of invented modern prose: "We have used the same method to calculate the number of cells that are used to generate a single cell size." repeated about 10 times. The right half returned a Page-footer "50".
- Entry `[B:452:0]`: 1,428 chars, `is_continuation: true`, no headword, `norm_edits: 0`.
- Match: BM25 query "cells calculate used generate cell single size method number ...". Top after rerank "Cell counting" `[W:32690554:1340592923]` (BM25 rank 2, embed cosine 0.28, logit -3.66, margin 0.08). Next: "Single-cell analysis" -3.74. Status `matched`.
- Compare (`artifacts/compare/pairs/B_452_0.json`): 1 difference, 5 Wikipedia-only topics (counting chambers, colony forming units, ...), 0 claims. All 6 quotes passed the substring check.
- Tool calls (1): `get_pair(B:452:0)`. 18,151 tokens, 13.5 s.

## Result

The agent called the Britannica text "repetitive, near-degenerate", said it "carries no substantive encyclopedic content", flagged the match as uncertain (margin 0.08), and gave an inference that the text is "corrupted or truncated extraction text rather than a real 1771-1797 article". It still listed five Wikipedia-only topics as if coverage had been compared.

This is a failure because one Parse hallucination passed through every stage: segment made an entry, BM25 found a topical article, embed and rerank accepted it, compare produced "differences" and "Wikipedia-only topics" with valid quotes, and the coverage drift counts them. The agent did not call `view_scan`. One look at the blank cover would have settled it.

What it reveals:
- Parse: a full-page budget failure plus the column-split fallback on a blank image produced fluent, repeated text. Repetition is a cheap detection signal.
- Segmentation and match: no stage checks that the text looks like 18th-century English (no long s, no headword, modern words such as "system" and "method").
- Rerank: margin 0.08 is the lowest kind of signal, but the logit rule ignored it.
- Compare: the quote check proves quotes exist, not that the source is real. Garbage in still passes.
- Agent: it reasoned well from text alone, but the skill only asks it to view the scan when OCR looks wrong, not when the content looks impossible.

Limits: one page. Only 2 of 100 pages used the column-split fallback (rows 452 and 2243); we did not inspect row 2243.
