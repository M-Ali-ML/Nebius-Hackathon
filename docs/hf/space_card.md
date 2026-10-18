---
title: Britannica Across Time
emoji: 📜
colorFrom: yellow
colorTo: indigo
sdk: static
app_file: index.html
pinned: false
license: mit
short_description: 18th-century Britannica scans vs modern Wikipedia
tags:
  - nemotron
  - ocr
  - document-parsing
  - entity-linking
  - reranking
  - agents
  - digital-humanities
  - wikipedia
  - historical-text
---

# Britannica Across Time

**What did people know in the 1700s, and what do we know now?**
We read 100 scanned pages of the 18th-century Encyclopaedia Britannica with NVIDIA Nemotron models, matched each entry to its modern Wikipedia article, and split every difference into four kinds of drift: the spelling changed, the name changed, the knowledge changed, or the topic was dropped.
Every claim on this site has a quote from both sources, and every quote was checked against the source text.

[Open the archive](${app_url}) · [Dataset](${dataset_url}) · [Code on GitHub](${github})

![The archive index: 100 scanned pages with match status and uncertainty causes](https://huggingface.co/spaces/${space_id}/resolve/main/img_card/index.png)

![A page view: the scan with Parse 3.5 boxes, the compiled LaTeX PDF, and the Wikipedia match with drift claims](https://huggingface.co/spaces/${space_id}/resolve/main/img_card/page.png)

![Explore changes: every claim with a quote from each side](https://huggingface.co/spaces/${space_id}/resolve/main/img_card/explore.png)

## What you can do in the demo

- **Read a scan with its layout.** Each page shows the scan with Parse 3.5 boxes (text, headers, pictures). Turn box layers on and off, and read the Parse text block by block in reading order.
- **Compare the scan with a clean LaTeX rebuild.** All 100 pages were compiled to PDF from the Parse blocks, 89 of them in two columns.
- **See the modern counterpart.** Each entry links to the matched Wikipedia article and revision, with the BM25 rank, embed cosine, rerank logit, and margin that decided the match.
- **See why a match failed.** Pages with no clear counterpart get a cause: no usable text, OCR failure, obsolete subject, candidate pool miss, or threshold miss.
- **Read the drift.** For each matched pair, claims are tagged enduring, renamed, superseded, or dropped, each with a Britannica quote and a Wikipedia quote.
- **Explore changes across the corpus.** The Explore page lists every claim and every old -> new term pair, with search and filters by type. Click `[B:..]` to see the scan and `[W:..]` to open the exact Wikipedia revision.
- **Read the analysis.** Coverage, causes of unmatched pages, drift shares, word frequencies, and visual matching of engraving plates.

## Headline numbers

| Stage | Result |
| --- | --- |
| Parse 3.5 | 100 of 100 scans parsed, 262 entries, 723 long-s and ligature repairs |
| LaTeX | 100 of 100 PDFs compiled |
| Matching | ${pages_matched} of 100 pages and ${entries_matched} of 262 entries matched; the rest carry a stated cause |
| Retrieval (P@1, 40 hand labels, gold in pool) | BM25 ${p1_bm25} -> + Embed VL ${p1_embed} -> + Rerank VL ${p1_rerank} |
| Drift (${claims_checked} quote-checked claims, ${pairs} pairs) | enduring ${enduring}, renamed ${renamed}, superseded ${superseded}, dropped ${dropped} |
| Agent | Hermes with 4 team tools; 3 success and 3 failure cases kept with full transcripts |

The retrieval labels are our own judgment, from one reader. OCR noise inflates the renamed and superseded shares. The quote check proves that a quote exists in its source, not that it supports the claim.

## Nemotron models used

| Model | What it does |
| --- | --- |
| `nvidia/nemotron-3.5-parse` | Reads each scan into ordered blocks with class and bbox. Feeds entries, the LaTeX rebuild, and the boxes on the site. |
| `nvidia/llama-nemotron-embed-vl-1b-v2` | Re-scores BM25 candidates per entry. Embeds engraving plates as images. Builds the LanceDB vectors the agent searches. |
| `nvidia/llama-nemotron-rerank-vl-1b-v2` | Re-ranks the top 10. Its logit and margin decide match or no clear counterpart. Scores plate images against articles. |
| `nvidia/Nemotron-3.5-Super-VL` | Writes the quote-checked comparisons, describes plates, expands queries from the page image, and runs the agent. |
| Hermes Agent + Super VL | Answers comparison questions with tools `search_sources`, `get_pair`, `find_drift`, `view_scan`, and cites `[B:row:n]` and `[W:page_id:revision_id]`. |

## Data and code

- **Dataset:** [${dataset_id}](${dataset_url}) has every entry, match, candidate score, claim, term pair, hand label, and agent transcript behind this site.
- **Code:** [${github}](${github}) has the full pipeline (`extract`, `match`, `compare`, `site`, `agent`).

## Licenses

- Site code: MIT.
- Britannica scans: CC0, from the National Library of Scotland ([NationalLibraryOfScotland/encyclopaedia_britannica_illustrated](https://huggingface.co/datasets/NationalLibraryOfScotland/encyclopaedia_britannica_illustrated), revision `309f765b`).
- Wikipedia text: CC BY-SA 4.0. Every quote links to its article and revision id.

Built for Nebius Build Week.
