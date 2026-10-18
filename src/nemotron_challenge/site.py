"""Build the static website from page records, LaTeX builds, entries, matches, and comparison outputs.

Output (default: <work_dir>/../site):
  index.html            list of all scans
  pages/<row>.html      scan with Parse bbox overlay | compiled PDF | matched Wikipedia articles
  analysis.html         comparison plots and word frequencies, when present
  scans/, thumbs/, pdf/ copies, so the site works from file:// and from `python -m http.server`

Inputs written by other stages are optional. The site shows a note when one is missing.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import time
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .latex import latest_status, resolve_scan

TEMPLATES = Path(__file__).parent / "site_templates"
DRIFT_TAGS = ("enduring", "renamed", "superseded", "dropped")
CLASS_COLORS = {
    "Text": "#2b6cb0", "Section-header": "#c05621", "Title": "#9b2c2c", "Page-header": "#718096",
    "Page-footer": "#a0aec0", "List-item": "#2f855a", "Caption": "#b7791f", "Footnote": "#6b46c1",
    "Picture": "#d53f8c", "Table": "#00838f", "Formula": "#5a67d8",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _copy(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime or dst.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dst)
    return True


def _thumb(scan: Path, dst: Path, width: int = 160) -> bool:
    from PIL import Image

    if dst.exists() and dst.stat().st_mtime >= scan.stat().st_mtime:
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(scan) as image:
        image.thumbnail((width, width * 2))
        image.convert("RGB").save(dst, "JPEG", quality=80)
    return True


def running_head(record: dict[str, Any]) -> str:
    heads = [b["text"] for b in sorted(record["blocks"], key=lambda b: b["order"]) if b["cls"] == "Page-header"]
    if not heads:
        heads = [b["text"] for b in record["blocks"] if b["cls"] in {"Title", "Section-header"}][:1]
    return " / ".join(h.replace("\n", " ") for h in heads)[:80]


def load_inputs(work_dir: Path) -> dict[str, Any]:
    entries = read_jsonl(work_dir / "extract" / "entries.jsonl")
    matches = {m["entry_id"]: m for m in read_jsonl(work_dir / "match" / "matches.jsonl") if "entry_id" in m}
    by_row: dict[int, list[dict[str, Any]]] = {}
    for entry in entries:
        item = {**entry, "match": matches.get(entry.get("entry_id"))}
        item["pair"] = load_pair(work_dir, entry.get("entry_id", ""))
        item["has_pair"] = item["pair"] is not None
        by_row.setdefault(entry.get("row_index"), []).append(item)
    page_matches = {m["row_index"]: m for m in read_jsonl(work_dir / "match" / "page_matches.jsonl") if "row_index" in m}
    return {"entries": entries, "matches": matches, "by_row": by_row, "page_matches": page_matches,
            "has_entries": bool(entries), "has_matches": bool(matches), "has_page_matches": bool(page_matches)}


def load_pair(work_dir: Path, entry_id: str) -> dict[str, Any] | None:
    path = work_dir / "compare" / "pairs" / f"{entry_id.replace(':', '_')}.json"
    if not path.is_file():
        return None
    try:
        pair = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return pair if pair.get("claims") is not None else None


def page_drift(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Claim tag counts, 3 example claims (different tags first), and term pairs for one page."""
    pairs = [e["pair"] for e in entries if e.get("pair")]
    if not pairs:
        return None
    counts = {tag: 0 for tag in DRIFT_TAGS}
    claims = []
    for pair in pairs:
        for claim in pair.get("claims") or []:
            if claim.get("tag") in counts:
                counts[claim["tag"]] += 1
                claims.append({**claim, "cite_b": pair.get("cite_britannica"), "cite_w": pair.get("cite_wikipedia"),
                               "wiki_title": pair.get("wiki_title"), "wiki_url": pair.get("wiki_url")})
    examples, seen = [], set()
    for tag in ("superseded", "renamed", "dropped", "enduring"):
        for claim in claims:
            if claim["tag"] == tag and tag not in seen:
                examples.append(claim)
                seen.add(tag)
    examples += [c for c in claims if c not in examples]
    terms = [{**t, "cite_b": p.get("cite_britannica"), "cite_w": p.get("cite_wikipedia")}
             for p in pairs for t in p.get("term_pairs") or []]
    total = sum(counts.values())
    return {"pairs": [{"cite_b": p.get("cite_britannica"), "cite_w": p.get("cite_wikipedia"), "headword": p.get("headword"),
                       "wiki_title": p.get("wiki_title"), "wiki_url": p.get("wiki_url"),
                       "quote_check": p.get("quote_check") or {}} for p in pairs],
            "counts": counts, "total": total,
            "shares": {t: (counts[t] / total if total else 0) for t in DRIFT_TAGS},
            "examples": examples[:3], "terms": terms[:8], "model": pairs[0].get("model")}


