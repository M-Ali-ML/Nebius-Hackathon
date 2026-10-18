# Hermes agent

The agent is Hermes Agent with `nvidia/Nemotron-3.5-Super-VL` and five tools. The map is [docs/diagrams/hermes.svg](diagrams/hermes.svg).

Tested with Hermes Agent v0.22.2. Install from the [official guide](https://hermes-agent.nousresearch.com/docs/getting-started/installation). Record your version with `hermes --version`.

Run these commands from the repository root after `.env` contains `SUPER_API_KEY` and `RETRIEVAL_BASE_URL`.

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

`data/hermes` stays out of git. It can hold conversations and the API key through Hermes config.

Plugin Doctor checks that five tools register. It does not call a model.

Ask the saved questions:

```sh
uv run nemotron-challenge run agent
```

Or open a session. Start Hermes from the same shell:

```sh
set -a; source .env; set +a
export HERMES_HOME="$PWD/data/hermes"
export NEMOTRON_REPO="$PWD"
hermes chat --toolsets nemotron_challenge --skills britannica-compare
```

The banner must show `nvidia/Nemotron-3.5-Super-VL`. Prompts for a recording are in [docs/demo-commands.md](demo-commands.md).

| Tool | Reads | Needs |
| --- | --- | --- |
| `search_sources` | LanceDB, live Wikipedia BM25, then Rerank VL | GPU service and Wikipedia API |
| `get_pair` | One saved comparison | `artifacts/compare` |
| `find_drift` | All saved comparisons | `artifacts/compare` |
| `view_scan` | The page image | `data/raw/britannica` |
| `view_neighbors` | Nearby scans in the same volume | scans, and Parse for uncached neighbors |

Each tool runs `uv run python -m nemotron_challenge.agent_tools` in `NEMOTRON_REPO`. Copy the plugin into `data/hermes` again after you change it, then restart Hermes.
