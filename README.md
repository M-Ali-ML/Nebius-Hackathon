# Knowledge Across Time: Britannica meets Wikipedia

We match 100 scanned pages of the Encyclopaedia Britannica (1768 to 1860) to modern Wikipedia articles, then separate a change in spelling from a change in knowledge.

**Winner of the NVIDIA track** at the Nebius Build Week hackathon, for the best use of an NVIDIA Nemotron model.

## Open it on Hugging Face

The archive is a Hugging Face Space. Open it here:

**https://huggingface.co/spaces/nebius-build-week/britannica-across-time**

The dataset of entries, matches, claims, and agent transcripts is [nebius-build-week/britannica-wikipedia-drift](https://huggingface.co/datasets/nebius-build-week/britannica-wikipedia-drift).

The pictures below are the live Space. Each one links to that screen.

### The archive

[![The archive index: 100 scanned pages, match status, and the five Nemotron stages](docs/hf/img/index.png)](https://nebius-build-week-britannica-across-time.static.hf.space/)

### One page: the scan, the LaTeX rebuild, and the Wikipedia match

[![Page 1910: Parse boxes on the lightning scan, the compiled PDF, and the drift claims](docs/hf/img/page.png)](https://nebius-build-week-britannica-across-time.static.hf.space/pages/1910.html)

### Every claim, with a quote from both sides

[![Explore: enduring, renamed, superseded, and dropped claims with Britannica and Wikipedia quotes](docs/hf/img/explore.png)](https://nebius-build-week-britannica-across-time.static.hf.space/explore.html)

### What changed, and why some pages have no match

[![Analysis: coverage counts and the drift bar](docs/hf/img/analysis.png)](https://nebius-build-week-britannica-across-time.static.hf.space/analysis.html)

### The agent debate

Three Hermes agents on Nemotron 3.5 Super VL argue one question. The Scholar of 1790 cites only Britannica. The Wikipedian cites only Wikipedia. The Judge rules each point.

[![Time-travel debate: Lightning, with the Scholar of 1790 opening from the scan](docs/hf/img/debate.png)](https://nebius-build-week-britannica-across-time.static.hf.space/debate.html#lightning/2)

The same Space also has the [atlas](https://nebius-build-week-britannica-across-time.static.hf.space/atlas.html).

## The parts

| Part | Where |
| --- | --- |
| Results | [docs/results.md](docs/results.md) |
| How to run it | [docs/setup.md](docs/setup.md) |
| Atlas | [docs/atlas.md](docs/atlas.md) |
| Agent debate | [docs/debate.md](docs/debate.md) |
| Six case studies | [docs/cases/README.md](docs/cases/README.md) |
| All of the docs | [docs/README.md](docs/README.md) |

Source: https://github.com/M-Ali-ML/Nebius-Hackathon

Code: MIT. Britannica scans: CC0 (National Library of Scotland). Wikipedia text: CC BY-SA 4.0. [ATTRIBUTION.md](ATTRIBUTION.md).
