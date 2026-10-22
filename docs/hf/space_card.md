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

**Winner of the NVIDIA track** at the Nebius Build Week hackathon, for the best use of an NVIDIA Nemotron model.

**What did people know in the 1700s, and what do we know now?**
We read 100 scanned pages of the 18th-century Encyclopaedia Britannica with NVIDIA Nemotron models, matched each entry to its modern Wikipedia article, and split every difference into four kinds of drift: the spelling changed, the name changed, the knowledge changed, or the topic was dropped.
Every claim on this site has a quote from both sources, and every quote was checked against the source text.

**[Open the archive](${app_url})** · [Dataset](${dataset_url}) · [Code on GitHub](${github})

![The archive index: 100 scanned pages with match status and uncertainty causes](https://huggingface.co/spaces/${space_id}/resolve/main/img_card/index.png)

![A page view: the scan with Parse 3.5 boxes, the compiled LaTeX PDF, and the Wikipedia match with drift claims](https://huggingface.co/spaces/${space_id}/resolve/main/img_card/page.png)

![Explore changes: every claim with a quote from each side](https://huggingface.co/spaces/${space_id}/resolve/main/img_card/explore.png)

![Analysis: coverage and the share of enduring, renamed, superseded, and dropped claims](https://huggingface.co/spaces/${space_id}/resolve/main/img_card/analysis.png)

![Agent debate: three Hermes agents on Nemotron 3.5 Super VL argue what lightning is. The Scholar of 1790 cites only Britannica. The Wikipedian cites only Wikipedia.](https://huggingface.co/spaces/${space_id}/resolve/main/img_card/debate.png)

Results, setup, the atlas, the debate, and the six case studies are in the [docs](${github}/blob/main/docs/README.md).

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
