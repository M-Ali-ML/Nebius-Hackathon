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
ARTIFACTS = Path(os.environ.get("NEMOTRON_ARTIFACTS", str(MAIN / "artifacts")))
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


def ask(question: str, *, repo: Path, max_turns: int = 12, timeout: int = 900, runs: Path = RUNS,
        retrieval_mode: str = "full") -> Path:
    from dotenv import dotenv_values

    import tempfile

    secrets = {k: v for k, v in dotenv_values(repo / ".env").items() if v is not None}
    tool_log = Path(tempfile.mkstemp(prefix="tool-log-", suffix=".jsonl")[1])
    env = {**secrets, **os.environ, "HERMES_HOME": HERMES_HOME, "NEMOTRON_REPO": str(repo),
           "NEMOTRON_RETRIEVAL_MODE": retrieval_mode, "NEMOTRON_TOOL_LOG": str(tool_log)}
    cmd = [_hermes(), "chat", "-q", question, "--format", "stream-json", "-t", "nemotron_challenge",
           "-s", SKILL, "--max-turns", str(max_turns)]
    started = datetime.now()
    record: dict[str, Any] = {"question": question, "started": started.isoformat(timespec="seconds"),
                              "command": cmd[1:], "hermes_home": HERMES_HOME, "tool_repo": str(repo),
                              "retrieval_mode": retrieval_mode}
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
    record["tool_log"] = [json.loads(l) for l in tool_log.read_text().splitlines() if l.strip()]
    record["tool_log_note"] = "full tool results; events[] tool outputs are cut at 5,000 chars by Hermes stream-json"
    tool_log.unlink(missing_ok=True)
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


# ---------- retrieval ablation (agent side) ----------

ABLATION_QUESTIONS = [
    {"question": "What did the Britannica say about lightning, and how does Wikipedia explain lightning today?",
     "expect_b": "B:1910:0", "expect_w": "61344"},
    {"question": "How does the Britannica explain why a magnet attracts iron, compared with Wikipedia?",
     "expect_b": "B:756:0", "expect_w": "19716"},
    {"question": "Which Britannica claims about coining money in a mint still hold today according to Wikipedia?",
     "expect_b": "B:1250:1", "expect_w": "24057311"},
    {"question": "Compare the Britannica and Wikipedia accounts of the Huguenots. Cite both sides.",
     "expect_b": "B:1327:8", "expect_w": "75899"},
    {"question": "How did the Britannica describe the city of Erfurt, and what does Wikipedia say?",
     "expect_b": "B:2473:9", "expect_w": "9481"},
    {"question": "What did the Britannica say about inflammable air (firedamp) in coal mines, and what does Wikipedia say?",
     "expect_b": "B:1214:0", "expect_w": "505455"},
    {"question": "What does the Britannica say about the planet Neptune?", "expect_b": None, "expect_w": None},
]
CITE = re.compile(r"\[(B:\d+:\d+|W:\d+:\d+)\]")
NO_EVIDENCE = re.compile(r"no evidence|can't confirm|cannot confirm|unable to|could not find|found no|has no (?:entry|article)", re.I)
META_TOOLS = {"tool_describe", "tool_search", "tool_call"}
_WIKI_REVISIONS: dict[str, str | None] = {}


def resolves(cite: str, work_dir: Path) -> bool:
    """True when a citation id names a real source: an extracted entry, or a Wikipedia page at that revision."""
    kind, a, b = cite.split(":")
    if kind == "B":
        return any(json.loads(l)["entry_id"] == cite for l in (work_dir / "extract" / "entries.jsonl").read_text().splitlines() if l.strip())
    art = work_dir / "match" / "articles" / f"{a}.json"
    if art.exists():
        return str(json.loads(art.read_text())["revision_id"]) == b
    if a not in _WIKI_REVISIONS:
        from .clients import ServiceError, WikiClient
        from .config import Settings

        try:
            with WikiClient(Settings.from_env().wikipedia_api_url) as wiki:
                _WIKI_REVISIONS[a] = wiki.article(a, 0, 1).revision_id
        except (ServiceError, ValueError):
            _WIKI_REVISIONS[a] = None
    return _WIKI_REVISIONS[a] == b


