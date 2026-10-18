#!/usr/bin/env bash
# Run the live agent Space on this machine, without Docker. Open http://127.0.0.1:7860 after start.
# Usage (from the repo root): bash scripts/run_agent_space_local.sh
# Needs: uv, Hermes Agent (~/.local/bin/hermes), SUPER_API_KEY in .env, data/raw and artifacts/ in --root.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${ROOT:-/Users/aly/repos/Nebius-Hackathon}"     # checkout with artifacts/ and data/raw/
LOCAL="$REPO/build/agent-space-local"                 # Hermes profile and UI env for the local Space
export PATH="$HOME/.local/bin:$PATH"

# 1. Stage the same files the Space would get
uv run python "$REPO/scripts/publish_agent_space.py" stage --root "$ROOT"

# 2. Separate Hermes profile: talks to the local proxy, not to Token Factory
export HERMES_HOME="$LOCAL/hermes"
mkdir -p "$HERMES_HOME/plugins" "$HERMES_HOME/skills/research"
cp "$REPO/space/hermes-config.yaml" "$HERMES_HOME/config.yaml"
rm -rf "$HERMES_HOME/plugins/nemotron-challenge"
cp -R "$REPO/integrations/hermes/nemotron-challenge" "$HERMES_HOME/plugins/"
cp -R "$REPO/integrations/hermes/skills/britannica-compare" "$HERMES_HOME/skills/research/"
hermes plugins enable nemotron-challenge >/dev/null

# 3. UI environment (same pins as the Dockerfile)
if [ ! -x "$LOCAL/uienv/bin/python" ]; then
  uv venv -q -p 3.12 "$LOCAL/uienv"
  uv pip install -q --python "$LOCAL/uienv/bin/python" \
    "gradio==5.9.1" "pydantic==2.10.6" "huggingface-hub<1.0" "httpx>=0.27,<0.29"
fi

# 4. Secrets from .env (never printed); tools run with the project venv
set -a; source "$REPO/.env"; set +a
unset HF_TOKEN RETRIEVAL_BASE_URL
uv sync -q --project "$REPO"
export NEMOTRON_TOOL_CMD="$REPO/.venv/bin/python"

echo "Starting on http://127.0.0.1:7860 (Ctrl+C to stop). Budget counter: /tmp/agent_budget.json"
cd "$REPO/build/agent-space"
exec "$LOCAL/uienv/bin/python" space/app.py
