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
        pair = work_dir / "compare" / "pairs" / f"{entry.get('entry_id')}.json"
        item["has_pair"] = pair.is_file()
        by_row.setdefault(entry.get("row_index"), []).append(item)
    return {"entries": entries, "matches": matches, "by_row": by_row,
            "has_entries": bool(entries), "has_matches": bool(matches)}


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
        entries = inputs["by_row"].get(row, [])
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
        }
        rows.append(info)
        neighbours = {"prev": records[i - 1]["row_index"] if i > 0 else None,
                      "next": records[i + 1]["row_index"] if i + 1 < len(records) else None}
        blocks = [{**b, "color": CLASS_COLORS.get(b["cls"], "#4a5568")}
                  for b in sorted(record["blocks"], key=lambda b: b["order"])]
        html = env.get_template("page.html").render(
            page=info, blocks=blocks, entries=entries, inputs=inputs, nav=neighbours, built=built,
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
    }
    (site_dir / "index.html").write_text(env.get_template("index.html").render(
        rows=rows, totals=totals, inputs=inputs, built=built))
    analysis = build_analysis(env, work_dir, site_dir, built)
    return {"site_dir": str(site_dir), **totals, "missing_scans": missing_scans, "analysis": analysis}


def build_analysis(env: Environment, work_dir: Path, site_dir: Path, built: str) -> dict[str, Any]:
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
    pairs = len(list((compare / "pairs").glob("*.json"))) if (compare / "pairs").is_dir() else 0
    (site_dir / "analysis.html").write_text(env.get_template("analysis.html").render(
        plots=plots, wordfreq=wordfreq, sections=_wordfreq_sections(wordfreq), pairs=pairs, built=built))
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