def score_run(rec: dict[str, Any], expect_b: str | None, expect_w: str | None, work_dir: Path | None = None) -> dict[str, Any]:
    final = rec.get("final_text") or ""
    cited = set(CITE.findall(final))
    w_pages = {c.split(":")[1] for c in cited if c.startswith("W:")}
    calls = [c["name"] for c in rec.get("tool_calls", []) if c["name"] not in META_TOOLS]
    out = {"status": rec.get("status"), "tool_calls": len(calls), "calls": calls,
           "tokens": (rec.get("tokens") or {}).get("total"), "seconds": rec.get("seconds"),
           "no_evidence": bool(NO_EVIDENCE.search(final[:300])), "citations": len(cited),
           "expected_b_cited": None if expect_b is None else expect_b in cited,
           "expected_w_cited": None if expect_w is None else expect_w in w_pages}
    if work_dir is not None:
        out["unresolved_citations"] = sorted(c for c in cited if not resolves(c, work_dir))
    return out


def run_ablation(modes: tuple[str, ...] = ("bm25_only", "embed_only", "full"), *, repo: Path,
                 questions: list[dict[str, Any]] = ABLATION_QUESTIONS, runs: Path = RUNS / "ablation") -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    def one_mode(mode: str) -> list[dict[str, Any]]:
        rows = []
        for q in questions:
            path = ask(q["question"], repo=repo, runs=runs / mode, retrieval_mode=mode)
            rec = json.loads(path.read_text())
            rows.append({"mode": mode, "question": q["question"], "path": str(path.relative_to(runs.parent.parent.parent))
                         if runs.parent.parent.parent in path.parents else str(path),
                         **score_run(rec, q["expect_b"], q["expect_w"], ARTIFACTS)})
        return rows

    with ThreadPoolExecutor(len(modes)) as pool:
        rows = [r for rs in pool.map(one_mode, modes) for r in rs]
    return summarize_ablation(rows, runs)


def summarize_ablation(rows: list[dict[str, Any]], runs: Path) -> dict[str, Any]:
    by_mode = {}
    for mode in dict.fromkeys(r["mode"] for r in rows):
        rs = [r for r in rows if r["mode"] == mode]
        exp_b = [r["expected_b_cited"] for r in rs if r["expected_b_cited"] is not None]
        exp_w = [r["expected_w_cited"] for r in rs if r["expected_w_cited"] is not None]
        mean = lambda k: round(sum(r[k] or 0 for r in rs) / len(rs), 1)
        by_mode[mode] = {"runs": len(rs), "ok": sum(r["status"] == "ok" for r in rs),
                         "mean_tool_calls": mean("tool_calls"), "mean_tokens": mean("tokens"), "mean_seconds": mean("seconds"),
                         "answered": sum(not r["no_evidence"] for r in rs), "no_evidence": sum(r["no_evidence"] for r in rs),
                         "expected_britannica_cited": f"{sum(exp_b)}/{len(exp_b)}",
                         "expected_wikipedia_cited": f"{sum(exp_w)}/{len(exp_w)}",
                         "citations": sum(r["citations"] for r in rs),
                         "unresolved_citations": sum(len(r.get("unresolved_citations", [])) for r in rs)}
    summary = {"time": datetime.now().isoformat(timespec="seconds"), "by_mode": by_mode, "runs": rows,
               "metrics": {"answered/no_evidence": "regex on the final text for no-evidence phrases",
                           "expected_*_cited": "the final answer cites the entry / Wikipedia page we know is the right source",
                           "unresolved_citations": "ids in the answer that name no real entry, or no Wikipedia page at that revision"}}
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    return {"by_mode": by_mode}


def rescore_ablation(runs: Path = RUNS / "ablation", questions: list[dict[str, Any]] = ABLATION_QUESTIONS) -> dict[str, Any]:
    """Score saved ablation transcripts again (no new model calls)."""
    expect = {q["question"]: q for q in questions}
    rows = []
    for mode_dir in sorted(p for p in runs.iterdir() if p.is_dir()):
        for path in sorted(mode_dir.glob("*.json")):
            rec = json.loads(path.read_text())
            q = expect.get(rec["question"])
            if q is None:
                continue
            rows.append({"mode": mode_dir.name, "question": rec["question"], "path": f"runs/agent/ablation/{mode_dir.name}/{path.name}",
                         **score_run(rec, q["expect_b"], q["expect_w"], ARTIFACTS)})
    return summarize_ablation(rows, runs)
