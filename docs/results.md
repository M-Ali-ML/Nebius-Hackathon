# Results

The saved run is in this checkout. Open the archive before you read the table: https://huggingface.co/spaces/nebius-build-week/britannica-across-time

| Stage | Result |
| --- | --- |
| Parse 3.5 | 100 of 100 scans. 2 dense pages used a two-column fallback. 10 engraving plates. |
| Entries | 262 (176 with a headword, 76 continuations). 723 long-s and ligature repairs. |
| LaTeX | 100 of 100 PDFs. 89 two-column. |
| Match | 73 entries matched in either pass. 52 of 100 pages matched. The rest are `no_clear_counterpart` with a reason. |
| Retrieval | P@1 on 27 labeled entries in the BM25 pool: BM25 0.30, plus Embed VL 0.56, plus Rerank VL 0.70. [Details](retrieval-ablation.md) |
| Compare | 87 pairs (83 matched plus 4 rescued threshold misses), 508 quote-checked claims. Enduring 42.9%, dropped 39.2%, superseded 13.2%, renamed 4.7%. |
| Scan check | Super VL read the scan for 94 drift items: 79 were OCR errors, 15 confirmed. `find_drift` leaves out the OCR errors. |
| Topics | 14 shared topic clusters over Britannica and Wikipedia vectors. [Details](topics.md) |
| Agent | 5 tools. 3 success and 3 failure cases. [Cases](cases/README.md) |
| Atlas | One Embed VL space: 100 scans, 17 plate crops, 259 entries, 1,058 Wikipedia chunks. 92.8% of text scans have their own entry as nearest Britannica entry (chance 1.0%). [Details](atlas.md) |
| Debate | 4 debates, 20 of 20 turns. Three Hermes agents on Super VL. [Details](debate.md) |

`find_drift` is the tool added after a corpus question failed (35 calls, 435,766 tokens, no invented answer). The same question then used 62,455 tokens.

Every factual sentence cites `[B:<row>:<n>]` and `[W:<page_id>:<revision_id>]`.

Pages with no clear counterpart, and the cause of each one: [uncertainty.md](uncertainty.md).
