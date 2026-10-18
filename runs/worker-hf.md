# Worker hf: Hugging Face publish

## Status 15:20: DONE (both repos public in the org, verified)

| Repo | URL | Size | Hub commit |
| --- | --- | --- | --- |
| Space (static) | https://huggingface.co/spaces/nebius-build-week/britannica-across-time | 29.2 MB, 583 files | 742f34e4 |
| App URL | https://nebius-build-week-britannica-across-time.static.hf.space | | |
| Dataset | https://huggingface.co/datasets/nebius-build-week/britannica-wikipedia-drift | 21.8 MB, 12 files | ae9908b0 |

Both repos are owned by `nebius-build-week` and public. Token account: MightyStudent (fine-grained, write on the org).

## What was uploaded

Space: a copy of `site/` from the main checkout, plus `img_card/` (4 headless Chrome screenshots: index, page 1910, explore, analysis) and `README.md` (card from `docs/hf/space_card.md`).

Dataset: 10 JSONL configs, declared in the card YAML, each with one `train` split.

| Config | Rows |
| --- | --- |
| entries | 262 |
| matches | 362 (262 entry level + 100 page level, with uncertainty cause) |
| candidates | 8,135 (every scored Wikipedia candidate, 1,000-char excerpts) |
| comparisons | 83 |
| claims | 500 (476 quote check passed, 24 failed) |
| term_pairs | 254 (112 flagged likely_ocr) |
| retrieval_labels | 40 (one reader, our judgment; top-1 and correct per method) |
| ablation_results | 8 (4 match retrieval methods, 4 agent search modes) |
| agent_trajectories | 47 (14 top-level runs, 33 ablation runs; 8 runs carry a case id, 6 primary) |
| parse_pages | 100 |

Not uploaded: full Wikipedia articles (`artifacts/match/articles/`), raw Parse replies, scans in the dataset, LanceDB vectors.
Image data is removed from transcripts. Local checkout paths are rewritten to repo-relative paths.

## Verification (15:15)

- Space runtime: RUNNING. GET `/`, `index.html`, `explore.html`, `pages/13.html`, `img_card/index.png`: all 200.
- Served the upload folder with `python -m http.server`: all relative links tested return 200.
- datasets-server `/is-valid`: viewer true. `/splits` lists all 10 configs. `/first-rows` returns rows for all 10.
- `load_dataset("nebius-build-week/britannica-wikipedia-drift", <config>)` loads all 10 configs.

## Republish (after the design freeze)

From the main checkout, after merging `M-Ali-ML/mvp-hf`:

```sh
uv run python scripts/publish_hf.py screenshots   # optional: refresh docs/hf/img/*.png (needs Chrome)
uv run python scripts/publish_hf.py publish       # build, upload Space + dataset, verify
```

From a worktree, add `--root /Users/aly/repos/Nebius-Hackathon` so the script reads the current `site/`, `artifacts/`, and `runs/`.
The script is idempotent: `create_repo(exist_ok=True)`, then `upload_folder` with `delete_patterns="*"` (removes stale files on the Hub).
Card numbers (P@1, drift shares, match counts, row counts) are computed from the artifacts at build time.

## Notes for the lead

- The site header says "Britannica 1842". The README says 1771 to 1797. One of them is wrong; the cards avoid a year and say "18th-century".
- The drift numbers in the cards come from `artifacts/compare/drift_summary.json` (83 pairs, 476 claims): enduring 44%, renamed 5%, superseded 13%, dropped 38%. `docs/cases/README.md` still says 67 matched pairs.

## Failed attempts

- First `publish` run: uploads succeeded, then `/is-valid` returned HTTP 500 while the viewer processed the new dataset. Fixed: verify now retries on errors.

## 15:30: LaTeX PDF blocked in the Space (fixed)

Symptom: on huggingface.co the LaTeX panel showed "This page has been blocked by Chrome".
Cause: Hugging Face shows a static Space inside an iframe with a `sandbox` attribute. Chrome does not run its PDF viewer in a sandboxed frame, and our PDF iframe inherits the sandbox. A GET of the PDF has no blocking header.
Fix (Space build only, `site/` unchanged): `publish_hf.py` adds `pdfview.html` (PDF.js 3.11.174 from cdnjs) and points each `iframe.pdf` at it. "Open PDF" links now open in a new tab, which leaves the sandbox. Tested in a local iframe with the same sandbox flags, then republished with the current site and new screenshots.
