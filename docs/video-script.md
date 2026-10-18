# Video script (3:00)

Record the screen at 1080p. Keep `site/` open in a browser and Hermes in a terminal.
Each block lists what to show and what to say. Times are targets.

## 0:00 to 0:20 Hook

Show: `site/index.html`, then one scan page.
Say: "The 18th-century Britannica explains lightning as 'electric fire' from a charged 'electrical atmosphere'. Wikipedia measures it in gigajoules and return strokes. We built a pipeline that finds out what changed: the spelling, the words, the facts, or the coverage. Every step runs on Nemotron."

## 0:20 to 0:50 Parse 3.5 and the LaTeX archive

Show: a two-column page. Toggle the bbox overlay by class. Open the compiled PDF next to it. Point at a red marker for an invented character.
Say: "Parse 3.5 reads all 100 scans into ordered blocks with classes and boxes. We keep reading order and headings in a LaTeX archive. Two dense pages looped past the token limit, so we parse each column. We show OCR errors, we do not hide them."

## 0:50 to 1:25 Matching with Embed VL and Rerank VL

Show: a page with matches, scores, and one `no_clear_counterpart` badge. Then `docs/retrieval-ablation.md` chart. Then the Hydrostatics plate page.
Say: "For each entry, BM25 gives 30 Wikipedia candidates, Embed VL keeps 10, Rerank VL decides. On 40 entries we labeled, top-1 accuracy goes from 0.30 with BM25 to 0.56 with the embedder to 0.70 with the reranker. When no candidate is good enough, we say so. Plates have no text: Super VL describes the engraving, and both vision models compare the image itself. BM25 picks 'Hydrostatic skeleton'. The image picks 'Hydrostatics'."

## 1:25 to 1:55 Drift decomposition

Show: the drift panel on a page and the drift chart on `analysis.html`.
Say: "To separate language from knowledge, Super VL tags each historical claim with quotes from both sides: enduring, renamed, superseded, or dropped. We reject any quote that is not in the source. Across our pairs about half the claims still hold, and about a third are gone from Wikipedia."

## 1:55 to 2:35 Hermes agent: one success

Show: Hermes terminal, lightning question (`runs/agent/20261018-140114-...`). Show the tool calls, the `view_scan` image read, and the cited answer.
Say: "The Hermes agent runs on Super VL with our four tools. It searches LanceDB, reads the pair and the drift, and looks at the original scan to check the OCR. Every claim cites a Britannica entry and a Wikipedia revision, and it reports when a match is uncertain."

## 2:35 to 2:55 Failures

Show: failure-1 then success-3 (old terms), then failure-3 (page 452).
Say: "Three failures taught us the most. A corpus-wide question failed after 35 tool calls, but the agent invented nothing. We added a find_drift tool, and the same question worked with 86 percent fewer tokens. Page 452 is a blank cover: Parse invented text, and the error passed through every stage. The case files explain each one."

## 2:55 to 3:00 Close

Show: README model table.
Say: "Parse, Embed VL, Rerank VL, and Super VL, each with a job. Code, archive, and all six cases are in the repo."
