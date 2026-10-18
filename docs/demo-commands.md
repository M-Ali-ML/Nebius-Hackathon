# Demo commands (screen recording)

The video script is [video-script.md](video-script.md). This page has the browser tabs, the page controls, and the Hermes commands.

## Browser tabs to open before you record

Use the live Space and hard-refresh each tab once (Cmd+Shift+R). Base URL: https://nebius-build-week-britannica-across-time.static.hf.space

| Tab | URL path | Choreography in the 3:00 video |
| --- | --- | --- |
| Home | `/index.html` | `0:00–0:15` Hook: intro and the five cards |
| Page 1250 & Page 1910 | `/pages/1250.html` & `/pages/1910.html` | `0:15–0:40` Toggle Parse chips on scan + compiled PDF (`1250`), then show match scores (BM25 rank 2, rerank -3.75, margin 0.72, pill says matched) and the drift bar (`1910`). No uncertainty-cause pill on this page. |
| **Atlas (Wow #1)** | `/atlas.html` | `0:40–1:20` Point at `92.8%` / `88.1%`, click Guided Tours `1 -> 2 -> 3 -> 4`, toggle `Kind / Match / Drift / Topic`, zoom into scan thumbnails, drag `1797 <-> 2026` slider |
| Explore & Analysis | `/explore.html` & `/analysis.html` | `1:20–1:45` Filter claims to "superseded" and "renamed", then show Super VL Scan Check card (`79` OCR illusions filtered), 14 topic clusters, `shared_space_umap.png`, and ablation chart |
| **Debate (Wow #2)** | `/debate.html#lightning` | `1:45–2:20` Play at `2x–4x`, point at Scholar of 1790's `view_scan` tool pill fixing `"firele"` -> `"stroke"` and inline quote underlines, expand `Tool trace (3)`, press `E` for Judge's verdict |
| Hermes Terminal | Terminal | `2:20–2:50` Clip 1: blank cover `B:452:0` (`view_scan`). Clip 2: old terms (`find_drift`). Optional flash: `docs/cases/failure-2.md` (plate 651 matched to a restaurant). Plate 2077 is a `view_neighbors` success, not one of the three failures. |
| Hugging Face Space & Dataset | HF browser tabs | `2:50–3:00` Close on `nebius-build-week/britannica-across-time` and `britannica-wikipedia-drift` |

Page controls:
- **Atlas (`/atlas.html`):** Click Guided Tours `1` (`A page finds its own words`), `2` (`Plate 270 meets Hydrostatics`), `3` (`Natural History and Entomology`), `4` (`Alone in the space: HUGHILY`) in the left panel; toggle `Kind | Match | Drift | Topic` and `Edges` in the top bar; scroll to zoom into scan thumbnails; drag the `1797 <-> 2026` slider at the bottom.
- **Debate (`/debate.html#lightning`):** `Space` play/pause, `S` faster (`2x` or `4x`), `←` `→` step through turns, click `Tool trace (3)` on the Scholar of 1790's opening card, press `E` to jump to the Judge's verdict stamp, `1` to `4` to switch debate topics.

## Hermes terminal clips for the 3:00 video (`2:20–2:50`)

Because `debate.html#lightning` (`1:45–2:20`) already showcases the full Lightning comparison and `view_scan` OCR fix visually, use the 30-second terminal block (`2:20–2:50`) to show the **failures and repairs** with `/new` between them:

| Clip | Question | Shows | Screen time (2x waits) |
| --- | --- | --- | --- |
| **Clip 1 (`2:20–2:32`)** | Blank cover `B:452:0` (below) | `get_pair` + `view_scan`: catches Parse's hallucinated modern prose on a blank cover (`failure-3` repaired) | ~12 s |
| **Clip 2 (`2:32–2:50`)** | Old terms `find_drift` (below) | `find_drift(kind="term_pairs")` (scan-verified, `ocr_errors_filtered: 20`) solving the 35-call corpus-wide failure (`failure-1` -> `success-3` with 86% fewer tokens) | ~15 s |
| *(Optional)* | Plate `B:2077` (`view_neighbors`) or Lightning | Multi-page `view_neighbors` contact sheet finding `[R:2078]` *MICROSCOPE Plate CCC*, or raw CLI run of Lightning | ~10 s (cut search waits) |

## Before you record

1. Work in the main checkout (`/Users/aly/repos/Nebius-Hackathon`), not in a worktree.
2. Check that the retrieval service tunnel is up (`RETRIEVAL_BASE_URL`, `http://127.0.0.1:8000/v1`).
3. Start Hermes:

```bash
cd /Users/aly/repos/Nebius-Hackathon
export HERMES_HOME="$PWD/data/hermes"
set -a; source .env; set +a
export NEMOTRON_REPO=$PWD
export NEMOTRON_RETRIEVAL_MODE=hybrid
hermes chat --toolsets nemotron_challenge --skills britannica-compare
```

The banner must show model `nvidia/Nemotron-3.5-Super-VL`, provider `custom:tokenfactory-super`, and 5 tools. Type `/new` between questions.

## Clip 1 (`2:20–2:32`): Blank cover `B:452:0` (`view_scan` catches Parse hallucination)

Fastest visual failure-and-repair clip (23 s raw, ~10 s at 2x):

```
What does Britannica entry B:452:0 say, and how does it compare with its matched Wikipedia article?
```

Expected tool calls (rehearsal `runs/agent/demo/20261018-145209-what-does-britannica-entry-b-452-0-say-a.json`):
1. `get_pair` `B:452:0`
2. `view_scan` `B:452:0`

Point at:
- Stored OCR is repeated modern prose about `"number of cells"` matched to `"Cell counting"`, but `view_scan` shows a blank cover and the agent refuses to trust the OCR (`docs/cases/failure-3.md`).

## Clip 2 (`2:32–2:50`): Corpus-wide `find_drift` (scan-verified repair of `failure-1`)

Paste:

```
Which old terms in the Britannica have different modern names in Wikipedia? Give three examples with quotes from both sides.
```

Expected tool calls:
1. `find_drift` kind `term_pairs` (automatically filters out 20 OCR-error term pairs caught by Super VL scan check and ranks scan-confirmed historical renames first)
2. `get_pair` for the chosen entries (`"Botnhic gulph"` `[B:1017:11]` -> `"Gulf of Bothnia"` `[W:191032:1338024466]`, `"European Turkey"` `[B:604:2]` -> `"East Thrace"` `[W:2356527:1349354581]`, `"Jupiter"` `[B:2171:6]` -> `"Zeus"` `[W:360731:1343072536]`)

Point at:
- Without `find_drift`, this exact question failed after 35 tool calls and 436k tokens without inventing anything (`docs/cases/failure-1.md`).
- With `find_drift` + `Super VL` scan verification, it succeeds in 1 aggregate call with 86% fewer tokens and zero OCR noise.

## Optional Clip 3: Plate `B:2077` (`view_neighbors`) or Lightning

- **Plate `B:2077` (`view_neighbors`):**
  ```
  What does plate B:2077 show, and where in the Britannica is it explained?
  ```
  Point at: `view_scan` sees row 2077 is a blank leaf; `view_neighbors` inspects the adjacent volume scan `[R:2078]` (`MICROSCOPE. / Plate CCC.`) and describes the compound microscope figures.
- **Lightning (`search_sources` + `get_pair` + `view_scan`):**
  ```
  What did the Britannica say about lightning, and how does Wikipedia explain it today? Did the language or the knowledge change?
  ```
- **Topic clusters (`find_drift` kind `topics`):**
  ```
  What topic clusters do you have across the Britannica and Wikipedia embeddings?
  ```
- **Missing evidence (Neptune):**
  ```
  What does the Britannica say about the planet Neptune?
  ```
