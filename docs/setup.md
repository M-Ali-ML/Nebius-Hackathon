# Setup and installation

Run every command from the repository root.

The saved run is already in `site/`, `artifacts/`, `docs/cases/`, and `runs/agent/`. You can read it before you call a model.

## 1. Install the tools

| Tool | Use | Install |
| --- | --- | --- |
| Python 3.12 | Pipeline. Not 3.14: Hermes may use 3.14, this package does not. | `uv python install 3.12` |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Locked dependencies | official installer |
| [tectonic](https://tectonic-typesetting.github.io/) | LaTeX PDFs for `run site` | `brew install tectonic` on macOS |
| [Hermes Agent](https://hermes-agent.nousresearch.com/docs/getting-started/installation/) | Agent only. Tested at v0.22.2. | official installer |
| Docker plus an NVIDIA GPU | Embed VL and Rerank VL | [model-service.md](model-service.md) |
| Nebius Token Factory key | Super VL for compare and the agent | your own account |

Parse 3.5 and the Wikipedia BM25 API are shared event tunnels. They need no key. The URLs are in `.env.example`. If a tunnel is down, the saved files in `artifacts/` still open.

## 2. Python environment

```sh
uv python install 3.12
uv sync --locked
```

## 3. Configuration

```sh
cp .env.example .env
```

| Variable | Required for | Value |
| --- | --- | --- |
| `WIKIPEDIA_API_URL` | match, hybrid search | prefilled shared tunnel |
| `PARSE_BASE_URL` | `parse` | prefilled shared tunnel |
| `PARSE_API_KEY` | only if your Parse host requires it | empty for the event tunnel |
| `RETRIEVAL_BASE_URL` | match, `search_sources` | `http://127.0.0.1:8000/v1` |
| `RETRIEVAL_API_KEY` | only if a proxy requires it | empty for local Docker |
| `SUPER_API_KEY` | compare, plates, Hermes | your Token Factory key |
| `SUPER_BASE_URL` | Super VL | `https://api.tokenfactory.nebius.com/v1` |
| `SUPER_MODEL` | must stay | `nvidia/Nemotron-3.5-Super-VL` |
| `HF_TOKEN` | `scripts/publish_hf.py` only | your Hugging Face token |

Do not commit `.env`.

## 4. Scans

```sh
uv run nemotron-challenge data show
uv run nemotron-challenge data fetch
```

`data show` prints the pinned manifest. `data fetch` downloads the pinned Parquet file (about 357 MiB), checks checksums, and writes 100 images to `data/raw/britannica`. The images are not in git.

## 5. Check the install

```sh
uv run nemotron-challenge doctor --offline
uv run pytest -q
```

`doctor --live` also checks Wikipedia, Parse, the GPU service, and Super VL. It does not run a match. Start the GPU service first if you want that check to pass.

```sh
uv run nemotron-challenge doctor --live
```

## 6. Embedding and reranking service

On the GPU machine, from this repository:

```sh
docker buildx build --platform linux/amd64 --load \
  -t nemotron-challenge-models:local infra/model-service
docker run -d --name nemotron-models --gpus device=0 \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g \
  --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:8000:8000 nemotron-challenge-models:local
```

The image is about 6.8 GB and needs no Hub token. Wait until `curl --fail http://127.0.0.1:8000/ready` returns 200. If the GPU is on another machine, forward the port:

```sh
ssh -N -L 8000:127.0.0.1:8000 <user>@<vm>
```

Set `RETRIEVAL_BASE_URL=http://127.0.0.1:8000/v1`. Full limits, smoke check, and model pins: [model-service.md](model-service.md).

## 7. Hermes

Follow [hermes.md](hermes.md). Short form:

```sh
export HERMES_HOME="$PWD/data/hermes"
export NEMOTRON_REPO="$PWD"
mkdir -p "$HERMES_HOME/plugins" "$HERMES_HOME/skills/research"
cp integrations/hermes/config.example.yaml "$HERMES_HOME/config.yaml"
rm -rf "$HERMES_HOME/plugins/nemotron-challenge"
cp -R integrations/hermes/nemotron-challenge "$HERMES_HOME/plugins/"
cp -R integrations/hermes/skills/britannica-compare "$HERMES_HOME/skills/research/"
hermes plugins doctor integrations/hermes/nemotron-challenge --ci
hermes plugins enable nemotron-challenge
```

## 8. Run the pipeline

Parse output for these 100 pages is already in `artifacts/extract/raw`. `parse` skips a page that has a raw file.

```sh
uv run nemotron-challenge parse
uv run nemotron-challenge run extract
uv run nemotron-challenge run match
uv run nemotron-challenge run compare
uv run nemotron-challenge run site
uv run nemotron-challenge run agent
uv run nemotron-challenge run evaluate
```

| Command | What it spends |
| --- | --- |
| `parse` | Parse 3.5 only for pages missing `artifacts/extract/raw/<row>.json` |
| `run extract` | local segmentation |
| `run match` | Wikipedia API, Embed VL, Rerank VL, then LanceDB |
| `run compare` | Super VL |
| `run site` | tectonic, then `site/` |
| `run agent` | Hermes, Super VL, and the GPU service for `search_sources` |
| `run evaluate` | checks that each case links to a saved transcript |
| `build_atlas.py` | Embed VL for missing images, then `site/atlas.html` |
| `build_atlas.py --offline` | cached vectors only |
| `debate.py run` | three Hermes agents and Super VL |
| `debate.py site` | saved transcripts, then `site/debate.html` |

Plate pages: `uv run nemotron-challenge plates`. Atlas rebuild: [atlas.md](atlas.md). Debate rebuild: [debate.md](debate.md).

Open the local site:

```sh
python -m http.server 8080 -d site
```

Then open http://127.0.0.1:8080/how.html . The atlas is http://127.0.0.1:8080/atlas.html . The debate is http://127.0.0.1:8080/debate.html .

Live questions and the three demo prompts: [demo-commands.md](demo-commands.md).

## Sample and versions

The sample is the organizer's fixed draw: 100 of 2,573 scans, seed `20261016`, sorted by source row. Manifest sha256 `779542e078756874f23fa6971d7d8a2d8635ad6d9d9484e1deb607d94a28e396`.

| Source | Version |
| --- | --- |
| Britannica `NationalLibraryOfScotland/encyclopaedia_britannica_illustrated` | `309f765b1ecc83e0a7f7762e44b4a927a7555443`, CC0 |
| Wikipedia via the shared BM25 API | `417c267bb457fa645c22eb3b5c77764963194c70`, 7,182,883 articles, CC BY-SA 4.0 |
| Embed VL / Rerank VL | `582e3bf7` / `b8a9987b` |
| Run date | 2026-10-18 |

`runs/evaluate.json` records model ids, revisions, and the code revision.
