---
title: Britannica Agent (live)
emoji: 📜
colorFrom: yellow
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: cc-by-sa-4.0
short_description: Live Hermes agent comparing Britannica 1771 and Wikipedia
---

# Britannica agent (live)

A live **Hermes Agent v0.22.2** that compares the Encyclopaedia Britannica, 1st edition (1771-1797), with current Wikipedia.
It runs **nvidia/Nemotron-3.5-Super-VL** on Nebius Token Factory, with the team plugin (5 tools) and the `britannica-compare` skill.

- Archive with all saved runs and the six case studies: [nebius-build-week/britannica-across-time](https://huggingface.co/spaces/nebius-build-week/britannica-across-time)
- Dataset: [nebius-build-week/britannica-wikipedia-drift](https://huggingface.co/datasets/nebius-build-week/britannica-wikipedia-drift)
- Code: [github.com/M-Ali-ML/Nebius-Hackathon](https://github.com/M-Ali-ML/Nebius-Hackathon)

## What runs here

- `search_sources`: keyword BM25 over the 262 bundled Britannica entries, and the live Wikipedia BM25 API (7.18M articles).
- `get_pair`, `find_drift`: read the bundled matches and Super VL comparisons (83 pairs, drift decomposition).
- `view_scan`, `view_neighbors`: show the bundled page scans; neighbor scans are bundled for the 10 plate pages only.

**This Space runs without the Embed/Rerank GPU.** The full pipeline used Nemotron Embed VL and Rerank VL (on a Nebius GPU) to match entries to articles. Those results are bundled. Live search here is BM25 only, so search quality is lower than in the full pipeline.

## Limits (enforced on the server)

| Limit | Value |
| --- | --- |
| Questions per browser session | 3 |
| Tool calls per question | 12 (the run stops after that) |
| Output tokens per model call | 4,000 |
| Time per question | 300 s |
| Running questions at once | 2 |
| Tokens per day, all users | 5,000,000 (from Token Factory usage) |

The daily counter is stored in `/tmp` and **resets when the Space restarts**. When the budget is spent, the Space answers:
"Daily demo budget reached. See the saved runs in the archive Space."

The Token Factory key is a Space secret. Only a local proxy inside the container uses it; Hermes and the browser never see it.

## Licenses

Britannica scans and text: National Library of Scotland, CC0. Wikipedia excerpts: CC BY-SA 4.0, cited with page and revision ids.
