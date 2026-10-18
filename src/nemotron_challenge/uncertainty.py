"""Uncertainty report: why each page and entry still has no clear counterpart.

Causes come from one reader's judgment (uncertainty_causes.tsv, next to this file), checked against saved evidence.
This module joins them with the evidence and writes:
  match/uncertainty.jsonl   one line per unmatched entry (B:<row>:<n>) and page (P:<row>)
  match/uncertainty_summary.json
and adds `uncertainty_cause` and `uncertainty_note` to no_clear_counterpart rows of match/page_matches.jsonl.
No model calls.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

CAUSES = {
    "no_text": "No usable text (blank scan, caption only, bare cross-reference)",
    "ocr_failure": "Parse/OCR failure (garbled headword or text, invented text)",
    "obsolete_or_minor": "Obsolete or historical concept, or a subject too minor for its own Wikipedia article",
    "pool_miss": "Candidate pool miss: the right article exists but retrieval never returned it",
    "threshold_miss": "Threshold miss: the right article is top 1 but the scores are below the accept rules",
    "other": "Other (ranking miss, segmentation error, tables, unclear subject)",
}
TSV = Path(__file__).with_name("uncertainty_causes.tsv")


def load_causes(path: Path = TSV) -> dict[str, dict[str, str]]:
    out = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t") + ["", "", ""]
        item_id, cause, article, note = parts[:4]
        if cause not in CAUSES:
            raise ValueError(f"unknown cause {cause!r} for {item_id}")
        out[item_id] = {"cause": cause, "right_article": article or None, "note": note}
    return out


def _nonword_rate(text: str) -> float:
    from .segment import is_word, wordlist

    words = wordlist()
    tokens = [w for w in re.findall(r"[A-Za-z]{3,}", text) if not w[0].isupper()]
    return round(sum(not is_word(w, words) for w in tokens) / max(len(tokens), 1), 3)


def _best(d: dict[str, Any] | None) -> dict[str, Any] | None:
    if not d or not d.get("wiki_page_id"):
        return None
    return {k: d.get(k) for k in ("wiki_page_id", "wiki_title", "wiki_revision_id", "rerank_logit", "rerank_margin",
                                  "embed_cos", "bm25_rank", "method")}


def run_uncertainty(work_dir: Path) -> dict[str, Any]:
    from .segment import is_word, wordlist

    mdir = work_dir / "match"
    causes = load_causes()
    entries = {e["entry_id"]: e for e in map(json.loads, (work_dir / "extract" / "entries.jsonl").read_text().splitlines())}
    long = {d["entry_id"]: d for d in map(json.loads, (mdir / "matches.jsonl").read_text().splitlines())}
    short = {d["entry_id"]: d for d in map(json.loads, (mdir / "matches_short.jsonl").read_text().splitlines())}
    pages = [json.loads(l) for l in (mdir / "page_matches.jsonl").read_text().splitlines() if l.strip()]
    rows, unclassified = [], []
    for entry_id, e in entries.items():
        if long.get(entry_id, {}).get("status") == "matched" or short.get(entry_id, {}).get("status") == "matched":
            continue
        c = causes.get(entry_id) or {"cause": "other", "right_article": None, "note": "not yet classified"}
        if entry_id not in causes:
            unclassified.append(entry_id)
        head = e["headword"] or ""
        rows.append({
            "id": entry_id, "level": "entry", "row_index": e["row_index"], "page_id": e["page_id"],
            "headword": e["headword"], "cause": c["cause"], "cause_label": CAUSES[c["cause"]],
            "right_article": c["right_article"], "note": c["note"],
            "evidence": {"chars": e["chars"], "nonword_rate": _nonword_rate(e["text_norm"]),
                         "headword_in_wordlist": bool(head) and all(is_word(w, wordlist()) for w in re.findall(r"[A-Za-z]+", head)),
                         "plate": e["plate"], "text_start": e["text_norm"][:160],
                         "long_reason": long.get(entry_id, {}).get("reason"),
                         "short_reason": short.get(entry_id, {}).get("reason")},
            "best_long": _best(long.get(entry_id)), "best_short": _best(short.get(entry_id)),
            "judged_by": "match worker (Claude Opus 5.5), one reader",
        })
    for p in pages:
        if p["status"] == "matched":
            continue
        pid = f"P:{p['row_index']}"
        c = causes.get(pid) or {"cause": "other", "right_article": None, "note": "not yet classified"}
        if pid not in causes:
            unclassified.append(pid)
        vision = p.get("vision_expand") or {}
        rows.append({
            "id": pid, "level": "page", "row_index": p["row_index"], "page_id": p["page_id"],
            "page_kind": p["page_kind"], "page_topic": p.get("page_topic"),
            "cause": c["cause"], "cause_label": CAUSES[c["cause"]], "right_article": c["right_article"], "note": c["note"],
            "evidence": {"reason": p.get("reason"), "vision_subject": vision.get("subject"),
                         "vision_best": vision.get("best"), "vision_logit": vision.get("rerank_logit"),
                         "vision_margin": vision.get("rerank_margin"), "entry_ids": p.get("entry_ids")},
            "best": _best(p), "judged_by": "match worker (Claude Opus 5.5), one reader",
        })
        p["uncertainty_cause"], p["uncertainty_note"] = c["cause"], c["note"]
        if c["right_article"]:
            p["uncertainty_note"] += f" (likely article: {c['right_article']})"
    with (mdir / "uncertainty.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (mdir / "page_matches.jsonl").open("w") as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    summary = {
        "entries": dict(Counter(r["cause"] for r in rows if r["level"] == "entry")),
        "pages": dict(Counter(r["cause"] for r in rows if r["level"] == "page")),
        "entries_total": sum(r["level"] == "entry" for r in rows),
        "pages_total": sum(r["level"] == "page" for r in rows),
        "right_article_named": sum(bool(r["right_article"]) for r in rows),
        "unclassified": unclassified, "causes": CAUSES,
    }
    (mdir / "uncertainty_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary
