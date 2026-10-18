# Case study

Case ID: failure-2 (plate page matched to "Fig (restaurant)")
Classification: failure
Run record: `runs/agent/20261018-141132-what-is-britannica-entry-b-651-0-about-a.json`
Code revision: f324728; Hermes session 20261018_141134_ef5566

## Question

"What is Britannica entry B:651:0 about, and what does its matched Wikipedia article say about the same subject?"

## Evidence

- Britannica `[B:651:0]`, page `britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:651`, image sha256 `a4e89a900a4041b934828dcc5c677df6edf0de903ab97d097948b7b17427da7d`. A plate page. Parse blocks: Page-header "HELMINTHOLOGY. Plate CCLI", then Caption and Picture blocks with labels only. Entry text (verbatim): "Fig 1 Fig.2. Fig.2. Fig.1. O Fig.3. Fig.3. Fig.8. Fig.7. Fig.9. Fig.9." Segment record: `plate: true`, `topic_hint: HELMINTHOLOGY`, 70 chars.
- Match: BM25 query was "fig". Candidate pool of 30 had only "Fig ..." titles. Top after rerank: "Fig (restaurant)" `[W:76464128:1346779193]` (BM25 rank 15, embed cosine 0.20, rerank logit -3.93, margin 0.43). Next: "Fig (company)" -4.36, "Fig (disambiguation)" -4.55. Logit -3.93 > tau -4.0, so status `matched`.
- Compare (`artifacts/compare/pairs/B_651_0.json`): 0 similarities, 1 difference "Subject matter", 0 claims, 1 Wikipedia-only topic "Restaurant history and awards".
- Tool calls (1): `get_pair(B:651:0)`. 16,154 tokens, 11.9 s.

## Result

The agent said the entry "is not substantive encyclopedia content", that the two sides "merely share the token Fig", and that the match is weak and uncertain (logit -3.93, margin 0.43). It cited both ids.

This is a failure of the pipeline. A plate of worms was matched to a restaurant in Charleston, and compare ran on the pair. The agent avoided a false comparison, but it did not call `view_scan`. The scan would have shown helminthology figures and let it suggest a real counterpart.

What it reveals:
- Parse: plate pages give captions such as "Fig.2." and little text. Parse also invented a footer ("Sthold Owner Walls Instagram from").
- Segmentation: the entry kept `topic_hint: HELMINTHOLOGY`, but the match stage did not use it.
- BM25 candidate pool: the query was built from entry text only ("fig"), so the correct article ("Helminthology") was never a candidate. Embed and rerank can only reorder the pool. They cannot fix a bad pool.
- Rerank: absolute logits are low for every candidate (-3.9 to -5.1). A single tau on the logit accepts the least bad candidate. The margin (0.43) was a better signal here.
- Compare: it should skip pairs with no Britannica claims. It produced a "difference" that only restates the mismatch.

Limits: one plate page. Inference: other plate pages (`plate: true`) will fail in the same way unless the BM25 query uses the running head.
