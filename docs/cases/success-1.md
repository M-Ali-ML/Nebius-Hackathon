# Case study

Case ID: success-1 (lightning: language and knowledge change, uncertain match flagged)
Classification: success
Run record: `runs/agent/20261018-140114-what-did-the-britannica-say-about-lightn.json`
Code revision: 9a48f18 (agent tools); Hermes session 20261018_140116_090b7b

## Question

"What did the Britannica say about lightning and electricity, and how does Wikipedia explain lightning today? Did the language or the knowledge change?"

## Evidence

- Britannica entry `[B:1910:0]`, page `britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:1910`, image sha256 `f4723acc17718590625f337a0d5ddeef3e257ff963f793fe287f0f0cb81834ee`. Continuation entry with no headword. OCR quote (verbatim, checked as a substring): "when a returning firele comes to be produced by the fuddro removal of the very frong elafic electrical prefi-fore of the electrical atmosphere of a thunder-cloud powerfully charged".
- Wikipedia `[W:61344:1353843790]` "Lightning". Quotes (verbatim, checked): "Lightning is a natural phenomenon consisting of electrostatic discharges occurring through the atmosphere between two electrically charged regions"; "Lightning involves a near-instantaneous release of energy on a scale averaging between 200 megajoules and 7 gigajoules".
- Match record: status `matched`, rerank logit -3.75 (tau -4.0), margin 0.72, so `uncertain_match: true`.
- Saved comparison `artifacts/compare/pairs/B_1910_0.json`: 8 checked claims, 4 superseded, 2 enduring, 2 dropped. Term pairs include "prime conductor" -> "lightning rod" and "electrical atmosphere" -> "electric field".
- Tool calls (5): `search_sources` x3 ("lightning electricity", "lightning", "electricity"), `get_pair(B:1910:0)`, `view_scan(B:1910:0)`. 62,764 tokens, 25.9 s.

## Result

The agent found the entry through `search_sources` and loaded the pair and drift block with `get_pair`. It then read the page scan with `view_scan` before it quoted. It separated the drift signals: orthographic (1.61 spelling edits per 100 words, which it calls OCR noise), lexical (old -> new terms), knowledge (4 of 8 claims superseded: the "returning flash" mechanism vs the stepped leader and return stroke model), and coverage (Wikipedia-only topics such as energy and lightning types). It reported the uncertain match with logit and margin, and it labeled its summary as "Inference:".

This is a success because every factual sentence carries a `[B:...]` or `[W:...]` id that resolves to the right source, the sampled quotes are real substrings, the uncertainty is stated, and the answer uses all three tools as designed.

Limits:
- The agent corrected OCR from the scan in its explanation ("returning flash" for "returning firele"). That reading comes from Super VL vision. No second check confirms it.
- The agent disagreed with one drift label: the system flagged "electric fire" -> "electric charge" as likely OCR. The agent said "electric fire" is real period language. Both are labels, not ground truth.
- Inference: the match is correct (the entry is the LIGHTNING article), but the reranker margin was small. A small change in tau could lose it.
