# Time-travel debate

Three Hermes agents on `nvidia/Nemotron-3.5-Super-VL` debate one question. The page is `site/debate.html`.

## Roles

| Role | Evidence | Tools | Voice |
| --- | --- | --- | --- |
| The Scholar of 1790 | Britannica only | `search_sources` (side `britannica`), `get_pair` (Britannica side), `view_scan` | light 18th-century |
| The Wikipedian | Wikipedia only | `search_sources` (side `wikipedia`, live BM25 included) | modern |
| The Judge | both transcripts and the saved drift | `get_pair` once | neutral, JSON verdict |

The format is: opening statement from each side, one rebuttal from each side, then the verdict.
The judge rules on each point with one of the four claim tags:
`enduring` (both agree), `renamed` (the language changed), `superseded` (the knowledge changed), `dropped` (Wikipedia no longer says it).
The judge names a winner per point and overall, flags uncited or unsupported claims, and labels inferences.

## How it runs

Each turn is one `hermes chat -q ... --format stream-json -t nemotron_challenge -s britannica-compare` process.
The two openings run in parallel. Each rebuttal uses `--resume <session_id>` on the speaker's own session, so a persona keeps its own memory and tool results. The saved session ids show this.
The judge is a new session.

Hermes v0.22.2 has a native `delegate_task` tool for sub-agents. We did not use it: we need a fixed turn order and a full tool trace for every turn, and child runs do not appear in the parent's stream-json. We orchestrate the three processes ourselves in `src/nemotron_challenge/debate.py`.

Caps:
- Personas: `--reasoning none` (thinking off). The judge: `--reasoning low`.
- `--max-turns 7`: at most 6 tool calls and one reply per turn.
- The prompt asks for 80 to 120 words, at least two exact quotes, and at most 3 more tool calls in a rebuttal.
- We did not set a `max_tokens` cap in the Hermes profile. The word limit in the prompt held for the personas (replies of 68 to 116 words).

## Rebuild

Run from the worktree or the main checkout. Hermes must use the main checkout profile (`data/hermes`).

```bash
uv run python scripts/debate.py run          # 4 debates in parallel, about 90 s; skips saved debates (add --redo)
uv run python scripts/debate.py verify       # check citations and quotes again, no model calls
uv run python scripts/debate.py site         # write site/debate.html, site/debate.css, site/debate.js, site/debate/*.jpg
```

Outputs: `artifacts/debate/<slug>.json` (every turn: prompt, command, all stream-json events, full tool log, reply, tokens, seconds, session id, status, checks) and `artifacts/debate/summary.json`.

## Verification

Every sentence that cites or quotes gets one status:

- `verified`: every cited id resolves to a saved record (an entry in `extract/entries.jsonl`, an article in `match/articles/` at that revision, or a live BM25 hit returned by a tool in this debate) and every quote is a substring of the cited source (`compare.quote_ok`, same normalization as the compare stage).
- `cited`: the ids resolve, but the sentence has no quote to check.
- `unverified`: an id does not resolve, an id has a malformed form, or a quote is not in the cited source. The page shows these sentences with a red dashed underline. We do not hide them.
- `echo`: an uncited quote of the opponent's words. It is not a source claim and is not counted.

Run on 2026-10-18 at 16:20, 20 of 20 turns completed with the expected model id:

| Debate | Entry | Verified | Cited | Unverified | Verified share | Grounded share | Tool calls | Tokens | Seconds | Judge |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Lightning | B:1910:0 | 3 | 16 | 3 | 14% | 86% | 8 | 126k | 71 | Wikipedian 4, draws 2 |
| Magnetism | B:756:0 | 2 | 2 | 8 | 17% | 33% | 12 | 127k | 86 | Wikipedian 2, draws 2 |
| Inflammable air | B:1214:0 | 4 | 9 | 0 | 31% | 100% | 8 | 99k | 54 | Wikipedian 1, draws 2 |
| Coining | B:1250:1 | 3 | 15 | 4 | 14% | 82% | 7 | 98k | 70 | overall draw (Wikipedian 2, draws 5) |

Grounded share = (verified + cited) / all checked sentences.
The numbers come from `artifacts/debate/summary.json`. Rerun `verify` to recompute them.

## Honest failures

1. The Scholar quotes text that is not in the OCR. In Magnetism it quotes "is attracted by a magnet" and "all this is extremely obscure" for `[B:756:0]`. Neither string is in the stored OCR text. The Scholar called `view_scan` in that turn, so some quotes can be readings of the scan that the OCR lacks (in Lightning, "mathematically evident" is OCR "_mattematically couldn"). We cannot tell a scan reading from an invented quote without a person checking the image. We mark all of them `unverified`.
2. The Wikipedian used a malformed id `[W:19716:1352239981:1]` (an extra chunk number) three times in Magnetism. The tools never issue this form. We mark it `unverified`.
3. The judge did not keep to "3 or 4 points": Lightning has 6 points and Coining has 7.
4. The judge never gave a point to the Scholar. Inference: the rulings tie "superseded" to a Wikipedian win, so the format favors the modern side when the knowledge changed. A fairer judge would also score evidence quality per side.
5. In Coining the judge called the overall result a draw, although the point count is Wikipedian 2, Scholar 0.

## Page

`site/debate.html` replays the saved runs as a chat: typing animation, play, pause, next, speed, and a step link in the URL hash (`#lightning/5`). Shortcuts: Space, arrow keys, 1 to 4, R, E, S.
Each citation is a pill that links to `pages/<row>.html` or the Wikipedia revision. A hover card shows the checked quotes and a crop of the scan.
The page loads no images or scripts from the network (icons and avatars are inline SVG). Fonts fall back to system fonts offline. Motion stops under `prefers-reduced-motion`.
