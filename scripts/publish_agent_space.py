"""Build and publish the live Hermes agent Space (nebius-build-week/britannica-agent).

Usage (from the repo root):

    uv run python scripts/publish_agent_space.py stage     # write build/agent-space only
    uv run python scripts/publish_agent_space.py publish   # stage, upload, set the secret, wait for the build
    uv run python scripts/publish_agent_space.py status    # runtime stage
    uv run python scripts/publish_agent_space.py pause     # pause the Space (stops spending)
    uv run python scripts/publish_agent_space.py restart   # restart it after a pause

Options: --root <checkout with artifacts/ and data/raw> (default: /Users/aly/repos/Nebius-Hackathon).
Idempotent: create_repo(exist_ok=True), upload_folder with stale files removed, secret set again.
HF_TOKEN and SUPER_API_KEY come from .env or the environment. The script never prints them and
never writes them into the staged folder.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
import time

SPACE_ID = "nebius-build-week/britannica-agent"
REPO = Path(__file__).resolve().parents[1]
STAGE = REPO / "build" / "agent-space"
CAPS = {"CAP_MAX_TOKENS": "4000", "CAP_MAX_TOOL_CALLS": "12", "CAP_QUESTIONS_PER_SESSION": "3",
        "CAP_DAILY_TOKENS": "5000000", "CAP_CONCURRENCY": "2", "CAP_QUESTION_SECONDS": "300"}


def env_value(name: str, root: Path) -> str:
    value = os.environ.get(name, "")
    for path in (REPO / ".env", root / ".env"):
        if value or not path.exists():
            continue
        for line in path.read_text().splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip().strip("'\"")
    if not value:
        sys.exit(f"{name} is not set in the environment or .env")
    return value


def stage(root: Path) -> Path:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    copy = lambda src, dst: (shutil.copytree if src.is_dir() else shutil.copy2)(src, STAGE / dst)
    copy(REPO / "space" / "Dockerfile", "Dockerfile")
    copy(REPO / "space" / "README.md", "README.md")
    copy(REPO / "pyproject.toml", "pyproject.toml")
    (STAGE / "space").mkdir()
    for name in ("app.py", "hermes-config.yaml"):
        copy(REPO / "space" / name, f"space/{name}")
    shutil.copytree(REPO / "src", STAGE / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(REPO / "integrations" / "hermes" / "nemotron-challenge", STAGE / "integrations/hermes/nemotron-challenge",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "integrations" / "hermes" / "skills", STAGE / "integrations/hermes/skills")
    art, out = root / "artifacts", STAGE / "artifacts"
    for rel in ("extract/entries.jsonl", "match/matches.jsonl", "match/page_matches.jsonl", "compare/drift_summary.json"):
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(art / rel, out / rel)
    for rel in ("extract/pages", "match/articles", "compare/pairs"):
        shutil.copytree(art / rel, out / rel)
    # plates: records and neighbor scans + parsed blocks; no raw Parse replies
    shutil.copytree(art / "plates", out / "plates", ignore=shutil.ignore_patterns("raw", "failures.jsonl"))
    shutil.copytree(root / "data" / "raw" / "britannica", STAGE / "data" / "raw" / "britannica")
    for path in STAGE.rglob("*"):  # the staged folder must never hold a secret file
        if path.name.startswith(".env") or path.suffix in {".key", ".pem"}:
            sys.exit(f"refusing to publish {path}")
    size = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file())
    print(f"staged {STAGE} ({size / 1e6:.1f} MB)")
    return STAGE


def api(root: Path):
    from huggingface_hub import HfApi

    return HfApi(token=env_value("HF_TOKEN", root))


def publish(root: Path) -> None:
    stage(root)
    hf = api(root)
    hf.create_repo(SPACE_ID, repo_type="space", space_sdk="docker", exist_ok=True)
    hf.add_space_secret(SPACE_ID, "SUPER_API_KEY", env_value("SUPER_API_KEY", root))
    for key, value in CAPS.items():
        hf.add_space_variable(SPACE_ID, key, value)
    hf.upload_folder(repo_id=SPACE_ID, repo_type="space", folder_path=str(STAGE), delete_patterns="*",
                     commit_message="Publish live Hermes agent Space")
    print(f"uploaded https://huggingface.co/spaces/{SPACE_ID}")
    wait(hf)


def wait(hf, minutes: int = 40) -> None:
    for _ in range(minutes * 4):
        stage_name = hf.get_space_runtime(SPACE_ID).stage
        print("runtime:", stage_name, flush=True)
        if stage_name in {"RUNNING", "BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR"}:
            return
        time.sleep(15)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["stage", "publish", "status", "pause", "restart"])
    parser.add_argument("--root", type=Path, default=Path("/Users/aly/repos/Nebius-Hackathon"))
    args = parser.parse_args()
    if args.command == "stage":
        stage(args.root)
    elif args.command == "publish":
        publish(args.root)
    elif args.command == "status":
        print(api(args.root).get_space_runtime(SPACE_ID).stage)
    elif args.command == "pause":
        print(api(args.root).pause_space(SPACE_ID).stage)
    else:
        print(api(args.root).restart_space(SPACE_ID).stage)


if __name__ == "__main__":
    main()
