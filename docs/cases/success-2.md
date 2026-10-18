# Case study

Case ID: success-2 (coinage: enduring vs superseded claims with quotes from both sides)
Classification: success
Run record: `runs/agent/20261018-140224-which-britannica-claims-about-coining-mo.json`
Code revision: 9a48f18 (agent tools); Hermes session 20261018_140226_8f720c

## Question

"Which Britannica claims about coining money in a mint still hold today according to Wikipedia?"

## Evidence

- Britannica entry `[B:1250:1]` headword COINAGE, page `britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:1250`, image sha256 `2e0c75f854185185ace0f165eea2b904222208282d93a1c66b97c9b5c42f5c95`. OCR opening (verbatim): "COINAGE, or Coining, the art of making ma-ery, as performed either by the hammer or mill."
- Wikipedia `[W:24057311:1345146028]` "Coining (mint)". Quotes (verbatim, checked): "the process used in both hammered coinage and milled coinage"; "coin dies were manufactured individually by hand by artisans known as engravers"; "the planchet is not heated".
- Match record: `matched`, rerank logit -3.22, margin 1.35, `uncertain_match: false`.
- Saved comparison `artifacts/compare/pairs/B_1250_1.json`: 7 checked claims.
- Tool calls (4): `search_sources` x2, `get_pair(B:1250:1)`, `view_scan(B:1250:1)`. 63,314 tokens, 19.9 s.

## Result

The agent answered with four enduring claims (hammer or mill; engravers cut dies; dies are hardened; one fixed and one movable die) and three claims that no longer hold (blanks cut with a trepan; planchets boiled before striking, against Wikipedia "the planchet is not heated"; edge lettering limited to crowns). Each claim has a Britannica and a Wikipedia citation.

Lead pick was firedamp. We replaced it. In the real-data run (`runs/agent/20261018-140244-what-did-the-britannica-say-about-inflam.json`), B:1214:0 -> Firedamp had rerank logit -4.46, just below tau -4.0, so it was `no_clear_counterpart` and has no saved comparison. The agent correctly said it could not confirm a change. The "phlogiston superseded" answer exists only in a dev-fixture run (`runs/agent/dev-fixture/`), so it cannot be a case.

This is a success because the answer is grounded on a confident match, splits enduring from changed knowledge, and the Wikipedia quotes resolve.

Limits:
- Several Britannica "quotes" in the answer are the agent's scan-based reading, not the OCR text. Example: the answer quotes "the art of making money", the OCR says "making ma-ery"; the answer says "dies", the OCR says "dyas". The answer states that it verified wording against the scan, but it presents corrected text inside quotation marks.
- The Wikipedia support for "one die remains fixed" is weak ("one per each side of the coin" does not say one is fixed). Inference: this claim should be "dropped", not "enduring".
