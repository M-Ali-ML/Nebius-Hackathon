# Worker: design

Branch `M-Ali-ML/mvp-design`. Scope: the visual design of the static site (`src/nemotron_challenge/site_templates/*`) and presentation parts of `site.py`.

## What changed

- One token sheet in `style.css` (`:root`): colors, radii, the 4/8/12/16/24 spacing scale, the 11/12/13/14/16/20/28 type scale, fonts.
- Fonts (Google Fonts, with offline fallbacks): Instrument Serif for brand and page titles, Newsreader for Britannica source text, Inter for UI, JetBrains Mono for IDs, scores, rows, and citations.
- Page view is a full-viewport workbench: scan pane (paper surface), PDF pane, 380px inspector (slate surface). Each pane scrolls on its own. A 48px top bar holds the brand, breadcrumbs, prev/next icon buttons, and nav buttons.
- Native checkboxes became pill chips (`aria-pressed`). Links have no browser blue. Scores are a key-value grid (`_macros.html: scores`).
- Status and claim tags are tinted pills (emerald, sky, amber, slate). "uncertain" has a dashed amber border. The drift bar is 6px with muted tints.
- Claim cards: 3px left accent in the claim color; Britannica quote in Newsreader italic on paper; Wikipedia quote in Inter; mono citation pills.
- Index: dense table with sticky header, 40px thumbnails, search field with an icon, filter chips (matched, uncertain, plates, one per uncertainty cause), LaTeX status dot. Rows open the page on click.
- Explore: segmented tabs, chip filters, dense tables. How it works: numbered vertical pipeline with the model ID in a mono pill.
- Focus rings (2px) and `prefers-reduced-motion` are in place.

## Uncertainty cause (lead request)

- `site.py` reads `match/uncertainty.jsonl` (entry causes by `id`) and `uncertainty_cause` / `uncertainty_note` from `match/page_matches.jsonl`. `CAUSE_LABELS` maps codes to pill text.
- The cause shows as a muted pill next to the amber "uncertain" pill, with the note as secondary text, in the inspector (page match and each entry) and in the index table.
- `docs/uncertainty.md` is copied to `site/docs/` and linked from `analysis.html`.

## Checks

- `uv run pytest -q`: 99 passed (one new test for the uncertainty cause on the page and the index).
- Real build: `uv run nemotron-challenge run site --work-dir artifacts`. Link check: 2157 local links, 0 broken.
- Screenshots: `runs/design/before-*.png` and `runs/design/after-*.png` (headless Chrome; the PDF iframe can render black there).

## Not changed

- The analysis plots are PNGs from the compare stage. They keep their own matplotlib colors.
- The bbox class colors (`CLASS_COLORS`) are unchanged so overlays stay visible on the scan.

## Fixed dates

- Replaced every "1842" label in the templates with the collection range 1768-1860 (brand, drift header, table headers, how and analysis leads).
- One "1842" stays on pages/374.html. It is in the Super VL search phrases (model output), so it is not changed.

## Less clutter (progressive disclosure)

- Inspector shows the key fact per section; scores, reasoning, extra claims, terms, model checks, and plate details open on click. "Expand all" opens everything.
- Entries are one compact row (headword, status, article or cause); click to see snippet, scores, reason.
- Block-class chips moved into a "Layers" popover; provenance is collapsed.
- Index: cause notes on hover; cause chips appear only with the Uncertain filter.
- Claim quotes clamp to 4 lines; click to show the full quote.
- Screenshots: runs/design/calm-*.png.

## Hugging Face look

- Fonts: Source Sans 3 (UI, headings, brand) and IBM Plex Mono (IDs, scores, citations), as on huggingface.co. Newsreader stays for Britannica source text only.
- Tailwind gray neutrals, green status pills, 8px radius, white-to-gray gradient buttons, underline nav tabs, sentence-case labels.
- Screenshots: runs/design/hf-*.png.

## HF look, final

- Merged main (2951418). HF cards (12px, gray-50 to white gradient), HF tag pills, yellow/orange accent only on the brand mark and the primary button.
- Real site rebuilt; links 0 broken; pytest passed. Screenshots: runs/design/hf-*.png. Branch head a82935a.
