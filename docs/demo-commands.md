# Demo commands (screen recording)

Three questions, about 40 s of screen time each. Each one has a saved rehearsal transcript in `runs/agent/demo/`.

## Recommended run for the video

Record these four, in this order, with `/new` between them. Together they show every tool and both kinds of honesty.

| # | Question | Shows | Screen time |
| --- | --- | --- | --- |
| 1 | Lightning (Question 1 below) | Hybrid search, `get_pair` drift split (language vs knowledge), `view_scan` reading the page, citations on both sides, uncertain match reported | about 35 s |
| 2 | Plate B:2077 (Question 2) | `view_neighbors`: a blank plate leaf, explained by the next scan (MICROSCOPE Plate CCC) | about 40 s after cutting the searches |
| 3 | Blank cover B:452:0 (alternate Question 3) | `view_scan` catches a Parse hallucination that passed every pipeline stage | about 25 s |
| 4 | Neptune: `What does the Britannica say about the planet Neptune?` | Says "No evidence found in Britannica" and labels the 1846 discovery as inference | about 15 s |

If you have time for a fifth, use the old-terms question (Question 3) to show `find_drift`. Point only at "Botnhic gulph" to "Gulf of Bothnia"; other pairs in that answer are often OCR noise.

## Before you record

1. Work in the main checkout, not in a worktree. The Hermes profile lives in the main checkout's `data/hermes`; a worktree has none, and Hermes then starts an empty profile ("Unknown toolsets", 0 tools, model unknown).
2. Check that the retrieval service tunnel is up (`RETRIEVAL_BASE_URL`, http://127.0.0.1:8000/v1).
3. Install the current plugin and skill into the Hermes profile. Run from the repository root:

```bash
export HERMES_HOME="$PWD/data/hermes"
rm -rf "$HERMES_HOME/plugins/nemotron-challenge"
cp -R integrations/hermes/nemotron-challenge "$HERMES_HOME/plugins/"
cp -R integrations/hermes/skills/britannica-compare "$HERMES_HOME/skills/research/"
hermes plugins doctor integrations/hermes/nemotron-challenge --ci   # expect: 5 tool(s)
hermes plugins list | grep nemotron                                # expect: enabled 0.4.0
```

## Start Hermes

```bash
cd /path/to/Nebius-Hackathon                # the main checkout, not a worktree
export HERMES_HOME="$PWD/data/hermes"
set -a; source .env; set +a                 # loads SUPER_API_KEY and the service URLs
export NEMOTRON_REPO=$PWD                    # tool code runs from this checkout
export NEMOTRON_RETRIEVAL_MODE=hybrid        # the default; set it so the screen shows it
hermes chat --toolsets nemotron_challenge --skills britannica-compare
```

The banner must show model `nvidia/Nemotron-3.5-Super-VL`, provider `custom:tokenfactory-super`, and 5 tools.
If it shows 3 tools, Hermes Tool Search is on: the 5 tools hide behind `tool_search` / `tool_describe` / `tool_call`. They still work, but the trace is noisier. For the video, turn it off in `data/hermes/config.yaml`:

```yaml
tools:
  tool_search:
    enabled: off
```

The saved rehearsals below ran with Tool Search on, so live runs can show fewer calls than listed. Type `/new` between questions so that each question starts with an empty context (images from an earlier question count toward the 8-image limit).

## Question 1: language vs knowledge (drift split + scan)

Paste:

```
What did the Britannica say about lightning, and how does Wikipedia explain it today? Did the language or the knowledge change?
```

Expected tool calls (rehearsal `runs/agent/demo/20261018-144505-what-did-the-britannica-say-about-lightn.json`, 34 s, 81k tokens):
1. `search_sources` query "lightning", side both (hybrid: LanceDB plus live Wikipedia BM25)
2. `get_pair` B:1910:0 (saved comparison and drift block)
3. `view_scan` B:1910:0 (Super VL reads the original page)

Point at:
- The agent reads the scan and fixes the OCR: "returning firele" in the OCR is "returning stroke" on the page. Running head "L I G H T N I N G", page 423.
- Citations on both sides: `[B:1910:0]` and `[W:61344:1353843790]`.
- The drift split: language changed (old terms such as "electric fire", "prime conductor"), and knowledge changed (the "returning stroke through the body" model is superseded by stepped leader and return stroke).
- The uncertain-match note (rerank margin 0.72 below 1.0).

## Question 2: a plate explained on another page (view_neighbors)

Paste:

```
What does plate B:2077 show, and where in the Britannica is it explained?
```

Expected tool calls (rehearsal `runs/agent/demo/20261018-144539-what-does-plate-b-2077-show-and-where-in.json`, 96 s, 92k tokens; cut the search part in the edit):
1. `search_sources` x2 (finds nothing useful: the page is blank)
2. `view_scan` 2077 (a blank leaf)
3. `view_neighbors` 2077 (one combined image of the next scan)
4. `view_neighbors` with before 2, after 2
5. more `search_sources`, then `get_pair` P:2077

Point at:
- Row 2077 itself is blank. The agent says so from the image.
- The next scan `[R:2078]` has the running head "MICROSCOPE. / Plate CCC." and shows a compound microscope in lettered figures.
- It checks the other neighbor `[R:2079]` ("MID", page 760) and says that page does not explain the plate. It does not invent the page that does.

## Question 3: corpus-wide drift (find_drift)

Paste:

```
Which old terms in the Britannica have different modern names in Wikipedia? Give three examples with quotes from both sides.
```

Expected tool calls (rehearsal `runs/agent/demo/20261018-144715-which-old-terms-in-the-britannica-have-d.json`, 47 s, 66k tokens):
1. `find_drift` kind term_pairs (one call over all 83 saved comparisons)
2. `get_pair` x3 for the chosen entries
3. `find_drift` again with k 20

Point at:
- One tool call searches all saved comparisons. Without `find_drift` the same question took 35 calls and 436k tokens and failed (`docs/cases/failure-1.md`).
- "Botnhic gulph" `[B:1017:11]` and "Gulf of Bothnia" `[W:191032:1338024466]`, with quotes from both sides.
- The agent's own caveat: it dropped OCR-noise pairs ("tenparts" to "tenements", "cry" to "crown").
- Be careful: in the rehearsal, "rife" to "common use" is an OCR error for "rise", and "Zie Grafjnaar" is OCR for "The Craftsman". Do not present those two as real renames.

## Alternate question 3: blank cover (view_scan catches a Parse error)

Short and visual. Use it if question 3 gives OCR-noise examples on the day.

```
What does Britannica entry B:452:0 say, and how does it compare with its matched Wikipedia article?
```

Rehearsal `runs/agent/demo/20261018-145209-what-does-britannica-entry-b-452-0-say-a.json`, 23 s, 37k tokens: `get_pair` B:452:0, then `view_scan` B:452:0. Point at: the stored text is repeated modern prose about "number of cells", the scan is a blank cover, and the agent says the OCR cannot be trusted. The original failure is `docs/cases/failure-3.md`.

## Do not use in the demo

- `runs/agent/demo/20261018-144811-which-facts-in-the-18th-century-britanni.json` ("superseded facts"). It looks good but example 2 is wrong: the OCR says the ounce is the "fitteenth" part of a pound, the scan says "ſixteenth". The compare stage and the agent both took an OCR error as a superseded fact.
- `runs/agent/demo/20261018-144845-find-three-britannica-claims-where-the-f.json` (renamed claims, checked against scans). It hit the turn limit (24 calls, 319k tokens). Finding: of 20 "renamed" candidates the agent kept only 2 after it checked the scans.
- `runs/agent/demo/first-attempt/`: the first rehearsal. It ran in `full` mode by mistake, and the plate question failed with the 8-image limit. Fixed in `3402ab4`.
