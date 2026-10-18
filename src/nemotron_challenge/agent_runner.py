"""Send questions to Hermes one at a time and save each full transcript, tool calls included.

Hermes runs as `hermes chat -q <question> --format stream-json`. Each JSON event line is kept as is.
Transcripts go to runs/agent/<timestamp>-<slug>.json. Failed runs are saved with their error details.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any

from .config import SUPER_MODEL

MAIN = Path(os.environ.get("NEMOTRON_MAIN", "/Users/aly/repos/Nebius-Hackathon"))
RUNS = Path(os.environ.get("NEMOTRON_RUNS", str(MAIN / "runs" / "agent")))
HERMES_HOME = os.environ.get("HERMES_HOME", str(MAIN / "data" / "hermes"))
SKILL = "britannica-compare"
DATA_URL = re.compile(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+")

DEFAULT_QUESTIONS = [
    "What did the 1771-1797 Britannica say about bleaching, and how does Wikipedia describe it today? Cite both sides.",
    "Which Britannica entries talk about air or gases? Did the language or the knowledge change compared with Wikipedia?",
    "Compare the Britannica description of ship-building with the matched Wikipedia article.",
]


def slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-") or "question"


def _hermes() -> str:
    found = shutil.which("hermes") or str(Path.home() / ".local" / "bin" / "hermes")
    if not Path(found).exists():
        raise FileNotFoundError("hermes is not installed; read docs/hermes.md")
    return found


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    tool_calls, text_parts, result, model = [], [], None, None
    for ev in events:
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            model = ev.get("model")
        elif kind == "tool_use":
            tool_calls.append({"name": ev.get("name"), "input": ev.get("input"), "output": None})
        elif kind == "tool_result":
            for call in reversed(tool_calls):
                if call["name"] == ev.get("name") and call["output"] is None:
                    call["output"] = ev.get("output")
                    break
        elif kind == "text":
            text_parts.append(ev.get("text", ""))
        elif kind == "result":
            result = ev
    final = (result or {}).get("text") or "".join(text_parts).strip()
    return {"model": model, "model_ok": model == SUPER_MODEL, "tool_calls": tool_calls, "final_text": final,
            "session_id": (result or {}).get("session_id"), "tokens": (result or {}).get("tokens"),
            "duration_ms": (result or {}).get("duration_ms"), "completed": result is not None and bool(final)}


def ask(question: str, *, repo: Path, max_turns: int = 12, timeout: int = 900, runs: Path = RUNS) -> Path:
    env = {**os.environ, "HERMES_HOME": HERMES_HOME, "NEMOTRON_REPO": str(repo)}
    cmd = [_hermes(), "chat", "-q", question, "--format", "stream-json", "-t", "nemotron_challenge",
           "-s", SKILL, "--max-turns", str(max_turns)]
    started = datetime.now()
    record: dict[str, Any] = {"question": question, "started": started.isoformat(timespec="seconds"),
                              "command": cmd[1:], "hermes_home": HERMES_HOME, "tool_repo": str(repo)}
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        events, other = [], []
        for line in proc.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                if line.strip():
                    other.append(line)
        record.update({"exit_code": proc.returncode, "stderr": proc.stderr[-4000:], "non_json_stdout": other,
                       "events": events, **summarize(events)})
        record["status"] = "ok" if proc.returncode == 0 and record["completed"] and record["model_ok"] else "failed"
    except (OSError, subprocess.TimeoutExpired) as exc:
        record.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    record["seconds"] = round(time.time() - t0, 1)
    runs.mkdir(parents=True, exist_ok=True)
    text = DATA_URL.sub("<image data omitted; see image_path>", json.dumps(record, indent=1, ensure_ascii=False))
    path = runs / f"{started.strftime('%Y%m%d-%H%M%S')}-{slug(question)}.json"
    path.write_text(text)
    return path


def run_questions(questions: list[str], *, repo: Path, runs: Path = RUNS) -> dict[str, Any]:
    saved = []
    for q in questions:
        path = ask(q, repo=repo, runs=runs)
        rec = json.loads(path.read_text())
        saved.append({"question": q, "path": str(path), "status": rec["status"],
                      "tool_calls": [c["name"] for c in rec.get("tool_calls", [])]})
    return {"runs": saved, "ok": sum(r["status"] == "ok" for r in saved), "failed": sum(r["status"] != "ok" for r in saved)}


def load_questions(path: Path | None) -> list[str]:
    if path and path.exists():
        data = json.loads(path.read_text())
        return [q if isinstance(q, str) else q["question"] for q in data]
    return DEFAULT_QUESTIONS
