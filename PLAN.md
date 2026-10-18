# Plan: Britannica vs Wikipedia with the Nemotron stack

Status: draft for team discussion. Written 2026-10-18 12:45. Deadline 18:30 (about 5h45m).

## 1. What the reference repo changes in the earlier research

The pasted research was written without the starter repo. Several of its assumptions are wrong.

| Earlier assumption | What the starter and brief actually say | Effect on us |
| --- | --- | --- |
| We pick 100 pages with stratified sampling | Starter ships a fixed 100-scan manifest (seed `20261016`, checksums). Brief: "you can use as a starting point" | Use the fixed sample. Drop the sampling work. Document it as "organizer manifest". |
| Parse 3.0 | `nvidia/nemotron-3.5-parse`, shared endpoint, live (checked 12:44) | Default prompt already returns bbox + classes + markdown. |
| "Nemotron-3-Embed-VL", Matryoshka, 32k | `llama-nemotron-embed-vl-1b-v2`, 2048-d, query 512 tokens, doc 8k text / 2k image tokens, `input_type` is `query` or `document` | We deploy it ourselves on a Nebius GPU with the Docker recipe. |
| Reranker takes image queries | Query is text only. Documents can be text, image, or both. Max 32 docs. Scores are raw logits | Image use is on the document side (Britannica crops). |
| Wikipedia has infoboxes, images, QIDs, LiftWing scores | Shared API is BM25 over 7.18M articles. Returns title, text, revision, checksum. No images, infoboxes, or QIDs | Drop the Wiki-diagram and QID ideas. BM25 gives candidates; embed + rerank decide. |
| 5-minute or 2-minute video | Three sources disagree: track page (`pre-docs/context-submission-info.md`) says 5 min, general rules say 2 min, brief PDF says 3 min and "follow the ... 3-minute video requirements stated in this brief" | Script for 3:00 with a 2:00 cut inside it. Confirm with organizers. |
| Track page asks us to "document your selection method" | Brief allows the starter's fixed sample | README section: "organizer manifest, random without replacement, seed 20261016, 100 of 2,573 rows, manifest sha256 `7795...e396`". |
| Deploy embed/rerank on a GPU VM with an SSH tunnel | Participant guide: 1 reserved RTX PRO 6000 (96 GB, same as the recipe's reference GPU). Recommended path is a Serverless AI Endpoint with managed HTTPS and bearer auth | Deploy the Docker image as a Serverless Endpoint. Set `RETRIEVAL_BASE_URL` to its URL and `RETRIEVAL_API_KEY` to its token. The starter client already sends the bearer header. |
| (not mentioned) | Static website with compiled LaTeX per page is required, and worth points for Parse structure | Must be in the MVP. `tectonic` is installed locally. |

Claims in the research about launch dates, CharXiv scores, and native video input for Super VL are not verified. We test video input before we build on it.

## 2. Where the points are (brief rubric, 100 total)

| Criterion | Pts | What earns full marks |
| --- | --- | --- |
| Completion of specs | 20 | 5 x 4: LaTeX site, 100-page matching coverage, comparison with citations, Hermes + 6 cases, repo + video |
| Creativity | 20 | Original contribution + shown value for exploring differences |
| Parse 3.5 | 15 | Integration, fidelity with errors identified, structure (reading order, headings) in LaTeX |
| Embed + Rerank | 15 | Each works, and both work together, shown with examples |
| Hermes extension | 10 | Team-built tool/skill works and helps end to end |
| Super VL | 20 | Powers agent, comparison quality, grounding in both sources, failure handling |

The MVP must touch every row at "working" level (2 to 3 of 5). Increments then push single rows to 5.

## 2b. Status (14:00)

- Done: starter in repo root, all 100 scans parsed (98 direct, 2 by column split, 3 picture-only plates), page records in `artifacts/extract/pages/`.
- Embed/rerank: no organizer image existed, so we use one GPU VM (`nemotron-models-gpu`, RTX PRO 6000, 81.85.4.210) instead of a Serverless Endpoint. Image built on the VM in about 8 min. Container listens on VM loopback. Laptop reaches it through `ssh -N -L 8000:127.0.0.1:8000 aly@81.85.4.210`. Smoke receipt: `runs/model-service-smoke.json`.
- Super VL: works for vision and tool calls. Default reasoning is long; pipeline calls disable it. It invents text when asked to transcribe, so it does not rewrite OCR.
- Parallel Orca workers: `mvp-match` (segment + match + LanceDB), `mvp-site` (LaTeX + site), `mvp-agent` (Hermes + compare). Contracts: `docs/team-contracts.md`.

## 3. MVP: thinnest end-to-end slice (target: done by about 15:30)

Rule: every stage runs on all 100 pages, with simple logic. Quality comes later.

### Step 0. Setup (12:45 to 13:15, parallel)

- Copy the starter into our repo root (template use is allowed). Keep `reference/` as is.
- `uv sync`, `.env`, `doctor --live`.
- Start the GPU early. This is the longest pole.
  - Install the Nebius skills in Claude Code (`claude plugin marketplace add nebius/skills`, `claude plugin install nebius-cloud@nebius`) and the `nebius` CLI. Profile on our `groupNN-project`, region `uk-south2`. Read-only checks first.
  - Get the image. First ask organizers for a prebuilt image or digest. Else build it on a CPU VM in our project (linux/amd64, 60 GB disk; building amd64 on a Mac is slow) and push it to our container registry.
  - Create a Serverless Endpoint: preset `gpu-rtx6000-a` / `1gpu-24vcpu-218gb`, port 8000, bearer token auth, dry run first, team confirms before create. Weights are in the image, so a restart does not download them. A cold start still takes minutes.
  - Check `/ready`, then run `smoke_gpu.py` and keep the receipt (proof for the Embed+Rerank score).
- Token Factory: redeem the event promo code, create the key, send one Super VL text request and one image request.
- Install Hermes (`hermes --version`), copy plugin + config per `docs/hermes.md`.
- `nemotron-challenge data fetch` (357 MiB Parquet, 100 scans).

### Step 1. Extract (Parse 3.5)

- Call Parse on each scan (4 in parallel). Save raw JSON to `artifacts/extract/raw/<page>.json`. Never overwrite raw output.
- Convert blocks to a page record: reading order, class, bbox, text.
- Entry segmentation, simple rule: a new entry starts at a text block whose first token is an uppercase headword (`^[A-Z][A-Z\-]+[,.]`) or at a section header. First block without a headword = continuation from the previous page.
- Light normalization for search only (long-s `ſ`->`s`, ligatures). Keep original text for display.
- Coverage report: pages parsed, failed, blank, entries per page.

### Step 2. LaTeX + static site

- One `.tex` per page from blocks in reading order: headers -> `\section*`, text -> paragraphs, pictures -> `\includegraphics` of the bbox crop, captions under them. Two-column via `multicol` when Parse shows two columns.
- Compile with `tectonic`. Log failures, do not hide them.
- Static HTML (Jinja, no framework): page list | scan with bbox overlay (SVG) | compiled PDF | matched Wikipedia articles with scores.

### Step 3. Match (BM25 -> Embed -> Rerank)

Per entry (cap at the 3 longest entries per page for the MVP, about 300 entries):

1. Query string = headword + top TF-IDF terms of the entry. `wiki.search(top_k=30)`.
2. Embed entry (`query`) and the 30 excerpts (`document`). Keep top 10 by cosine.
3. Rerank: query = entry text (cut to 2,000 chars), documents = the 10 excerpts.
4. Decision: accept top-1 if logit > tau. Else label `no_clear_counterpart`. Keep all scores and the margin top1 - top2 as an uncertainty signal.
5. For accepted matches, fetch the full article (paginate, verify `text_sha256`).
6. Write to LanceDB: `entries` (text, vector, page_id, bbox) and `wiki_chunks` (chunked article text, vector, page_id, revision_id).

Set tau by reading 15 to 20 pairs by hand. Record that check.

### Step 4. Compare

- Corpus level: raw and normalized word frequency, top distinctive words per side (log-odds), plots like the brief examples. Count only intended documents.
- Pair level: Super VL reads entry + matched article and returns JSON: similarities, differences, each with a quote from each side; and each historical claim tagged `enduring | renamed | superseded | dropped`. Reject outputs whose quotes are not substrings of the source.
- This claim tagging is how we separate change in language (`renamed`) from change in knowledge (`superseded`).

### Step 5. Hermes agent

Replace `challenge_compare` with three tools in the plugin:

- `search_sources(query, side)`: embed query, LanceDB search on `entries` and/or `wiki_chunks`, rerank, return passages with IDs `[B:page:entry]` and `[W:page_id:rev]`.
- `get_pair(entry_id)`: entry text, matched article excerpt, scores, margin, saved comparison.
- `view_scan(page_id, bbox?)`: returns the scan crop as an image so Super VL can check OCR against the original.

Add a skill file with the answer rules: cite both sides, label inferences, say "no evidence" when a side is missing, report low-margin matches as uncertain.

### Step 6. Six cases

Run about 15 questions, save every transcript, choose 3 successes and 3 failures. Use `templates/case-study.md`. Failure candidates that will appear naturally: polysemous headwords (e.g. "calculus" as kidney stone), merged column entries from Parse, plate pages with no caption context.

## 4. Increments after the MVP (in this order)

Each one is additive. Stop at any point and still have a complete submission.

### Inc 1. Retrieval ablation and agent economics (about 1h 15m)

Hits: Embed+Rerank "combined workflow" (5), Creativity, Super VL grounding.

- Labeled set: 30 entries whose correct article we checked by hand in Step 3, plus 10 with no counterpart.
- Three configs on the same set: BM25 only / BM25 + embed / BM25 + embed + rerank. Report P@1, MRR, no-match accuracy.
- Agent side: same 10 questions with `search_sources` backed by each config. Log tool calls, tokens (Token Factory `usage`), latency, unsupported claims.
- One site tab with the table and two charts. Show it in the video.

### Inc 2. Multi-page vision tool (about 1h)

Hits: Hermes extension (10), Super VL (20), Creativity.

- First test: does Token Factory accept video for Super VL? If not, send an ordered list of images (same effect for us).
- The full Parquet has 2,573 rows and is already cached. Check that rows follow book order within a volume.
- New tool `view_neighbors(page_id, before, after)`: returns adjacent page images. Use case: a plate page or a continuation fragment whose explanation sits on another page. Super VL reads the sequence and links figure to text.
- This turns Failure 3 (orphan plate) into a repaired case. Keep the failed first attempt as its own record.

### Inc 3. Dataset export to Hugging Face (about 45m)

Hits: Creativity (value), Hugging Face Community Award.

- Export: matched pairs with scores, rerank-rejected candidates as hard negatives, claim tags, the 6 agent trajectories marked chosen / rejected.
- Keep provenance and licenses: Britannica CC0, Wikipedia CC BY-SA 4.0 with revision links.
- Publishing is public and hard to undo. Team confirms before push.

### Optional, if time remains

- Parse fidelity check: Super VL compares a crop with the Parse text and flags errors (long-s, merged columns). Direct points for "errors identified". About 45m.
- Reranker with image documents for plate pages: query = Wikipedia candidate lead, document = plate crop + caption. About 45m.
- BERTopic on our ~300 entries + matched articles (CPU is enough at this size). About 1h.

### Dropped

Stratified sampling, Wikipedia images/QIDs/infoboxes, thinking/non-thinking router (team choice), 1M-token report, Tavily.

## 5. Timeline

| Time | Work |
| --- | --- |
| 12:45 to 13:15 | Step 0. GPU starts first. |
| 13:15 to 15:30 | Steps 1 to 5 in parallel tracks |
| 15:30 | MVP freeze: full run on 100 pages, agent answers one question |
| 15:30 to 17:15 | Inc 1, then Inc 2, then Inc 3 |
| 17:15 to 18:00 | Six cases, README, submission template, site check |
| 18:00 to 18:30 | Record 3-minute video, push, submit |

Track split for 4 people (merge tracks for fewer):

- A: GPU endpoint (Nebius skills), Hermes install, then agent tools (Step 5).
- B: Extract + LaTeX + site (Steps 1, 2).
- C: Match + LanceDB (Step 3). Uses a stub retrieval client until the GPU is up.
- D: Compare + plots (Step 4), then cases and README.

## 6. Team cloud limits (from the participant guide)

- 1 GPU in total. A GPU endpoint and a GPU DevLab cannot run at the same time. The GPU serves embed/rerank only. Develop on laptops or a CPU DevLab/VM.
- 3 VMs in total, counting Serverless VMs. 20 vCPUs for CPU-only VMs. 4 disks, 500 GiB in total. 1 public IP. 1 registry. 1 bucket (200 GiB).
- Stopping the endpoint deletes its container disk. Keep LanceDB, Parse output, and site files on laptops and in git (or the team bucket), never only inside the endpoint.
- Cost is about $1.80/h while the endpoint runs. Leave it running from MVP to video, then stop it.

## 7. Risks

- GPU service late (image build or endpoint startup). Mitigation: start first; ask organizers for a prebuilt image; C builds against cached BM25 results and swaps in embed/rerank when ready.
- Endpoint 401 or 503. 401: check the gateway token. 503: read the startup logs before retrying. Do not create duplicate endpoints.
- Parse rate limits on the shared endpoint. Mitigation: cache, 4 workers, retry with backoff.
- Hermes setup friction. Mitigation: A installs it in Step 0, tests the stub plugin before tools exist.
- Video input not supported. Mitigation: multi-image fallback.

## 8. Open questions for the team

1. Team size and who takes which track?
2. Entry cap: 3 longest entries per page for the MVP, or all entries?
3. Has everyone accepted the Nebius tenant invite? What is our `groupNN-project`? Do organizers have a prebuilt embed/rerank image?
4. OK to publish the dataset to the `nebius-build-week` HF org (Inc 3)?
5. Video length: ask organizers (2, 3, or 5 minutes). Default 3:00.
