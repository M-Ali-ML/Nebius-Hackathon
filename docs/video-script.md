# Video script (3:00)

Record each block as a separate clip, then join them. Speed up model waits in the edit (2x to 4x) with a small "sped up" label.
Use the live Space for the browser parts: https://nebius-build-week-britannica-across-time.static.hf.space
Hermes runs in a terminal from the main checkout (see [demo-commands.md](demo-commands.md)).

The spoken lines below follow the saved runs. Do not say a number the page on screen does not support.

## 0:00 to 0:15 Hook (`index.html`)

Show: the intro and the five cards under it. The footnote on screen says 52 of 100 pages matched.
Say: "The Britannica calls lightning 'electric fire' from a charged 'electrical atmosphere'. Wikipedia measures that flash in gigajoules. We read 100 scans from 1768 to 1860 with all four NVIDIA Nemotron models, and separated a change in spelling from a change in knowledge."

## 0:15 to 0:40 Parse 3.5, the LaTeX archive, and the match (`pages/1250.html` -> `pages/1910.html`)

Show: `pages/1250.html`. Toggle the Parse class chips, hover a block, and scroll the compiled PDF (this page is two columns). Then `pages/1910.html`. Open Scores and reasoning: BM25 rank 2, rerank logit -3.75, margin 0.72. The pill says matched. Show the drift bar (2 enduring, 4 superseded, 2 dropped). This page has no uncertainty-cause pill.
Say: "Parse 3.5 reads all 100 scans into ordered blocks, with classes and bounding boxes. Every page compiles to a LaTeX PDF, with columns, headings, and cropped figures. Two pages whose full-page parse failed were split into columns and parsed again. BM25 returns 30 candidates. Embed VL keeps the top 10. Rerank VL scores them. Where the right article is already in that pool, top-1 accuracy goes from 0.30 to 0.56 to 0.70."

## 0:40 to 1:20 Wow Factor 1: The Nemotron Embed VL Atlas (`atlas.html`)

Show: `atlas.html`. Point at the `92.8%` card (n=97, chance 1.0%) and the `88.1%` card. Click Guided Tours 1 (*A page finds its own words*), 2 (*Plate 270 meets Hydrostatics*), 3 (*Natural History and Entomology*), and 4 (*Alone in the space: HUGHILY*). Toggle `Kind | Match | Drift | Topic`, zoom into the thumbnails, and drag the `1797 <-> 2026` slider.
Say: "This is one Embed VL space, 2,048 dimensions: page scans, engravings, OCR text, and Wikipedia. With no labels, 92.8 percent of the 97 scans that have an entry sit nearest that entry. Chance is 1 percent. And 88.1 percent of matched entries sit nearest their Wikipedia article. On Plate 270, the keyword 'Hydrostatics' ranks 'Hydrostatic skeleton' first. The engraving, through Embed VL and Rerank VL, lands on Hydrostatics. Natural History and Entomology is a cluster shared by both eras. HUGHILY is an OCR miss for the town of Hooghly, so that entry sits far from Wikipedia."

## 1:20 to 1:45 Drift decomposition and the Super VL scan check (`explore.html` -> `analysis.html`)

Show: `explore.html` filtered to "superseded", then the Super VL Scan Check card on `analysis.html` (94 items, 79 OCR, 15 confirmed). The `fitteenth` / `sixteenth` note is on that card.
Say: "Across 87 pairs, Super VL tags each extracted claim as enduring, renamed, superseded, or dropped. A quote counts only when it is a verbatim substring of its source. Of 94 drift items checked on the scan, 79, that is 84 percent, were OCR. 'Sixteenth' of a pound, printed with a long s, was read as 'fitteenth'. The other 15 are real historical shifts."

## 1:45 to 2:20 Wow Factor 2: The Time-Travel Debate (`debate.html#lightning`)

Show: `debate.html#lightning` at `2x` to `4x`. Point at the Scholar of 1790 and the tool pills `search_sources`, `get_pair`, and `view_scan`. Expand `Tool trace (3)`. Show a green underline and a red underline. Press `E` for the Judge.
Say: "Three Hermes agents on Nemotron 3.5 Super VL debate one question. The Scholar of 1790 cites only Britannica. The Wikipedian cites only Wikipedia. The Judge rules each point. The Scholar calls view_scan on B:1910:0. The OCR says 'returning firele'. Super VL reads the scan as 'returning stroke'. The Scholar concedes megajoules and keeps that observation. Quotes are checked after the debate. Green means the words are in the cited source. Red means they are not. Some scan readings stay red, because they are not in the OCR."

