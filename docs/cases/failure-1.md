# Case study

Case ID: failure-1 (old terms: no corpus-wide tool, agent gives up)
Classification: failure
Run record: `runs/agent/20261018-140517-which-old-terms-in-the-britannica-have-d.json`
Code revision: 9a48f18 (agent tools, before `find_drift`); Hermes session 20261018_140518_e0915e

## Question

"Which old terms in the Britannica have different modern names in Wikipedia? Give three examples with quotes from both sides."

## Evidence

- Tool calls (35): `search_sources` x21, `get_pair` x14. `get_pair` targets: B:2493:0, B:1214:0, B:493:1, B:1268:3, B:220:0, B:2250:14, B:1268:2, B:2001:2, B:1473:4, B:2001:1, B:258:2, B:2473:6, B:493:2, B:523:8.
- 435,766 total tokens (313,344 cached), 109.9 s. Hermes exit code 1. Runner status `failed`.
- Only 2 of 14 `get_pair` calls hit a matched pair with a saved comparison: `[B:2250:14]` BYZANTIUM -> `[W:3719:1353747147]` and `[B:1268:2]` NAXOS -> `[W:62278:1351880014]`. The other 12 entries were `no_clear_counterpart`.
- At that time the saved comparisons held 112 lexical term pairs and 14 `renamed` claims. The agent had no way to list them.

## Result

The agent searched entry by entry, and most entries it picked had no match. It reported one partial candidate (NAXIA -> Naxos City) and stopped. It said "I have no third example." It did not invent examples, and it explained what was left to do.

This is a failure because the question was not answered, at about 7 times the token cost of a normal run. The agent behavior was correct (no invented evidence). The tool design was the cause: `search_sources` finds passages, and `get_pair` reads one pair, but no tool aggregates over the saved comparisons.

What it reveals:
- Agent: Super VL with only per-item tools does a costly linear scan. It guessed entries from search hits, and most of those were unmatched.
- Match: about 26% of entries were matched at that time (67 of 262), so a random walk over entries mostly lands on `no_clear_counterpart`.
- Compare: the needed data existed (term pairs with checked quotes), so this was an access gap, not a data gap.

Repair: we added `find_drift(kind, k)`, which lists checked items across all pairs with both citation ids, and a skill rule to call it first for corpus-wide questions. The repaired run is a separate case (success-3). This failed run is kept as it was.

Limits: one run only. We did not test whether a larger `--max-turns` would have reached an answer.
