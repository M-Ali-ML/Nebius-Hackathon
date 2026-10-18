# Worker "site": LaTeX documents and static website

Branch: `M-Ali-ML/mvp-site` (3 commits, not pushed). Stage: `tasks.site`.

## What it builds

- `src/nemotron_challenge/latex.py`: one `.tex` per page record in `artifacts/latex/<row>.tex`, compiled with tectonic to `<row>.pdf`.
  - Parse reading order is kept. Page-header and short top-margin blocks (page number, guide words) go into the running head. Page-footer goes into the running foot.
  - Title -> `\section*` (always full width). Section-header -> `\subsection*`. Text -> paragraph with hyphenated line breaks joined. List-item -> `itemize`. Footnote -> small text at page end. Table -> our own `tabular` rebuilt from the Parse cells (Parse tabular commands dropped). Formula -> monospace. Picture -> `\includegraphics` of the bbox crop (`latex/img/<row>-<order>.jpg`), plus the Parse "text inside picture" in small gray. Captions that Parse reads before their picture move after it.
  - Two columns with `multicol` when body blocks sit on both halves. Wide blocks (>= 0.6 page width) and titles break out of the columns.
  - Markdown emphasis from Parse (`**x**`, `__x__`, `*x*`) becomes bold or italic. LaTeX specials are escaped. `ſ` -> `s`. Characters outside Latin, Greek, Cyrillic, and common punctuation show as a red `[U+XXXX]` marker, so they are visible and not lost.
  - Footer on every document: page_id, row index, image sha256, Parse model, finish reason, link to the scan.
  - `latex/build.jsonl`: one line per page per run: status ok/failed, seconds, two_column, pictures, unknown_chars, error tail.
- `src/nemotron_challenge/site.py` + `site_templates/`: static site in `/Users/aly/repos/Nebius-Hackathon/site/`.
  - `index.html`: all 100 pages: thumbnail, row, running head, blocks, entries, matched, uncertain, LaTeX status + PDF link. Filter box.
  - `pages/<row>.html`: 3 panes. Source (beige): scan with SVG overlay of Parse bboxes colored by class, class toggles, hover shows order and class, click jumps to that block's Parse text. Middle: compiled PDF + link to `.tex`. Generated (blue): entries from `extract/entries.jsonl` joined to `match/matches.jsonl`: headword, Parse snippet, Wikipedia title link + revision, rerank logit, margin, cosine, BM25 rank, method. `no_clear_counterpart` shows a yellow "uncertain" badge and a dashed border. Hover an entry to highlight its blocks on the scan. Missing inputs show a note.
  - `analysis.html`: shows `compare/*.png` and any `compare/wordfreq.json` shape as tables, and the count of `compare/pairs/*.json`.
  - Scans, thumbnails, PDFs, and .tex are copied into `site/`, so it works from `file://` and via `python -m http.server`.

## Rerun

```
uv run nemotron-challenge run site --work-dir /Users/aly/repos/Nebius-Hackathon/artifacts
cd /Users/aly/repos/Nebius-Hackathon/site && python -m http.server 8080   # or open site/index.html
```
About 40 s for all 100 pages (4 tectonic builds in parallel). Rerun after the match and compare stages write their files; the site picks them up.

## Numbers (last run)

- LaTeX: 100/100 ok, 0 failed, 89 two-column documents. 26 Picture blocks cropped (10 picture-only plate pages included, e.g. rows 1400, 651, 270).
- Site: 100 pages, 1507 local links checked, 0 broken. Entries 262 (from match worker), matches 0 at build time (matches.jsonl not yet written).
- Unknown characters (shown as red markers) on 11 pages: CJK and Ethiopic characters that Parse hallucinated, plus `ɓ` (rows 115, 251, 257, 318, 513, 611, 1904, 1942, 2093, 2131, 2277).
- Tests: `uv run pytest -q` 66 passed (tests/test_latex.py, tests/test_site.py; removed "site" from the unfinished-stage test).

## Manual PDF check (compared with scans)

- Row 13 (SHIP-BUILDING): two columns and paragraph order match the scan. The margin note "Practical Building" becomes a section header ("Fractical Building", Parse OCR). Numbered paragraphs "1st", "2dly" are Parse List-items, so they show as bullets.
- Row 1032 (HEAT): table rebuilt with 11 columns, readable. One Parse text block contains leaked Parse markup (`<x_0.1734><class_Text>...`); we keep it as source text. Footnote blocks go to the page end.
- Row 1400 (Midwifery plate): full-page crop, the Parse text inside the picture is listed under it.
- Row 1939 (PHARMACY): headings `535: Efential oil of ...` are bold section headers; long-s errors (`f` for `s`) come from Parse and are not corrected.
- Row 651 (Helminthology plate): figures cropped one by one, captions follow their picture.