## 2:20 to 2:50 Hermes terminal: retrieval cost and three failures

Show: the Hermes banner (`nvidia/Nemotron-3.5-Super-VL`, 5 tools). Clip 1 is blank cover `B:452:0` with `view_scan`. Clip 2 is the old-terms question with `find_drift`. If the edit has two seconds, flash `docs/cases/failure-2.md` (plate 651 matched to "Fig (restaurant)"). Plate 2077 is a success of `view_neighbors`, not one of the three failures.
Say: "Hermes has five tools. Hybrid search, LanceDB plus live BM25, used 39 percent fewer tokens than embed-and-rerank search, on seven questions. Three failures stand out. Page 452 is a blank cover. Parse invented text for it, and that text passed match and compare, until a later view_scan saw the blank page. A corpus question stopped after 35 calls and invented nothing. find_drift answered it with 86 percent fewer tokens. Two of the three examples hold. Plate 651 offered only the word 'Fig', so it matched a restaurant."

## 2:50 to 3:00 Close

Show: the Hugging Face Space (`nebius-build-week/britannica-across-time`) and the dataset (`nebius-build-week/britannica-wikipedia-drift`).
Say: "Parse, Embed VL, Rerank VL, and Super VL. Explore the live archive, the 10-config dataset, and the six case studies."

---

## Full spoken script (read straight through)

**0:00** The Britannica calls lightning "electric fire" from a charged "electrical atmosphere". Wikipedia measures that flash in gigajoules. We read 100 scans from 1768 to 1860 with all four NVIDIA Nemotron models, and separated a change in spelling from a change in knowledge.

**0:15** Parse 3.5 reads all 100 scans into ordered blocks, with classes and bounding boxes. Every page compiles to a LaTeX PDF, with columns, headings, and cropped figures. Two pages whose full-page parse failed were split into columns and parsed again. BM25 returns 30 candidates. Embed VL keeps the top 10. Rerank VL scores them. Where the right article is already in that pool, top-1 accuracy goes from 0.30 to 0.56 to 0.70.

**0:40** This is one Embed VL space, 2,048 dimensions: page scans, engravings, OCR text, and Wikipedia. With no labels, 92.8 percent of the 97 scans that have an entry sit nearest that entry. Chance is 1 percent. And 88.1 percent of matched entries sit nearest their Wikipedia article. On Plate 270, the keyword "Hydrostatics" ranks "Hydrostatic skeleton" first. The engraving, through Embed VL and Rerank VL, lands on Hydrostatics. Natural History and Entomology is a cluster shared by both eras. HUGHILY is an OCR miss for the town of Hooghly, so that entry sits far from Wikipedia.

**1:20** Across 87 pairs, Super VL tags each extracted claim as enduring, renamed, superseded, or dropped. A quote counts only when it is a verbatim substring of its source. Of 94 drift items checked on the scan, 79, that is 84 percent, were OCR. "Sixteenth" of a pound, printed with a long s, was read as "fitteenth". The other 15 are real historical shifts.

**1:45** Three Hermes agents on Nemotron 3.5 Super VL debate one question. The Scholar of 1790 cites only Britannica. The Wikipedian cites only Wikipedia. The Judge rules each point. The Scholar calls view_scan on B:1910:0. The OCR says "returning firele". Super VL reads the scan as "returning stroke". The Scholar concedes megajoules and keeps that observation. Quotes are checked after the debate. Green means the words are in the cited source. Red means they are not. Some scan readings stay red, because they are not in the OCR.

**2:20** Hermes has five tools. Hybrid search, LanceDB plus live BM25, used 39 percent fewer tokens than embed-and-rerank search, on seven questions. Three failures stand out. Page 452 is a blank cover. Parse invented text for it, and that text passed match and compare, until a later view_scan saw the blank page. A corpus question stopped after 35 calls and invented nothing. find_drift answered it with 86 percent fewer tokens. Two of the three examples hold. Plate 651 offered only the word "Fig", so it matched a restaurant.

**2:50** Parse, Embed VL, Rerank VL, and Super VL. Explore the live archive, the 10-config dataset, and the six case studies.
