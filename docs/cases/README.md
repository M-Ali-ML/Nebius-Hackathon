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