## Known problems

- OCR quality is Parse output without correction; some pages (e.g. row 104) are heavy with OCR errors. We do not hide or fix them.
- Reading order is Parse order. When Parse puts a right-column block before a left-column one, the PDF follows Parse.
- Running head heuristic: a block in the top 7% with <= 12 chars joins the head. A short real heading there could move to the head.
- The PDF iframe needs a browser PDF viewer (headless Chrome shows it black).

# Plates (visual matching for picture-only engraving plates)

Modules: `src/nemotron_challenge/neighbors.py`, `src/nemotron_challenge/plates.py`. CLI: `nemotron-challenge plates`. Site: `site_templates/plate.html`.

## Rerun

```
uv run nemotron-challenge plates --work-dir /Users/aly/repos/Nebius-Hackathon/artifacts --cache-dir /Users/aly/repos/Nebius-Hackathon/data/cache
uv run nemotron-challenge run site --work-dir /Users/aly/repos/Nebius-Hackathon/artifacts
```
About 65 s for 10 plates. Neighbor Parse replies are cached; Super VL, BM25, embed and rerank run again on each call.

## Book order finding (neighbors)

- The source Parquet has 2,573 rows in 195 volumes (column `id`). Rows of one volume are contiguous, about 13 rows per volume. The `label` column is 1 for illustrated pages.
- Rows are NOT consecutive printed pages and are NOT always in book order inside a volume. Evidence from Parse running heads of neighbors:
  - Plate 270 (Hydrostatics, Vol. id 149982181): rows 268 `LAU [602]`, 269 `JES [124]`, 271 `ING [27]`, 272 `INS [252]`. Page numbers jump and go back.
  - Plate 1400 (Midwifery): rows 1398 `MUSIC p.537`, 1399 `MONEY`, 1401 `MOR`, 1402 `NAN [599]`. Same volume (Vol. 14, MIC-NIC), sparse sample.
  - Plate 2243: neighbors `BOTANY`, `BAR (525)`, `PREFACE vi`, `ANATOMY 226`: mixed.
- So a neighbor rarely holds the text that explains the plate. It helped in 2 of 10 cases: plate 651 (row 649 is `HELMINTHOLOGY. Chap. II.`) and plate 2077 (row 2078 is `MICROSCOPE. Plate CCC.`).
- 33 neighbor scans saved to `plates/neighbors/<row>/<neighbor_row>.jpg`, all 33 parsed with Parse 3.5 (raw replies in `plates/neighbors/<row>/raw/`), 0 failures.

## Method per plate

a) Super VL (`nvidia/Nemotron-3.5-Super-VL`, thinking off, max 900 tokens): plate image (downscaled to 1280 px, JPEG) + plate caption text + neighbor text (1500 chars each). Returns description, subject, 3 to 5 keyword queries, `is_blank`, and quotes from neighbor text. Each quote is checked as a substring of the neighbor Parse text (`verified`).
b) BM25: each query and the description itself (top 30 each), merged by best rank, top 30 kept. We added the description as a query because BM25 does not return broad articles like "Astronomy" or "Midwifery" for a one-word query (short titles such as "Journal of Helminthology" rank first).
c) Embed VL: plate image embedded as a document and each candidate (title + excerpt) embedded as a document. Ranking by document-to-document cosine. Choice: the service accepts images only as documents, so image-to-text query similarity is not available; doc-doc cosine is the closest comparison.
d) Rerank VL with image documents: for the top 10 by cosine, query = candidate title + first 300 excerpt chars, documents = [plate image + caption text] and [plate image only]. Logits are compared across the 10 candidates.
e) Decision: `matched` when Rerank VL top 1 equals Embed VL top 1, or the logit is above tau = 0. `no_clear_counterpart` when Super VL reports a blank page or the two vision rankers disagree. All logits were between -5.5 and -1.3, so the logit alone did not separate good and bad picks.
Output: `plates/<row>.json` (every stage score, top 1 per stage, Super VL raw reply and usage, neighbor provenance), `plates/runs.jsonl` (one line per run).

## Numbers (10 plates: rows 270, 374, 651, 948, 1400, 1615, 1845, 2077, 2209, 2243)

