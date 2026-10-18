# Multimodal atlas

Page: `site/atlas.html`. Code: `src/nemotron_challenge/atlas.py`. Template: `site_templates/atlas.html`.

## What it shows

One map of one Nemotron Embed VL space (`nvidia/llama-nemotron-embed-vl-1b-v2`, revision `582e3bf`, 2048-d).
Four kinds of points sit together:

| Kind | Count | Input sent to Embed VL |
|---|---|---|
| `scan_image` | 100 | the scan JPEG only (no OCR text) |
| `plate_crop` | 17 | the crop of each Parse `Picture` block of at least 48 x 48 px |
| `britannica_entry` | 259 | `text_norm` of each entry (cached in `match/vectors/entries.jsonl`) |
| `wikipedia_chunk` | 1058 | about 1,500-char chunks of matched articles (cached in `match/vectors/wiki_chunks.jsonl`, plus 4 chunks of the plate 270 article) |

Every vector uses `input_type=document`.
So every distance on the map compares a document with a document.
The service does not accept an image as a query, and we do not mix query and document vectors.

## Numbers (full 2048-d cosine, not the 2D map)

From `artifacts/atlas/summary.json`:

- Image to text: 92.8% of scan images (90 of 97 pages that have entries) have one of their own page entries as nearest Britannica entry, out of 259. Chance is 1.0%. Median rank of the own entry is 1.
- Image to any text: 91.8% of scan images have their own entry as nearest point among all entries and Wikipedia chunks.
- Entry to article: 88.1% of matched entries (59 of 67) have a chunk of their matched article as nearest Wikipedia chunk.
- Plate 270 (HYDROSTATICS, Plate CCXXXIX), embedded as a picture crop: its nearest Wikipedia chunk of 1058 belongs to the Hydrostatics article `[W:527232:1334920169]`.

Inference: the scan images of text pages carry printed words, and Embed VL reads them.
So image-to-text agreement measures how well the model reads 18th-century print, not how well it matches pictures.
The 17 plate crops form their own small island on the map. That is the picture-only region.

## Map

- UMAP to 2D, cosine metric, `n_neighbors=15`, `min_dist=0.12`, seed `20261018`. 2D distances are approximate.
- Edges: entry to the nearest chunk of its matched article (`match/matches.jsonl`), scan image to its own entries, plate crop to its plate match (`plates/<row>.json`).
- Color options: kind, match status, dominant drift tag (from `compare/pairs/*.json`), topic cluster (read-only from `compare/topics.json`).
- Tours are chosen by code in `atlas.tours()`. Every number in a caption is computed there.
  1. A text scan whose nearest entry is its own entry (tightest group on the map).
  2. The only matched plate (270) and its Wikipedia article.
  3. The most compact topic cluster with at least 5 Britannica entries and 5 Wikipedia chunks.
  4. An unmatched headword entry far from all Wikipedia points, with the lowest best cosine.

## Page features

Pan, zoom, hover card, click to pin, click again to open the page view or the Wikipedia revision.
Search box with fly-to. Kind toggles. Time slider (1797 to 2026) fades Britannica or Wikipedia points.
Night (starfield) and paper themes. Mini-map. Keyboard shortcuts (`?`). Shareable state in the URL hash.
No external scripts: icons are inline SVG and data and thumbnails are inline, so the page works offline and from `file://`.
Animations stop when the browser asks for reduced motion.

## Rebuild

```
uv run python scripts/build_atlas.py --work-dir artifacts            # embeds missing images, then projects and builds
uv run python scripts/build_atlas.py --work-dir artifacts --offline  # cached vectors only, no service calls
```

Image embedding is resumable (`atlas/image_vectors.jsonl`). Failed calls go to `atlas/failures.jsonl` (0 in the saved run).
Files: `atlas/vectors.npz`, `atlas/ids.json` (ids, kinds, model, revision, dims, time), `atlas/points.json`, `atlas/summary.json`, `atlas/thumbs/`.

## Limits

- The first image run took 43 s for 117 images, one request at a time.
- Plate article chunks use the first 20,000 characters of the article.
- 3 of the 100 pages have no entries (picture-only plates), so the image-to-text share uses 97 pages.
- No image+text combined documents yet.
