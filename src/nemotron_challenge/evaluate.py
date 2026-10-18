"""Evaluate stage: collect run metadata and check that each case study links to a saved transcript.

Reads  docs/cases/*.md (case studies), runs/agent/**/*.json (transcripts), shared artifacts
Writes runs/evaluate.json
A case passes when its "Run record:" paths exist, each transcript names the expected model,
and its classification is success or failure. The check proves traceability, not answer quality.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .config import (EMBED_MODEL, EMBED_REVISION, PARSE_MODEL, RERANK_MODEL, RERANK_REVISION, SUPER_MODEL,
                     WIKIPEDIA_REVISION)
from .data import load_manifest

REPO = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _hermes_version() -> str | None:
    exe = shutil.which("hermes") or str(Path.home() / ".local" / "bin" / "hermes")
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
        return out.splitlines()[0].strip() if out else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def parse_case(path: Path) -> dict[str, Any]:
    text = path.read_text()
    field = lambda name: (m[1].strip() if (m := re.search(rf"^{name}:\s*(.+)$", text, re.M)) else None)
    records = re.findall(r"`?(runs/agent/[^\s`,;)]+\.json)`?", field("Run record") or "")
    return {"case": path.stem, "case_id": field("Case ID"), "classification": (field("Classification") or "").lower(),
            "run_records": records, "code_revision": field("Code revision")}


def check_case(case: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    problems, runs = [], []
    if case["classification"] not in {"success", "failure"}:
        problems.append(f"classification is {case['classification']!r}")
    if not case["run_records"]:
        problems.append("no run record path")
    for rel in case["run_records"]:
        path = next((root / rel for root in roots if (root / rel).exists()), None)
        if path is None:
            problems.append(f"missing transcript {rel}")
            continue
        rec = json.loads(path.read_text())
        runs.append({"path": rel, "status": rec.get("status"), "model": rec.get("model"),
                     "session_id": rec.get("session_id"), "tool_calls": [c["name"] for c in rec.get("tool_calls", [])
                                                                       if c["name"] != "tool_describe"],
                     "tokens": (rec.get("tokens") or {}).get("total"), "seconds": rec.get("seconds")})
        if rec.get("model") != SUPER_MODEL:
            problems.append(f"{rel}: model {rec.get('model')!r} differs from {SUPER_MODEL}")
    return {**case, "runs": runs, "ok": not problems, "problems": problems}


def run(work_dir: Path) -> dict[str, Any]:
    work_dir = Path(work_dir)
    main = work_dir.resolve().parent
    roots = [REPO, main]
    manifest = load_manifest()
    matches = _jsonl(work_dir / "match" / "matches.jsonl")
    pairs = list((work_dir / "compare" / "pairs").glob("*.json"))
    transcripts = list({p.name: p for root in (main, REPO) for p in (root / "runs" / "agent").glob("*.json")
                        if p.name != "questions.json"}.values())
    statuses = Counter(json.loads(p.read_text()).get("status") for p in transcripts)
    cases = [check_case(parse_case(p), roots) for p in sorted((REPO / "docs" / "cases").glob("*-[0-9].md"))]
    drift = work_dir / "compare" / "drift_summary.json"
    result = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "code_revision": _git("rev-parse", "HEAD"), "code_dirty": bool(_git("status", "--porcelain", "--", "src", "integrations")),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "models": {"parse": PARSE_MODEL, "embed": {"id": EMBED_MODEL, "revision": EMBED_REVISION},
                   "rerank": {"id": RERANK_MODEL, "revision": RERANK_REVISION}, "agent_and_compare": SUPER_MODEL},
        "hermes": _hermes_version(),
        "data": {"dataset": manifest["dataset"], "dataset_revision": manifest["revision"],
                 "manifest_sha256": manifest["manifest_sha256"], "sample_size": manifest["sample_size"],
                 "selection": manifest["selection"], "wikipedia_corpus_revision": WIKIPEDIA_REVISION},
        "artifacts": {
            "pages": len(list((work_dir / "extract" / "pages").glob("*.json"))),
            "entries": len(_jsonl(work_dir / "extract" / "entries.jsonl")),
            "match_status": dict(Counter(m.get("status") for m in matches)),
            "compare_pairs": len(pairs),
            "drift": {k: v for k, v in json.loads(drift.read_text()).items() if k in
                      ("pairs", "claims_checked", "claim_shares", "quotes_kept", "quotes_rejected")} if drift.exists() else None,
        },
        "agent_transcripts": {"total": len(transcripts), "by_status": dict(statuses)},
        "cases": cases,
        "cases_ok": sum(c["ok"] for c in cases),
        "cases_by_class": dict(Counter(c["classification"] for c in cases)),
    }
    out = main / "runs" / "evaluate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    return {"written": str(out), "cases": len(cases), "cases_ok": result["cases_ok"],
            "cases_by_class": result["cases_by_class"], "problems": [p for c in cases for p in c["problems"]]}