- Super VL: 10/10 usable JSON replies, 22,535 tokens total. Descriptions name the plate subject correctly for 7 of 7 non-blank plates (by eye: Hydrostatics, Helminthology, birds and insects, Midwifery, Colombia map, Astronomy x2).
- Blank or near blank pages: Super VL flags 3 (374 blank, 1615 faint sketch, 2077 blank). Parse had labeled them as Picture.
- Matched: 1 (270 Hydrostatics). No clear counterpart: 9. Errors: 0.
- Top 1 by stage that a reader would accept (my judgment, inference): Embed VL 4 (Hydrostatics, Helminthology, Geocentrism for 2243, Celestial globe for 2209 is partial), Rerank VL 3 (Hydrostatics, Midwife, Journal of Helminthology is near), BM25 top 1 is the weakest.

## Examples

- Good, row 270 (HYDROSTATICS. Plate CCXXXIX): Super VL describes "a large water wheel system (Fig. 1), siphons, barometers". BM25 top 1 is "Hydrostatic skeleton" (wrong). Embed VL top 1 "Hydrostatics" (cos 0.329), Rerank VL image+caption top 1 "Hydrostatics" (logit -1.66, margin 0.66 over "History of fluid mechanics"), image-only rerank agrees. Status matched, revision 1334920169.
- Bad, row 1400 (MIDWIFERY PLATE CCCXLVII): Super VL description is right (fetal positions in the uterus, a heart in Fig. 1). BM25 returns "Oyo State College of Nursing and Midwifery" first; the "Midwifery" article is not in the pool. Embed VL picks "Amyoplasia", Rerank VL picks "Midwife" (logit -2.85, margin 0.30). Disagreement, so no_clear_counterpart. Cause: candidate generation (BM25 favors short titles), not the image understanding.
- Bad, row 2077: Parse labels the page as a Picture, Super VL says it is blank. The neighbor row 2078 is the real MICROSCOPE plate. Super VL quoted "MICROSCOPE. / Plate CCC." from it, but the quote check failed (the "/" join is ours), so the evidence shows as not found.

## Known problems

- Rerank logits for (article text query, plate image document) are all negative and close together; they rank but do not calibrate.
- Super VL is called again on each rerun (output can change). Earlier runs are in `plates/runs.jsonl`.

# Demo polish (site)

Commit `3174738`. Rerun: `uv run nemotron-challenge run site --work-dir /Users/aly/repos/Nebius-Hackathon/artifacts` (about 40 s). The site reads whatever the other stages saved at build time, so rerun it after new compare or match runs.

- Index: new "Page match" column from `match/page_matches.jsonl` (matched title + link, or "uncertain" with the reason on hover); KPI "pages matched"; plate status badge.
- Page view, generated pane, top to bottom:
  - Page match: status, Wikipedia title + `[W:page_id:revision]`, rerank logit, margin, BM25 rank, method, and the match worker's "why" text. List-type page topics (dictionary pages) are hidden.
  - Plate: visual match (plate pages only).
  - Drift: a stacked bar of claim tags (enduring / renamed / superseded / dropped) over all compared pairs on the page; 3 example claims (different tags first) with the Britannica and Wikipedia quotes and their `[B:..]` / `[W:..]` ids; old to new term pairs; each pair's quotes kept / rejected. Marked "generated by Super VL", and it says that the quotes were checked as substrings.
  - Entry matches as before.
- `analysis.html`:
  - Coverage numbers (from `extract/coverage.json`, `match/summary.json`, `match/summary_pages.json`).
  - Grouped reasons for no_clear_counterpart, for entries and for pages.
  - Drift summary bar + legend + term pair table (from `compare/drift_summary.json`).
  - `compare/*.png` (drift.png, wordfreq_top.png, wordfreq_distinctive.png).
  - Distinctive word bars (log-odds z) and top word tables (from `compare/wordfreq.json`).
  - Plate results table.
  - The drift colors match drift.png.
- `how.html`: the pipeline from Parse 3.5 to Hermes, with each Nemotron model ID and its job, plus our evidence rules.
- Links: 1,825 local links checked, 0 broken. Tests: 90 passed.

Numbers on the site at build time:
- Pages: 100 parsed, 100 LaTeX documents, 45 of 100 pages matched.
- Entries: 262, of which 67 matched and 195 have no clear counterpart.
- Compare: 83 pairs with claims, 476 claims checked. Tags: 44% enduring, 5% renamed, 13% superseded, 38% dropped.
- Entry reasons: 178 rerank logit below the rules, 14 too short to judge, 3 with no searchable text.
- Page reasons: 46 low logit, 6 plates where the vision rankers disagree, 3 blank plates.

Known problems: the compare worker was still writing pairs during the build (77, then 83), so the numbers move between builds. Some drift labels in drift.png show raw headword lists (for example `['WILLIN', 'WILLLAMSBURG', ...]`). That comes from the compare output, not the site.
