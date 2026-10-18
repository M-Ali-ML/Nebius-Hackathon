# Worker "debate": summary

Branch `M-Ali-ML/mvp-debate`, head `aa3759e`. Not pushed, not merged.

## What

The time-travel debate. Three Hermes agents on `nvidia/Nemotron-3.5-Super-VL` argue one question:
the Scholar of 1790 (Britannica evidence only), the Wikipedian (Wikipedia evidence only), and the Judge (both transcripts plus `get_pair` drift).
Format: two openings, two rebuttals, a verdict with one claim tag per point (enduring, renamed, superseded, dropped).
Rebuttals use `hermes chat --resume <session_id>`, so each persona keeps its own memory. Hermes has a native `delegate_task`, but we orchestrate the 3 processes ourselves for a fixed turn order and a full trace per turn.

Page `site/debate.html`: animated chat replay (play, pause, next, speed, URL hash `#lightning/5`, keys Space, arrows, 1-4, R, E, S), inline SVG avatars (quill, laptop, gavel), tool chips with scan thumbnails, citation pills with a hover card (checked quotes plus a scan crop), a live scoreboard, a stamp and confetti on the final verdict. No network images or scripts. Motion stops under prefers-reduced-motion.

## Rebuild

```bash
uv run python scripts/debate.py run      # model calls; skips saved debates unless --redo
uv run python scripts/debate.py verify   # checks only
uv run python scripts/debate.py site     # writes site/debate.html (+ .css, .js, site/debate/*.jpg)
```
Merge note: `base.html` gets one nav line (Debate). The site build (`run site`) does not call the debate build; run `scripts/debate.py site` after it.

## Numbers (run 16:20, 20/20 turns ok, model id checked)

| Debate | Verified | Cited | Unverified | Verified share | Grounded | Tokens | Seconds | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Lightning B:1910:0 | 3 | 16 | 3 | 14% | 86% | 126k | 71 | Wikipedian 4, draws 2 |
| Magnetism B:756:0 | 2 | 2 | 8 | 17% | 33% | 127k | 86 | Wikipedian 2, draws 2 |
| Inflammable air B:1214:0 | 4 | 9 | 0 | 31% | 100% | 99k | 54 | Wikipedian 1, draws 2 |
| Coining B:1250:1 | 3 | 15 | 4 | 14% | 82% | 98k | 70 | judge says draw (Wikipedian 2, draws 5) |

Transcripts: `artifacts/debate/<slug>.json`; summary `artifacts/debate/summary.json`. Rules and failures: `docs/debate.md`.

## Screenshots

- `runs/debate/v2-lightning.png` (full debate with judge cards)
- `runs/debate/v4-final.png` (verdict stamp, judge flags, confetti)
- also `v4-hover.png` (citation preview card), `v3-play.png` (typing replay), `v4-mobile.png`

## Known limits

- Scholar quotes often are not in the OCR text (it read the scan, or it invented them). All are marked unverified; a person must check the scan.
- Wikipedian used a malformed id `[W:19716:1352239981:1]` 3 times in Magnetism (marked unverified).
- Judge ignored "3 or 4 points" (6 and 7 points in two debates) and never gave a point to the Scholar.
- No max_tokens cap in the Hermes profile; the word limit in the prompt held (68 to 116 words).
