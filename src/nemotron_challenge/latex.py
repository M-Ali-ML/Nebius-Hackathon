"""Turn Parse page records into LaTeX documents and compile them with tectonic.

Layout under the work dir:
  latex/<row>.tex          one document per scan, blocks in Parse reading order
  latex/<row>.pdf          tectonic output (missing when the build failed)
  latex/img/<row>-<n>.jpg  bbox crops of Picture blocks
  latex/build.jsonl        one status line per page per build run (ok or failed, with error tail)

The .tex keeps the Parse text as source data. It does not correct OCR errors.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any

TECTONIC = shutil.which("tectonic") or "/opt/homebrew/bin/tectonic"
HEAD_CLASSES = {"Page-header"}
FOOT_CLASSES = {"Page-footer"}
# Characters the Latin Modern font covers well. Others become a visible [U+XXXX] marker.
KNOWN_RANGES = ((0x20, 0x24F), (0x370, 0x3FF), (0x400, 0x4FF), (0x1E00, 0x1EFF), (0x2010, 0x2027),
                (0x2030, 0x203A), (0x20AC, 0x20AC))
CHAR_MAP = {
    "ſ": "s",  # long s: Latin Modern has no glyph, show the modern form
    "\xad": "",
    "≈": r"\ensuremath{\approx}", "√": r"\ensuremath{\surd}",
    "∞": r"\ensuremath{\infty}", "≠": r"\ensuremath{\neq}", "≤": r"\ensuremath{\leq}", "≥": r"\ensuremath{\geq}",
    "→": r"\ensuremath{\rightarrow}", "•": r"\textbullet{}", "†": r"\textdagger{}", "‡": r"\textdaggerdbl{}",
}
SPECIAL = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "#": r"\#",
    "%": r"\%", "_": r"\_", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
    "<": r"\textless{}", ">": r"\textgreater{}", "|": r"\textbar{}",
}


def _known(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in KNOWN_RANGES)


def escape(text: str, unknown: list[str] | None = None) -> str:
    """Escape one string of OCR text for LaTeX. Unknown characters stay visible as [U+XXXX]."""
    out = []
    for ch in text:
        if ch in SPECIAL:
            out.append(SPECIAL[ch])
        elif ch in CHAR_MAP:
            out.append(CHAR_MAP[ch])
        elif ch == "\n":
            out.append(" ")
        elif ch == "\t":
            out.append(" ")
        elif ord(ch) < 0x20:
            continue
        elif _known(ch):
            out.append(ch)
        else:
            if unknown is not None:
                unknown.append(ch)
            out.append(r"\unk{%04X}" % ord(ch))
    return "".join(out)


def join_lines(text: str) -> str:
    """Join hyphenated line breaks and plain line breaks inside one block."""
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)- ([a-z])", r"\1\2", text)  # a line-break hyphen that Parse already flattened
    return re.sub(r"\s*\n\s*", " ", text).strip()


def inline(text: str, unknown: list[str]) -> str:
    """Escape text and keep Parse markdown emphasis (**bold**, *italic*)."""
    parts = re.split(r"(\*\*.+?\*\*|(?<!\*)\*[^*\n]+?\*(?!\*))", text)
    out = []
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(r"\textbf{" + escape(part[2:-2], unknown) + "}")
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(r"\textit{" + escape(part[1:-1], unknown) + "}")
        else:
            out.append(escape(part, unknown))
    return "".join(out)


def table_rows(text: str) -> list[list[str]]:
    """Read cells from Parse table text (LaTeX tabular or plain rows). Drop the Parse tabular commands."""
    body = re.sub(r"\\(begin|end)\{tabular\}(\{[^}]*\})?", "", text)
    body = re.sub(r"\\hline|\\cline\{[^}]*\}", "", body)
    body = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}\{([^}]*)\}", r"\1", body)
    rows = []
    for line in re.split(r"\\\\|\n", body):
        if line.strip():
            rows.append([cell.strip() for cell in line.split("&")])
    return rows


def table_tex(text: str, unknown: list[str]) -> str:
    rows = table_rows(text)
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    width = f"{0.95 / ncols:.3f}\\linewidth"
    spec = "|".join([f">{{\\raggedright\\arraybackslash}}p{{{width}}}"] * ncols)
    lines = [" & ".join(inline(c, unknown) for c in row + [""] * (ncols - len(row))) + r" \\" for row in rows]
    return ("\\begin{center}\\scriptsize\\setlength{\\tabcolsep}{2pt}\n"
            f"\\begin{{tabular}}{{{spec}}}\n\\hline\n" + "\n".join(lines) + "\n\\hline\n\\end{tabular}\\end{center}\n")


def two_columns(blocks: list[dict[str, Any]]) -> bool:
    """True when body blocks sit on both halves of the page and are narrower than the page."""
    body = [b for b in blocks if b["cls"] not in HEAD_CLASSES | FOOT_CLASSES and b["bbox"][2] - b["bbox"][0] < 0.6]
    left = sum((b["bbox"][0] + b["bbox"][2]) / 2 < 0.5 for b in body)
    right = sum((b["bbox"][0] + b["bbox"][2]) / 2 >= 0.5 for b in body)
    return left >= 1 and right >= 1


def _is_running_head(block: dict[str, Any]) -> bool:
    if block["cls"] in HEAD_CLASSES:
        return True
    # A short block in the top margin (page number, column guide word) belongs to the running head.
    return block["cls"] in {"Text", "Section-header", "Caption"} and block["bbox"][3] < 0.07 and len(block["text"]) <= 12


def resolve_scan(record: dict[str, Any], work_dir: Path) -> Path:
    path = Path(record["scan_path"])
    if path.is_absolute():
        return path
    for base in (work_dir.parent, Path.cwd()):
        if (base / path).is_file():
            return base / path
    return work_dir.parent / path


def crop_picture(scan: Path, bbox: list[float], out: Path) -> bool:
    from PIL import Image

    with Image.open(scan) as image:
        w, h = image.size
        box = (int(max(0, bbox[0]) * w), int(max(0, bbox[1]) * h), int(min(1, bbox[2]) * w), int(min(1, bbox[3]) * h))
        if box[2] - box[0] < 4 or box[3] - box[1] < 4:
            return False
        out.parent.mkdir(parents=True, exist_ok=True)
        image.crop(box).convert("RGB").save(out, "JPEG", quality=90)
    return True


PREAMBLE = r"""\documentclass[10pt]{article}
\usepackage{fontspec}
\setmainfont{lmroman10-regular.otf}[BoldFont=lmroman10-bold.otf,ItalicFont=lmroman10-italic.otf,BoldItalicFont=lmroman10-bolditalic.otf]
\setmonofont{lmmono10-regular.otf}
\usepackage[a4paper,margin=16mm,top=14mm,bottom=16mm]{geometry}
\usepackage{multicol,graphicx,xcolor,array,fancyhdr}
\usepackage[hidelinks]{hyperref}
\setlength{\columnsep}{6mm}
\setlength{\parindent}{1em}
\setlength{\parskip}{2pt}
\newcommand{\unk}[1]{\textcolor{red}{\texttt{\scriptsize[U+#1]}}}
\pagestyle{fancy}\fancyhf{}\renewcommand{\headrulewidth}{0.4pt}
"""


def page_tex(record: dict[str, Any], work_dir: Path, scan_href: str | None = None) -> tuple[str, dict[str, Any]]:
    """Build the .tex source for one page record. Returns (source, stats)."""
    row = record["row_index"]
    blocks = sorted(record["blocks"], key=lambda b: b["order"])
    unknown: list[str] = []
    head = [b for b in blocks if _is_running_head(b)]
    foot = [b for b in blocks if b["cls"] in FOOT_CLASSES]
    body = [b for b in blocks if b not in head and b not in foot]
    multi = two_columns(body)
    scan = resolve_scan(record, work_dir)
    pictures = 0

    out: list[str] = []
    in_cols = False
    footnotes: list[str] = []
    pending_list = False

    def open_cols():
        nonlocal in_cols
        if multi and not in_cols:
            out.append("\\begin{multicols}{2}\\raggedcolumns\n")
            in_cols = True

    def close_cols():
        nonlocal in_cols
        if in_cols:
            out.append("\\end{multicols}\n")
            in_cols = False

    for block in body:
        cls, text, bbox = block["cls"], block["text"], block["bbox"]
        wide = bbox[2] - bbox[0] >= 0.6
        if cls != "List-item" and pending_list:
            out.append("\\end{itemize}\n")
            pending_list = False
        if multi and wide and cls in {"Title", "Picture", "Table", "Section-header", "Text", "Caption"}:
            close_cols()
        else:
            open_cols()
        tag = f"% block {block['order']} {cls} bbox={bbox}\n"
        out.append(tag)
        if cls == "Title":
            out.append("\\section*{\\centering " + inline(join_lines(text), unknown) + "}\n")
        elif cls == "Section-header":
            out.append("\\subsection*{" + inline(join_lines(text), unknown) + "}\n")
        elif cls == "List-item":
            if not pending_list:
                out.append("\\begin{itemize}\\setlength{\\itemsep}{1pt}\n")
                pending_list = True
            item = re.sub(r"^\s*([•\-\*]|\d+[.)]?)\s+", "", join_lines(text))
            out.append("\\item " + inline(item, unknown) + "\n")
        elif cls == "Footnote":
            footnotes.append(inline(join_lines(text), unknown))
            out.append(f"% footnote moved to page end\n")
        elif cls == "Table":
            out.append(table_tex(text, unknown))
        elif cls == "Formula":
            out.append("\\begin{center}\\small\\texttt{" + escape(join_lines(text), unknown) + "}\\end{center}\n")
        elif cls == "Picture":
            img = work_dir / "latex" / "img" / f"{row}-{block['order']}.jpg"
            if scan.is_file() and crop_picture(scan, bbox, img):
                pictures += 1
                height = "0.82\\textheight" if (bbox[3] - bbox[1]) > 0.5 else "0.45\\textheight"
                out.append("\\begin{center}\\includegraphics[width=\\linewidth,height=" + height
                           + ",keepaspectratio]{img/" + img.name + "}\\end{center}\n")
            else:
                out.append("\\begin{center}\\fbox{\\small picture crop missing}\\end{center}\n")
            if text.strip():
                out.append("{\\scriptsize\\color{gray}\\noindent Text inside picture (Parse): "
                           + inline(join_lines(text), unknown) + "\\par}\n")
        elif cls == "Caption":
            out.append("\\begin{center}\\small\\itshape " + inline(join_lines(text), unknown) + "\\end{center}\n")
        else:
            out.append(inline(join_lines(text), unknown) + "\n\n")
    if pending_list:
        out.append("\\end{itemize}\n")
    close_cols()

    head_text = " \\quad ".join(inline(join_lines(b["text"]), unknown) for b in head)
    foot_text = " \\quad ".join(inline(join_lines(b["text"]), unknown) for b in foot)
    meta = [
        ("page\\_id", escape(record["page_id"])),
        ("row index", str(row)),
        ("image sha256", escape(record["image_sha256"])),
        ("parse model", escape(str(record.get("parse_model")))),
        ("parse finish", escape(str(record.get("finish_reason")))),
        ("scan", "\\href{" + (scan_href or scan.as_uri()).replace("%", "\\%").replace("#", "\\#") + "}{"
         + escape(record["filename"]) + "}"),
    ]
    doc = [PREAMBLE,
           "\\fancyhead[C]{\\small " + head_text + "}\n",
           "\\fancyfoot[C]{\\scriptsize " + foot_text + "}\n" if foot_text else "",
           "\\begin{document}\n"]
    doc += out
    if footnotes:
        doc.append("\\par\\vspace{4pt}\\noindent\\rule{0.3\\linewidth}{0.4pt}\\par\n{\\footnotesize\n"
                   + "\n\n".join(footnotes) + "\\par}\n")
    doc.append("\\vfill\\par\\noindent\\rule{\\linewidth}{0.4pt}\\par\n{\\scriptsize\\color{gray}\\noindent "
               "Source: Encyclopaedia Britannica scan, text from Parse 3.5 without correction. "
               + " \\quad ".join(f"{k}: {v}" for k, v in meta) + "\\par}\n")
    doc.append("\\end{document}\n")
    stats = {"two_column": multi, "blocks": len(blocks), "pictures": pictures,
             "unknown_chars": "".join(sorted(set(unknown)))}
    return "".join(doc), stats


def compile_tex(tex: Path, timeout: int = 180) -> tuple[bool, str]:
    try:
        proc = subprocess.run([TECTONIC, "--chatter", "minimal", "--keep-logs", tex.name], cwd=tex.parent,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-15:]
    ok = proc.returncode == 0 and tex.with_suffix(".pdf").is_file()
    return ok, "\n".join(tail)


def build_one(record: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    out_dir = work_dir / "latex"
    row = record["row_index"]
    tex = out_dir / f"{row}.tex"
    pdf = tex.with_suffix(".pdf")
    started = time.time()
    try:
        source, stats = page_tex(record, work_dir, scan_href=f"../scans/{record['filename']}")
    except Exception as exc:  # a broken record must not stop the other pages
        return {"row_index": row, "page_id": record.get("page_id"), "status": "failed",
                "error": f"tex generation: {type(exc).__name__}: {exc}"}
    tex.write_text(source)
    if pdf.exists():
        pdf.unlink()
    ok, tail = compile_tex(tex)
    return {"row_index": row, "page_id": record["page_id"], "image_sha256": record["image_sha256"],
            "status": "ok" if ok else "failed", "seconds": round(time.time() - started, 2),
            **stats, "error": "" if ok else tail}


def build_all(work_dir: Path, workers: int = 4, rows: list[int] | None = None) -> dict[str, Any]:
    pages_dir = work_dir / "extract" / "pages"
    out_dir = work_dir / "latex"
    (out_dir / "img").mkdir(parents=True, exist_ok=True)
    records = [json.loads(p.read_text()) for p in sorted(pages_dir.glob("*.json"))]
    if rows is not None:
        records = [r for r in records if r["row_index"] in rows]
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(lambda r: build_one(r, work_dir), records))
    at = time.strftime("%Y-%m-%dT%H:%M:%S")
    with (out_dir / "build.jsonl").open("a") as log:
        for result in results:
            log.write(json.dumps({**result, "at": at}, ensure_ascii=False) + "\n")
    failed = [r["row_index"] for r in results if r["status"] != "ok"]
    return {"pages": len(results), "ok": len(results) - len(failed), "failed": failed,
            "two_column": sum(bool(r.get("two_column")) for r in results)}


def latest_status(work_dir: Path) -> dict[int, dict[str, Any]]:
    """Last build line per row from latex/build.jsonl."""
    path = work_dir / "latex" / "build.jsonl"
    status: dict[int, dict[str, Any]] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.strip():
                item = json.loads(line)
                status[item["row_index"]] = item
    return status
