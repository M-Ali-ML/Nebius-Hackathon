# Video script (3:00)

Record each block as a separate clip, then join them. Speed up model waits in the edit (2x to 4x) and say so with a small "sped up" label.
Use the live Space for the browser parts: https://nebius-build-week-britannica-across-time.static.hf.space
Hermes runs in a terminal from the main checkout (see [demo-commands.md](demo-commands.md)).

## 0:00 to 0:15 Hook (home page)

Show: the home page intro and the five "What you will see" cards. Slow scroll.
Say: "The 18th-century Britannica calls lightning 'electric fire' from a charged 'electrical atmosphere'. Wikipedia measures it in gigajoules. We read 100 Britannica pages with NVIDIA Nemotron and measured what changed: the spelling, the words, the facts, or the coverage."

## 0:15 to 0:35 Parse 3.5 and the LaTeX archive (card 01, page 1250)

Show: page 1250. Toggle the Parse class chips on the scan, hover a block, scroll the compiled PDF next to it.
Say: "Parse 3.5 reads every scan into ordered blocks with classes and boxes. Each page becomes a LaTeX document with its columns and headings. Two dense pages looped past the token limit, so we parse each column. We show OCR errors, we do not hide them."

## 0:35 to 1:00 Matching with Embed VL and Rerank VL (card 02)

Show: page 1910 inspector (match, scores grid, uncertain pill), then the ablation chart in `analysis.html`.
Say: "Keyword search gives 30 Wikipedia candidates, Embed VL keeps 10, Rerank VL decides. On 40 entries we labeled, top-1 accuracy goes from 0.30 to 0.56 to 0.70. When nothing is good enough, the page says uncertain and gives the cause."

## 1:00 to 1:30 The Atlas (card 03)

Show: `atlas.html`. Click tour 1, then tour 2 (plate 270). Zoom in so scan thumbnails grow. Hover a Wikipedia point.
Say: "This is one Embed VL space. 1790s engravings, OCR text and modern Wikipedia sit on the same map. For 92.8 percent of scans, the nearest text is the page's own entry; chance is 1 percent. Plate 270 has no usable text, and its picture lands next to the Hydrostatics article by itself."

## 1:30 to 1:55 What changed (card 05, Explore)

Show: the drift panel on a page, then `explore.html` filtered to "superseded", then the scan check card on `analysis.html`.
Say: "Super VL tags each historical claim with quotes from both sides: enduring, renamed, superseded, or dropped. Across 87 pairs, 43 percent still hold and 39 percent are gone from Wikipedia. Long-s OCR creates fake changes, like 'fitteenth' for 'sixteenth', so Super VL checks the scan crop and filters them out."

## 1:55 to 2:20 Hermes agent live (terminal)

Show: Hermes banner (Super VL, 5 tools), Question 1 (lightning): tool calls, `view_scan`, the cited answer. Speed up the waits.
Say: "The Hermes agent runs on Super VL with five tools of ours. It searches both sources, reads the saved comparison, and looks at the original scan to fix the OCR. Every claim cites a Britannica entry and a Wikipedia revision."

## 2:20 to 2:40 The Time-Travel Debate (card 04)

Show: `debate.html`, lightning tab at 1.5x, then press `E` to jump to the verdict stamp and confetti. Hover one citation pill.
Say: "Three Hermes agents on Super VL: a scholar of 1790 who may cite only the Britannica, a Wikipedian, and a judge who rules whether the language or the knowledge changed. Quotes we cannot verify are marked, not hidden."

## 2:40 to 2:55 Failures and repairs

Show: Question 2 (plate 2077 with `view_neighbors`), then `docs/cases/failure-1.md` next to `success-3.md`.
Say: "Plate 2077 is a blank leaf; view_neighbors shows Super VL the next scan, the real microscope plate. A corpus-wide question once failed after 35 tool calls without inventing anything. Our find_drift tool fixed it with 86 percent fewer tokens."

## 2:55 to 3:00 Close

Show: the home page "Built with" row and the Hugging Face Space header.
Say: "Parse, Embed VL, Rerank VL and Super VL, each with a job. Try it on Hugging Face."
