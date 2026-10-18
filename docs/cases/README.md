# Case studies

Six cases from saved Hermes runs on the real pipeline output (100 pages, 262 entries, 67 matched pairs).
Each case links to its transcript in `runs/agent/`. `uv run nemotron-challenge run evaluate` checks the links and writes `runs/evaluate.json`.

| Case | Class | Question | Tools | Tokens | What it shows |
| --- | --- | --- | --- | --- | --- |
| [success-1](success-1.md) | success | Lightning: did language or knowledge change? | search x3, get_pair, view_scan | 62,764 | Drift split, uncertain match reported, scan read |
| [success-2](success-2.md) | success | Coinage claims that still hold | search x2, get_pair, view_scan | 63,314 | Enduring vs changed claims, both sides cited |
| [success-3](success-3.md) | success | Old terms with modern names (rerun) | find_drift x3, view_scan x4 | 62,455 | Team tool repairs failure-1 (2 of 3 examples correct) |
| [failure-1](failure-1.md) | failure | Old terms with modern names (first run) | search x21, get_pair x14 | 435,766 | No corpus-wide tool; agent gave up, invented nothing |
| [failure-2](failure-2.md) | failure | Plate B:651:0 | get_pair | 16,154 | Plate matched to "Fig (restaurant)"; bad BM25 pool |
| [failure-3](failure-3.md) | failure | Blank cover B:452:0 | get_pair | 18,151 | Parse invents text; error passes through every stage |

Changes from the first pick: firedamp was replaced by coinage. In the real-data run, B:1214:0 -> Firedamp had logit -4.46, below tau -4.0, so no comparison exists. Its "phlogiston superseded" answer exists only in a fixture run.

## Where the agent does well

- It cites every factual sentence with `[B:row:n]` and `[W:page_id:revision_id]`. Ids in the sampled answers resolve to the right sources.
- It reports uncertainty. In the runs we read, it gave the match status, logit, and margin when a pair was weak (success-1, failure-2, failure-3, magnetism, optics).
- It refuses to fill gaps. Neptune (`runs/agent/20261018-140335-...`): "No evidence found in Britannica", with the 1846 discovery labeled as inference. Firedamp: "I can't confirm it" when the pair was below tau. failure-1: no invented examples.
- It uses vision to check OCR. In 10 of 14 runs it called `view_scan` and named concrete OCR errors (Erfurt "capital of Thailand" is "Thuringia" on the scan).
- With the right tool it is cheap: 13 of 14 runs used 16k to 70k tokens and 12 to 84 s per question.

## Where it struggles

- Corpus-wide questions without an aggregate tool (failure-1: 35 calls, 436k tokens, no answer).
- It quotes its own scan reading inside quotation marks. The Britannica "quotes" in success-2 are not verbatim OCR. Users cannot tell scan readings from OCR text.
- It does not call `view_scan` when the content, not the spelling, looks wrong (failure-2, failure-3).
- It accepts the drift labels from compare. In the Erfurt run it saw that OCR errors had been tagged as superseded facts, but the counts it reported still include them.

## What the failures reveal about the pipeline

- Parse: a budget failure plus the column-split fallback made fluent invented text on a blank cover (failure-3). Plate pages give only figure labels (failure-2). Long s and broken words are frequent. These are reading errors, not language change.
- Segmentation: no check that an entry looks like 18th-century text. The plate topic (running head) is kept but not used downstream.
- BM25 candidate pool: the pool decides the ceiling. If the right article is not among the 30 BM25 hits, embed and rerank cannot recover it (failure-2).
- Embed and rerank: absolute logits are low (-3 to -6) even for correct pairs. A single logit tau accepts the least bad candidate on garbage input (margins 0.08 and 0.43) and rejects some correct pairs (Firedamp, -4.46). The margin is a useful second signal.
- Compare: the quote check proves that quotes exist, not that they support the claim or that the source is real. OCR errors inflate the "superseded" share (Erfurt: 4 of 5 claims superseded, mostly OCR). 79 of 191 term pairs looked like OCR or spelling noise.
- Agent: one aggregate tool (`find_drift`) cut tokens by 86% on the corpus question. Inference: more aggregate tools would help more than better prompts.