def reason_group(reason: str | None) -> str:
    text = (reason or "").lower()
    for key, label in (("blank", "blank page (Super VL)"), ("disagree", "plate: vision rankers disagree"),
                       ("no searchable", "entry has no searchable text"), ("too short", "entry too short to judge (< 40 chars)"), ("flat margin", "flat rerank margin"),
                       ("below the acceptance", "rerank logit below the acceptance rules"),
                       ("below tau", "rerank logit below tau")):
        if key in text:
            return label
    return reason[:60] if reason else "no reason recorded"


def group_counts(rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("status") != "matched":
            label = reason_group(row.get("reason"))
            counts[label] = counts.get(label, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


def build_site(work_dir: Path, site_dir: Path | None = None) -> dict[str, Any]:
    site_dir = site_dir or work_dir.parent / "site"
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    env.filters["tojson_safe"] = lambda value: json.dumps(value, ensure_ascii=False).replace("</", "<\\/")
    site_dir.mkdir(parents=True, exist_ok=True)
    for asset in ("style.css", "app.js"):
        shutil.copy2(TEMPLATES / asset, site_dir / asset)

    records = sorted((json.loads(p.read_text()) for p in (work_dir / "extract" / "pages").glob("*.json")),
                     key=lambda r: r["row_index"])
    status = latest_status(work_dir)
    inputs = load_inputs(work_dir)
    built = time.strftime("%Y-%m-%d %H:%M")
    rows, missing_scans = [], []
    for i, record in enumerate(records):
        row = record["row_index"]
        scan = resolve_scan(record, work_dir)
        has_scan = _copy(scan, site_dir / "scans" / record["filename"])
        if has_scan:
            _thumb(scan, site_dir / "thumbs" / f"{row}.jpg")
        else:
            missing_scans.append(row)
        has_pdf = _copy(work_dir / "latex" / f"{row}.pdf", site_dir / "pdf" / f"{row}.pdf")
        _copy(work_dir / "latex" / f"{row}.tex", site_dir / "pdf" / f"{row}.tex")
        build = status.get(row, {})
        plate = load_plate(work_dir, site_dir, row)
        entries = inputs["by_row"].get(row, [])
        page_match = inputs["page_matches"].get(row)
        info = {
            "row": row, "page_id": record["page_id"], "filename": record["filename"],
            "image_sha256": record["image_sha256"], "parse_model": record.get("parse_model"),
            "finish_reason": record.get("finish_reason"), "head": running_head(record),
            "n_blocks": len(record["blocks"]), "n_entries": len(entries),
            "n_matched": sum(1 for e in entries if (e["match"] or {}).get("status") == "matched"),
            "n_uncertain": sum(1 for e in entries if (e["match"] or {}).get("status") == "no_clear_counterpart"),
            "latex": build.get("status", "not built"), "latex_error": build.get("error", ""),
            "two_column": build.get("two_column"), "has_pdf": has_pdf, "has_scan": has_scan,
            "classes": sorted({b["cls"] for b in record["blocks"]}),
            "plate_status": plate["status"] if plate else None,
            "page_match": page_match,
        }
        rows.append(info)
        neighbours = {"prev": records[i - 1]["row_index"] if i > 0 else None,
                      "next": records[i + 1]["row_index"] if i + 1 < len(records) else None}
        blocks = [{**b, "color": CLASS_COLORS.get(b["cls"], "#4a5568")}
                  for b in sorted(record["blocks"], key=lambda b: b["order"])]
        html = env.get_template("page.html").render(
            page=info, blocks=blocks, plate=plate, entries=entries, drift=page_drift(entries), page_match=page_match, inputs=inputs, nav=neighbours, built=built,
            colors={c: CLASS_COLORS.get(c, "#4a5568") for c in info["classes"]},
            aspect=record["height"] / record["width"] if record.get("width") else 1.4)
        (site_dir / "pages").mkdir(exist_ok=True)
        (site_dir / "pages" / f"{row}.html").write_text(html)

    totals = {
        "pages": len(rows), "latex_ok": sum(r["latex"] == "ok" for r in rows),
        "entries": len(inputs["entries"]), "matches": len(inputs["matches"]),
        "matched": sum(m.get("status") == "matched" for m in inputs["matches"].values()),
        "uncertain": sum(m.get("status") == "no_clear_counterpart" for m in inputs["matches"].values()),
        "errors": sum(m.get("status") == "error" for m in inputs["matches"].values()),
        "pages_matched": sum(m.get("status") == "matched" for m in inputs["page_matches"].values()),
    }
    (site_dir / "index.html").write_text(env.get_template("index.html").render(
        rows=rows, totals=totals, inputs=inputs, built=built))
    analysis = build_analysis(env, work_dir, site_dir, built, inputs, rows, totals)
    (site_dir / "how.html").write_text(env.get_template("how.html").render(built=built))
    return {"site_dir": str(site_dir), **totals, "missing_scans": missing_scans, "analysis": analysis}


def load_plate(work_dir: Path, site_dir: Path, row: int) -> dict[str, Any] | None:
    """Plate result from plates/<row>.json, with neighbor scans copied into the site."""
    path = work_dir / "plates" / f"{row}.json"
    if not path.is_file():
        return None
    plate = json.loads(path.read_text())
    for n in plate.get("neighbors", []):
        src = work_dir / n["image"]
        n["href"] = f"../neighbors/{row}/{n['row_index']}.jpg"
        n["thumb"] = f"../neighbors/{row}/{n['row_index']}.thumb.jpg"
        n["has_image"] = _copy(src, site_dir / "neighbors" / str(row) / f"{n['row_index']}.jpg")
        if n["has_image"]:
            _thumb(src, site_dir / "neighbors" / str(row) / f"{n['row_index']}.thumb.jpg", width=110)
    top = [c for c in plate.get("candidates", []) if c.get("rerank_logit") is not None]
    plate["reranked"] = sorted(top, key=lambda c: -c["rerank_logit"])
    return plate


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text()) if path.is_file() else None
    except json.JSONDecodeError:
        return None


def build_analysis(env: Environment, work_dir: Path, site_dir: Path, built: str, inputs: dict[str, Any],
                   rows: list[dict[str, Any]], totals: dict[str, Any]) -> dict[str, Any]:
    compare = work_dir / "compare"
    plots = []
    for png in sorted(compare.glob("*.png")) if compare.is_dir() else []:
        _copy(png, site_dir / "analysis" / png.name)
        plots.append(png.name)
    wordfreq = None
    wf_path = compare / "wordfreq.json"
    if wf_path.is_file():
        try:
            wordfreq = json.loads(wf_path.read_text())
        except json.JSONDecodeError as exc:
            wordfreq = {"error": f"could not read wordfreq.json: {exc}"}
    pair_files = sorted((compare / "pairs").glob("*.json")) if (compare / "pairs").is_dir() else []
    pairs = sum(1 for f in pair_files if (_read_json(f) or {}).get("claims") is not None)
    drift = _read_json(compare / "drift_summary.json")
    plates = [p for p in (_read_json(f) for f in sorted((work_dir / "plates").glob("[0-9]*.json"),
                                                       key=lambda f: int(f.stem))) if p] \
        if (work_dir / "plates").is_dir() else []
    coverage = {
        "pages": totals["pages"], "latex_ok": totals["latex_ok"],
        "parse_failures": len(read_jsonl(work_dir / "extract" / "failures.jsonl")),
        "extract": _read_json(work_dir / "extract" / "coverage.json") or {},
        "match": _read_json(work_dir / "match" / "summary.json") or {},
        "pages_summary": _read_json(work_dir / "match" / "summary_pages.json") or {},
        "entry_reasons": group_counts(list(inputs["matches"].values())),
        "page_reasons": group_counts(list(inputs["page_matches"].values())),
        "compare_failures": len(read_jsonl(compare / "failures.jsonl")),
    }
    (site_dir / "analysis.html").write_text(env.get_template("analysis.html").render(
        plots=plots, wordfreq=wordfreq, sections=_wordfreq_sections(wordfreq), pairs=pairs, built=built, drift=drift, tags=DRIFT_TAGS,
        plates=plates, coverage=coverage, totals=totals))
    return {"plots": len(plots), "wordfreq": wordfreq is not None, "pairs": pairs}


def _wordfreq_sections(data: Any) -> list[dict[str, Any]]:
    """Show any wordfreq.json shape: lists of rows become tables, scalars become a key/value list."""
    if not isinstance(data, dict):
        return []
    sections = []
    for key, value in data.items():
        if isinstance(value, list) and value:
            rows = value[:40]
            if all(isinstance(r, (list, tuple)) for r in rows):
                sections.append({"title": key, "header": None, "rows": [list(r) for r in rows]})
            elif all(isinstance(r, dict) for r in rows):
                header = list(rows[0].keys())
                sections.append({"title": key, "header": header, "rows": [[r.get(h) for h in header] for r in rows]})
            else:
                sections.append({"title": key, "header": None, "rows": [[r] for r in rows]})
        elif isinstance(value, dict) and value:
            items = list(value.items())[:40]
            if all(not isinstance(v, (dict, list)) for _, v in items):
                sections.append({"title": key, "header": None, "rows": [list(i) for i in items]})
            else:
                sections.extend({**s, "title": f"{key} / {s['title']}"} for s in _wordfreq_sections(value))
        else:
            sections.append({"title": key, "header": None, "rows": [[json.dumps(value, ensure_ascii=False)[:300]]]})
    return sections
