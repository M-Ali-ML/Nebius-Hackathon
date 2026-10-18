# Worker atlas: multimodal atlas

Branch `M-Ali-ML/mvp-atlas`, head `96c7cda`. Not pushed or merged.

## What

`site/atlas.html`: an interactive map of one Nemotron Embed VL space.
100 scan images, 17 plate crops, 259 Britannica entries and 1058 Wikipedia chunks sit on one map.
Every point is an `input_type=document` vector from `nvidia/llama-nemotron-embed-vl-1b-v2` (revision `582e3bf`).
New: the 117 images were embedded as image documents (0 failures, 43 s). Text vectors are reused from `match/vectors/`.

Page features: scan thumbnails as sprites that grow with zoom, night starfield and paper themes, pan and zoom,
hover card with thumbnail, citation, scores and drift bar, click to pin and click again to open the page view or the Wikipedia revision,
search with fly-to, kind toggles, color by kind, match, drift or topic cluster, pulsing matched edges,
a 1797 to 2026 time slider, mini-map, keyboard shortcuts (`?`), shareable URL hash, 4 guided tours with a caption card.
No external scripts. Data and thumbnails are inline (1.0 MB). Works from file:// and under `python -m http.server` (both checked).

## Numbers (full 2048-d cosine)

- Scan image to its own entry: 92.8% (90 of 97), chance 1.0%, median rank 1.
- Matched entry to its matched article: 88.1% (59 of 67).
- Plate 270 crop: nearest Wikipedia chunk of 1058 is Hydrostatics `[W:527232:1334920169]`.

## Rebuild

```
uv run python scripts/build_atlas.py --work-dir artifacts --offline   # no service calls
uv run python scripts/build_atlas.py --work-dir artifacts             # embeds missing images first
```

Files: `artifacts/atlas/` (vectors.npz, ids.json, points.json, summary.json, image_vectors.jsonl, failures.jsonl, thumbs/, articles/).
Doc: `docs/atlas.md`. Tests: `tests/test_atlas.py` (`uv run pytest -q`: 107 passed).
Nav: one line in `site_templates/base.html` adds "Atlas". The main site build does not yet render atlas.html; run the script above after `run site`.

## Screenshots

- `runs/atlas/atlas-overview.png`: overview, night theme.
- `runs/atlas/atlas-tour-plate.png`: tour 2, plate 270 and the Hydrostatics article.
- `runs/atlas/atlas-http-tour3.png`: tour 3 under http.server. `runs/atlas/iterations/`: earlier versions.

## Known limits

- Headless Chrome stalls requestAnimationFrame here. The page has a timer fallback, so screenshots show the final state.
- UMAP reruns on each build. The seed is fixed, but adding vectors moves points, so tours are chosen again by code.
- Image-to-text agreement mostly measures how well the model reads printed words in the scan, not picture matching. The 17 plate crops form their own island.
- Topic clusters are read from `compare/topics.json` at build time. If the other agent changes them, rebuild.
- No 3D view and no image+text combined documents.
