# Case study

Case ID: success-3 (old terms with find_drift: the repaired run)
Classification: success
Run record: `runs/agent/20261018-140740-which-old-terms-in-the-britannica-have-d.json`
Code revision: 5fa2fd1 (adds `find_drift`); Hermes session 20261018_140742_f7bb7d

## Question

"Which old terms in the Britannica have different modern names in Wikipedia? Give three examples with quotes from both sides."

This is the same question as failure-1. It is a separate run, made after we added the `find_drift` tool.

## Evidence

- Tool calls (7): `find_drift(term_pairs, k=6)`, `find_drift(term_pairs, k=20)`, `find_drift(renamed, k=20)`, `view_scan` x4 (B:1017:11, B:560:2, B:2171:6, B:1327:8). 62,455 tokens, 83.9 s. The failed run used 35 calls and 435,766 tokens.
- `find_drift` returned 112 term pairs and 14 renamed claims across 67 pairs, each with both citation ids.
- Example 1: Britannica `[B:2171:6]` "She was daughter of Jupiter, and cast down from heaven at the birth of Hercules" / Wikipedia `[W:79071:1353135063]` "Homer calls Ate the daughter of Zeus, while Hesiod has Ate as the daughter of Eris (Strife)". Both quotes are verbatim substrings.
- Example 2: Britannica `[B:1017:11]` "bounded by the Botnhic gulph on the cafl" / Wikipedia `[W:191032:1338024466]` "It borders Gästrikland, Dalarna, Härjedalen, Medelpad and the Gulf of Bothnia". Both verbatim.
- Example 3: Britannica `[B:2171:9]` "ATERNUM, a town of Lucerna in Italy, now Alteris" / Wikipedia `[W:13770710:1352684512]` "Aternum was a Roman town, on the site of Pescara, in Italy". Wikipedia quote verbatim; OCR has "s town", not "a town".

## Result

The agent called `find_drift` first, as the skill tells it to. It rejected OCR-noise pairs by name (`tenparts`/`tenements`, `cry`/`crown`, `rife`/`rise`) and checked four scans before it chose examples. It answered in 8 calls, where the first run gave up after 35.

This is a success for the Hermes extension: one team-built tool turned a corpus-wide question that failed into an answer with resolving citations from both sides.

Limits:
- Example 3 is wrong. The full Britannica entry says the first Aternum is "now Alteris" and a second Aternum is "now Pofcara" (OCR for Pescara). The rename is Pofcara -> Pescara, not Alteris -> Pescara. So 2 of 3 examples hold.
- Example 1 is a Roman -> Greek name choice (Jupiter vs Zeus), not a change over time. Inference: it is a valid "different name", but weak as evidence of language drift.
- The `find_drift` term pairs are still noisy. The agent had to filter them with vision.