## Limits

- 6 cases from 14 real-data runs. One run per question. No repeated runs to measure variance.
- Classification is our judgment from the evidence in each file. We checked a sample of quotes by hand against the sources, not all.
- Runs before 14:10 used tool code at `9a48f18` or `5fa2fd1`; later runs used `f324728`. The match stage changed during the day (tau -4.0 at run time).

## Agent economics: retrieval ablation

We ran the same 7 questions through Hermes with three `search_sources` modes, set by `NEMOTRON_RETRIEVAL_MODE`:

- `bm25_only`: Wikipedia BM25 API over the full 7.18M-article corpus, plus a BM25 keyword match over Britannica entries. No embed, no rerank.
- `embed_only`: query embedding and LanceDB cosine search over `entries` and `wiki_chunks` (matched articles only). No rerank.
- `full`: embedding, LanceDB search, then the reranker (the default).

The other tools (`get_pair`, `find_drift`, `view_scan`) are the same in every mode.
Questions: lightning, magnetism, coinage, Huguenots, Erfurt, firedamp, Neptune (expected: no evidence).
Transcripts: `runs/agent/ablation/<mode>/`. Numbers: `runs/agent/ablation/summary.json`.

| Mode | Runs ok | Mean tool calls | Mean tokens | Mean latency | Answered / no evidence | Right B entry cited | Right W page cited | Citations | Unresolved citations | Both sides grounded (hand check) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bm25_only | 7/7 | 3.7 | 60,524 | 29.2 s | 6 / 1 | 6/6 | 6/6 | 15 | 0 | 6/6 |
| embed_only | 7/7 | 4.3 | 71,035 | 38.3 s | 6 / 1 | 6/6 | 6/6 | 19 | 0 | 5/6 |
| full | 7/7 | 4.3 | 66,688 | 38.6 s | 6 / 1 | 6/6 | 6/6 | 15 | 0 | 5/6 |

How we measured:
- Tool calls count our tools only, not Hermes meta tools (`tool_search`, `tool_call`, `tool_describe`).
- "No evidence" means the answer opens with a no-evidence statement. In all modes that was only Neptune, which is correct.
- "Right B entry / W page cited" means the final answer cites the entry and page we know are correct for the question.
- "Unresolved" means a cited id names no real entry, or no Wikipedia page at that revision. We checked it against `extract/entries.jsonl`, `match/articles/`, and the Wikipedia API.
- Hand check: we read all 21 answers. For firedamp we matched quoted Wikipedia fragments against the Firedamp article text.

What it shows:
- For questions about entries that have a saved pair, retrieval mode changed little. The agent only needs search to find the Britannica entry; `get_pair` then supplies the Wikipedia side from the match stage. In this setup the match stage, not `search_sources`, decides answer quality.
- bm25_only was the cheapest (about 10% fewer tokens than full, 9 s faster).
- Firedamp separated the modes. B:1214:0 -> Firedamp is below tau, so Firedamp is not in `wiki_chunks`. bm25_only searched the full Wikipedia corpus, found Firedamp at rank 1, and quoted it (3 fragments verbatim). embed_only and full could only cite the id from `get_pair`, and both said they could not quote Wikipedia. They did not fill the gap from memory. The limit is the index coverage, not embed or rerank.
- Retrieval quality itself is measured on the match side (`artifacts/match/ablation_summary.json`, 40 hand-labeled entries by the match worker): P@1 is 0.22 for BM25, 0.42 for BM25+embed, 0.53 for BM25+embed+rerank. Embed and rerank pay off when they pick the article; once a pair is saved, the agent does not need them again.
- Inference: the best agent setup is hybrid. Use the vector index for Britannica search, and fall back to the Wikipedia BM25 API when the saved pairs have no counterpart.

Limits: 7 questions, one run each. The questions name their topics, which favors keyword search. Hermes `stream-json` cuts tool output in transcripts at 5,000 chars; the runner now also saves full tool results in `tool_log` (runs after commit e322c45 plus this fix).
