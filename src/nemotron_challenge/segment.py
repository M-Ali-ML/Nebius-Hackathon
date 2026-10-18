"""Split page records into Britannica entries.

Reads  extract/pages/<row>.json
Writes extract/entries.jsonl and extract/coverage.json

Rules (simple, MVP):
- Page-header and Page-footer blocks are dropped from text; the running head is kept as page metadata.
- Section-header and Title blocks that look like running heads ("H O R [ 664 ] H O R", "HEM") are treated the same way.
- A new entry starts at a block whose first words are an uppercase headword followed by "," "." or "(",
  or at a Section-header/Title that is an uppercase title ("TRIGONOMETRY.", "O R A T O R Y.").
- Body text before the first headword on a page is a continuation (headword null).
- Pages with no body text become one "plate" entry with any caption text.
- text_raw keeps Parse text with hyphenated line breaks joined. text_norm adds long-s and ligature fixes.
"""
from __future__ import annotations

from functools import lru_cache
from itertools import combinations
import json
from pathlib import Path
import re
from typing import Any

HEADER_CLASSES = {"Page-header", "Page-footer"}
BODY_CLASSES = {"Text", "List-item", "Footnote", "Formula", "Table", "Section-header", "Title"}
START_CLASSES = {"Text", "List-item", "Footnote", "Section-header", "Title"}
PLATE_CLASSES = {"Picture", "Caption"}
WORDLIST = Path("/usr/share/dict/words")

# First words in capitals ("FARM", "FARMING", "ABACUS", "HELSINGIC CHARACTER", "BLOW-PIPE") then , . or (
HEADWORD = re.compile(r"^[\s*_#]*((?:[A-Z][A-Z'\-]+)(?:[ \-][A-Z][A-Z'\-]+)*)\s*(?:[,.(]|\*)")
ROMAN = re.compile(r"[IVXLCDM]+")
SPACED_TITLE = re.compile(r"^(?:[A-Z] ){2,}[A-Z]\.?$")
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st", "ſ": "s"}
WORD = re.compile(r"[A-Za-z]+")


def strip_markup(text: str) -> str:
    return re.sub(r"[*_#]+", "", text).strip()


def join_hyphens(text: str) -> str:
    """Join words broken at a line end ("wri-\\nter", "be- nedit"), then flatten line breaks."""
    text = re.sub(r"(\w)-\s*\n\s*(?=[a-z])", r"\1", text)
    text = re.sub(r"([a-z])- (?=[a-z])", r"\1", text)
    return re.sub(r"\s*\n\s*", " ", text).strip()


def is_running_head(text: str) -> bool:
    """Running heads: short caps with a page number, or a bare 2-4 letter guide word."""
    plain = strip_markup(text)
    if len(plain) <= 40 and re.search(r"\d", plain) and not re.search(r"[a-z]{3}", plain):
        return True
    return bool(re.fullmatch(r"[A-Z]{2,4}\.?", plain.replace(" ", "")) and not SPACED_TITLE.match(plain))


def running_head_word(blocks: list[dict[str, Any]]) -> str | None:
    for block in blocks:
        if block["cls"] in HEADER_CLASSES or (block["cls"] in {"Section-header", "Title"} and is_running_head(block["text"])):
            plain = strip_markup(block["text"])
            match = re.search(r"[A-Z][A-Z .\-]*[A-Z]", plain)
            if match:
                return re.sub(r"\s+", "", match[0]) if " " in match[0] and len(match[0]) <= 12 else match[0].strip()
    return None


def headword_of(block: dict[str, Any]) -> str | None:
    text = strip_markup(block["text"])
    if block["cls"] in {"Section-header", "Title"}:
        if SPACED_TITLE.match(text):
            return text.replace(" ", "").rstrip(".")
        letters = re.sub(r"[^A-Za-z]", "", text)
        if len(letters) >= 3 and letters.isupper() and not ROMAN.fullmatch(letters):
            return re.sub(r"\s+", " ", text).rstrip(".")
    match = HEADWORD.match(block["text"])
    if match and sum(c.isupper() for c in match[1]) >= 2 and not ROMAN.fullmatch(match[1]):
        return match[1].strip(" -")
    return None


@lru_cache(maxsize=1)
def wordlist() -> frozenset[str]:
    if not WORDLIST.is_file():
        return frozenset()
    return frozenset(w.strip().lower() for w in WORDLIST.read_text(errors="ignore").splitlines() if w.strip())


def is_word(word: str, words: frozenset[str]) -> bool:
    w = word.lower()
    if w in words:
        return True
    for suffix, repl in (("s", ""), ("es", ""), ("ed", ""), ("ed", "e"), ("d", ""), ("ing", ""), ("ing", "e"),
                         ("ly", ""), ("ies", "y"), ("ied", "y"), ("er", ""), ("est", "")):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3 and w[: -len(suffix)] + repl in words:
            return True
    return False


@lru_cache(maxsize=100_000)
def fix_long_s(word: str) -> str:
    """Return the word with some f->s swaps if the original is not a word and a swap is."""
    words = wordlist()
    if "f" not in word.lower() or not words or is_word(word, words):
        return word
    spots = [i for i, c in enumerate(word) if c in "fF"]
    if len(spots) > 4:
        spots = spots[:4]
    for k in range(1, len(spots) + 1):
        for chosen in combinations(spots, k):
            chars = list(word)
            for i in chosen:
                chars[i] = "S" if chars[i] == "F" else "s"
            candidate = "".join(chars)
            if is_word(candidate, words):
                return candidate
    return word


def normalize(text: str) -> tuple[str, int]:
    edits = 0
    for lig, repl in LIGATURES.items():
        edits += text.count(lig)
        text = text.replace(lig, repl)
    text = strip_markup(text)

    def swap(match: re.Match) -> str:
        nonlocal edits
        fixed = fix_long_s(match[0])
        edits += fixed != match[0]
        return fixed

    return WORD.sub(swap, text), edits


def _finish(entry: dict[str, Any]) -> dict[str, Any]:
    raw = " ".join(entry.pop("_parts")).strip()
    raw = re.sub(r"([a-z])- (?=[a-z])", r"\1", raw)  # hyphen split across blocks
    norm, edits = normalize(raw)
    entry.update(text_raw=raw, text_norm=norm, norm_edits=edits, chars=len(raw))
    return entry


def segment_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    row, blocks = page["row_index"], sorted(page["blocks"], key=lambda b: b["order"])
    head = running_head_word(blocks)
    base = {"page_id": page["page_id"], "row_index": row, "image_sha256": page.get("image_sha256"), "running_head": head}
    body = [b for b in blocks if b["cls"] in BODY_CLASSES and b["text"].strip()
            and not (b["cls"] in {"Section-header", "Title"} and is_running_head(b["text"]))
            and not re.fullmatch(r"[\W\d]{0,10}", strip_markup(b["text"]))]
    if sum(len(b["text"]) for b in body) < 80:
        plate_blocks = [b for b in blocks if b["cls"] in PLATE_CLASSES or b in body]
        captions = [join_hyphens(b["text"]) for b in plate_blocks if b["text"].strip()]
        entry = {**base, "entry_id": f"B:{row}:0", "headword": None, "is_continuation": False, "plate": True,
                 "block_orders": [b["order"] for b in plate_blocks], "bboxes": [b["bbox"] for b in plate_blocks],
                 "_parts": captions}
        return [_finish(entry)]
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for block in body:
        headword = headword_of(block) if block["cls"] in START_CLASSES else None
        if headword or current is None:
            if current:
                entries.append(_finish(current))
            current = {**base, "entry_id": f"B:{row}:{len(entries)}", "headword": headword,
                       "is_continuation": headword is None, "plate": False,
                       "block_orders": [], "bboxes": [], "_parts": []}
        current["block_orders"].append(block["order"])
        current["bboxes"].append(block["bbox"])
        current["_parts"].append(join_hyphens(block["text"]))
    if current:
        entries.append(_finish(current))
    return entries


def run_segment(work_dir: Path) -> dict[str, Any]:
    pages_dir = work_dir / "extract" / "pages"
    pages = sorted((json.loads(p.read_text()) for p in pages_dir.glob("*.json")), key=lambda p: p["row_index"])
    all_entries, per_page, heads = [], {}, {}
    for page in pages:
        entries = segment_page(page)
        all_entries += entries
        per_page[str(page["row_index"])] = len(entries)
        heads[str(page["row_index"])] = entries[0]["running_head"] if entries else None
    out = work_dir / "extract" / "entries.jsonl"
    with out.open("w") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    failures_path = work_dir / "extract" / "failures.jsonl"
    failures = [json.loads(line) for line in failures_path.read_text().splitlines() if line.strip()] if failures_path.is_file() else []
    coverage = {
        "pages": len(pages),
        "entries": len(all_entries),
        "entries_per_page": per_page,
        "continuations": sum(e["is_continuation"] for e in all_entries),
        "with_headword": sum(e["headword"] is not None for e in all_entries),
        "plates": [e["row_index"] for e in all_entries if e["plate"]],
        "blank_pages": [e["row_index"] for e in all_entries if e["plate"] and not e["text_raw"]],
        "norm_edits": sum(e["norm_edits"] for e in all_entries),
        "running_heads": heads,
        "parse_failures": failures,
        "wordlist": str(WORDLIST) if wordlist() else None,
    }
    (work_dir / "extract" / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=1))
    return {k: v for k, v in coverage.items() if k not in {"entries_per_page", "running_heads", "parse_failures"}} | {
        "parse_failures": len(failures),
        "mean_entries_per_page": round(len(all_entries) / max(len(pages), 1), 2),
        "max_entries_page": max(per_page.items(), key=lambda kv: kv[1]) if per_page else None,
    }
