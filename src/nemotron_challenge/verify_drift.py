"""Visual scan verification of top drift items using Nemotron 3.5 Super VL.

Reads  compare/pairs/*.json, extract/entries.jsonl, extract/pages/*.json
Writes compare/raw_scan_check/<check_id>.json
       compare/pairs/*.json (attaches scan_check metadata on verified claims and term_pairs)
       compare/drift_verification.json
       compare/drift_summary.json, compare/drift.png
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any

from .agent_tools import ARTIFACTS, view_scan
from .clients import ChatClient, ServiceError
from .compare import drift_summary, norm, parse_json, safe_id
from .config import Settings

TOP_K = 25
WORKERS = 4
PROMPT_VERSION = "scan-check-v1"
DEMO_ENTRIES = {
    "B:713:3",
    "B:1910:0",
    "B:1017:11",
    "B:560:2",
    "B:1327:8",
    "B:1473:7",
    "B:2171:9",
    "B:452:0",
}

SYSTEM = (
    "You are an 18th-century print specialist verifying whether an apparent difference or renamed term between "
    "an Encyclopaedia Britannica OCR excerpt (1771-1797) and modern Wikipedia is a genuine historical shift or "
    "an OCR misreading of the physical scan. "
    "Warning: any OCR quote or OCR-derived claim may have misread initial or medial long-s (ſ) as f (for example, "
    "reading printed \"ſixteenth\" [sixteenth, 1/16] as \"fitteenth\" [fifteenth], or \"riſe\" [rise] as \"rife\", "
    "or \"ſhips\" [ships] as \"flips\", or \"ſlaves\" [slaves] as \"flares\"), or garbled italic or worn letters "
    "(such as \"The Craftsman\" read as \"Zie Grafjnaar\", \"tenements\" read as \"tenparts\", \"crown\" read as \"cry\", "
    "\"Thuringia\" read as \"Thailand\", or \"Peſcara\" read as \"Pofcara\"). "
    "Conversely, if the scan prints a genuinely archaic or older name or term for the same concept (such as "
    "\"Bothnic gulph\" vs \"Gulf of Bothnia\", \"Jupiter\" vs \"Zeus\", \"electric fire\" vs \"electric charge\", "
    "or a genuinely different historical date or measurement), that is a confirmed historical shift "
    "(\"status\": \"confirmed\", \"is_ocr_error\": false), even if the OCR had a minor one-letter typo like "
    "\"Botnhic\" for \"Bothnic\". Reply with one JSON object only, no prose."
)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _pad_bbox(bboxes: list[list[float]], pad: float = 0.015) -> list[float] | None:
    valid = [b for b in bboxes if isinstance(b, list) and len(b) == 4 and b[0] < b[2] and b[1] < b[3]]
    if not valid:
        return None
    x1 = min(1.0, max(0.0, min(b[0] for b in valid) - pad))
    y1 = min(1.0, max(0.0, min(b[1] for b in valid) - pad))
    x2 = min(1.0, max(0.0, max(b[2] for b in valid) + pad))
    y2 = min(1.0, max(0.0, max(b[3] for b in valid) + pad))
    if x1 >= x2 or y1 >= y2:
        return None
    return [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)]


def _norm_plain(text: str) -> str:
    return re.sub(r"[_*]", "", norm(text))


def resolve_entry_and_bbox(
    pair: dict[str, Any],
    item: dict[str, Any],
    entries: dict[str, dict[str, Any]],
    pages: dict[int, dict[str, Any]],
) -> tuple[str, list[float] | None]:
    cite = (item.get("cite_britannica") or "").strip().strip("[]")
    eid = cite if cite in entries else pair["entry_id"]
    if eid.startswith("P:") or eid not in entries:
        for cand in pair.get("entry_ids", []):
            if cand in entries:
                eid = cand
                break
    entry = entries.get(eid)
    if not entry or not entry.get("bboxes"):
        return eid, None
    bboxes = entry["bboxes"]
    quote = _norm_plain(item.get("quote_britannica") or "")
    if len(bboxes) > 2 and quote:
        page = pages.get(entry["row_index"], {})
        orders = set(entry.get("block_orders") or [])
        for blk in page.get("blocks", []):
            if (not orders or blk.get("order") in orders) and blk.get("bbox"):
                if quote[:36] in _norm_plain(blk.get("text") or ""):
                    padded = _pad_bbox([blk["bbox"]], pad=0.02)
                    if padded is not None:
                        return eid, padded
    return eid, _pad_bbox(bboxes, pad=0.015)


def collect_targets(work_dir: Path, top_k: int = TOP_K) -> list[dict[str, Any]]:
    pairs_dir = work_dir / "compare" / "pairs"
    pairs = {p.stem: json.loads(p.read_text()) for p in sorted(pairs_dir.glob("*.json"))}

    by_kind: dict[str, list[dict[str, Any]]] = {"term_pairs": [], "superseded": [], "renamed": []}
    extra_items: list[dict[str, Any]] = []

    for stem, pair in pairs.items():
        if pair.get("status") != "ok":
            continue
        eid = pair["entry_id"]
        margin = pair.get("rerank_margin")
        lexical_set = {(t["old"], t["new"]) for t in pair.get("drift", {}).get("lexical", {}).get("term_pairs", [])}

        for idx, tp in enumerate(pair.get("term_pairs", [])):
            rec = {
                "pair_stem": stem,
                "entry_id": eid,
                "wiki_title": pair.get("wiki_title"),
                "cite_britannica": tp.get("cite_britannica") or pair.get("cite_britannica"),
                "cite_wikipedia": pair.get("cite_wikipedia"),
                "rerank_margin": margin,
                "kind": "term_pairs",
                "section": "term_pairs",
                "index": idx,
                "item": tp,
            }
            if (tp["old"], tp["new"]) in lexical_set:
                by_kind["term_pairs"].append(rec)
            elif eid in DEMO_ENTRIES:
                extra_items.append(rec)

        for idx, cl in enumerate(pair.get("claims", [])):
            tag = cl.get("tag")
            if tag in ("superseded", "renamed"):
                rec = {
                    "pair_stem": stem,
                    "entry_id": eid,
                    "wiki_title": pair.get("wiki_title"),
                    "cite_britannica": cl.get("cite_britannica") or pair.get("cite_britannica"),
                    "cite_wikipedia": pair.get("cite_wikipedia"),
                    "rerank_margin": margin,
                    "kind": tag,
                    "section": "claims",
                    "index": idx,
                    "item": cl,
                }
                by_kind[tag].append(rec)

    selected: dict[tuple[str, str, int], dict[str, Any]] = {}
    for kind, rows in by_kind.items():
        rows.sort(key=lambda r: -(r.get("rerank_margin") or 0.0))
        for rank, r in enumerate(rows[:top_k], start=1):
            key = (r["pair_stem"], r["section"], r["index"])
            selected[key] = {**r, "rank": rank}
        for r in rows[top_k:]:
            if r["entry_id"] in DEMO_ENTRIES:
                key = (r["pair_stem"], r["section"], r["index"])
                selected.setdefault(key, {**r, "rank": None})

    for r in extra_items:
        key = (r["pair_stem"], r["section"], r["index"])
        selected.setdefault(key, {**r, "rank": None})

    return list(selected.values())


def check_id(target: dict[str, Any]) -> str:
    item = target["item"]
    sig = f"{target['entry_id']}|{target['section']}|{item.get('old', '')}|{item.get('new', '')}|{item.get('claim', '')}|{item.get('quote_britannica', '')}"
    digest = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:8]
    return f"{safe_id(target['entry_id'])}_{target['kind']}_{target['index']}_{digest}"


def build_user_prompt(target: dict[str, Any], scan_eid: str) -> str:
    item = target["item"]
    if target["section"] == "term_pairs":
        desc = (
            f"Unverified OCR candidate term pair (old -> new): \"{item['old']}\" -> \"{item['new']}\"\n"
            f"(Warning: \"{item['old']}\" comes from noisy OCR and may actually be \"{item['new']}\" printed with long-s ſ or worn type on the scan.)\n"
            f"Britannica OCR quote: \"{item.get('quote_britannica', '')}\"\n"
            f"Wikipedia quote ({target.get('wiki_title', '')}): \"{item.get('quote_wikipedia', '')}\""
        )
    else:
        desc = (
            f"Unverified OCR-derived claim (tagged {item.get('tag')}): \"{item.get('claim', '')}\"\n"
            f"Britannica OCR quote: \"{item.get('quote_britannica', '')}\"\n"
            f"Wikipedia quote ({target.get('wiki_title', '')}): \"{item.get('quote_wikipedia', '')}\""
        )
    return (
        f"Inspect the scan crop for Britannica entry {scan_eid}.\n"
        f"{desc}\n\n"
        "Return JSON with keys:\n"
        "- \"scan_reading\": string (what is actually printed on the 18th-century scan for the key word or phrase)\n"
        "- \"is_ocr_error\": boolean (true if the apparent difference or rename is caused by OCR misreading the scan "
        "or mispairing a corrupted OCR word; false if the scan genuinely prints an older historical term or a "
        "genuinely different historical claim)\n"
        "- \"status\": \"confirmed\" or \"ocr_error\"\n"
        "- \"explanation\": 1 short sentence citing what is visible on the scan (use single quotes around words inside strings, no em dashes)."
    )


def _parse_scan_json(content: str) -> dict[str, Any]:
    try:
        return parse_json(content)
    except ValueError:
        sr = re.search(r'"scan_reading"\s*:\s*"(.*?)"\s*,\s*"is_ocr_error"', content, re.S)
        ie = re.search(r'"is_ocr_error"\s*:\s*(true|false)', content, re.I)
        st = re.search(r'"status"\s*:\s*"(confirmed|ocr_error)"', content, re.I)
        ex = re.search(r'"explanation"\s*:\s*"(.*)"\s*\}', content, re.S)
        if sr and ie and ex:
            return {
                "scan_reading": sr.group(1).replace('\\"', "'").replace('"', "'").strip(),
                "is_ocr_error": ie.group(1).lower() == "true",
                "status": st.group(1).lower() if st else ("ocr_error" if ie.group(1).lower() == "true" else "confirmed"),
                "explanation": ex.group(1).replace('\\"', "'").replace('"', "'").strip(),
            }
        raise


def verify_one(
    chat: ChatClient,
    target: dict[str, Any],
    entries: dict[str, dict[str, Any]],
    pages: dict[int, dict[str, Any]],
    pairs: dict[str, dict[str, Any]],
    work_dir: Path,
    redo: bool = False,
) -> dict[str, Any]:
    cid = check_id(target)
    raw_dir = work_dir / "compare" / "raw_scan_check"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{cid}.json"

    pair = pairs[target["pair_stem"]]
    scan_eid, bbox = resolve_entry_and_bbox(pair, target["item"], entries, pages)

    if raw_path.exists() and not redo:
        saved = json.loads(raw_path.read_text())
        parsed = saved.get("parsed")
        if isinstance(parsed, dict) and parsed.get("status") in ("confirmed", "ocr_error"):
            return {**target, "check_id": cid, "scan_entry_id": scan_eid, "bbox": bbox, "scan_check": parsed}

    meta, img_bytes = view_scan(scan_eid, bbox=bbox, work_dir=work_dir)
    data_url = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()
    user_text = build_user_prompt(target, scan_eid)
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]
    reply = None
    last_err = None
    for attempt in range(3):
        extra = {"chat_template_kwargs": {"enable_thinking": False}, "temperature": 0.0 if attempt == 0 else 0.2}
        t0 = time.time()
        try:
            reply = chat.complete(messages, max_tokens=300, extra_body=extra)
            reply["_seconds"] = round(time.time() - t0, 2)
            data = _parse_scan_json(reply["choices"][0]["message"]["content"])
            is_err = bool(data.get("is_ocr_error"))
            scan_reading = str(data.get("scan_reading") or "").replace("—", ", ")
            explanation = str(data.get("explanation") or "").replace("—", ", ").replace("–", "-")
            if target["section"] == "term_pairs":
                new_norm = norm(target["item"].get("new") or "")
                old_norm = norm(target["item"].get("old") or "")
                sr_norm = norm(scan_reading)
                if new_norm and new_norm in sr_norm and old_norm not in sr_norm:
                    is_err = True
            status = "ocr_error" if is_err else "confirmed"
            parsed = {
                "scan_reading": scan_reading,
                "is_ocr_error": is_err,
                "status": status,
                "explanation": explanation,
                "scan_entry_id": scan_eid,
                "bbox": bbox,
                "model": reply.get("model"),
            }
            raw_path.write_text(
                json.dumps(
                    {
                        "check_id": cid,
                        "entry_id": target["entry_id"],
                        "scan_entry_id": scan_eid,
                        "bbox": bbox,
                        "scan_meta": meta,
                        "prompt_version": PROMPT_VERSION,
                        "parsed": parsed,
                        "reply": reply,
                    },
                    ensure_ascii=False,
                    indent=1,
                )
            )
            return {**target, "check_id": cid, "scan_entry_id": scan_eid, "bbox": bbox, "scan_check": parsed}
        except (ServiceError, ValueError, KeyError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(2 * (attempt + 1))

    raise RuntimeError(f"scan check failed for {cid}: {last_err}")


def run(settings: Settings | None = None, work_dir: Path = ARTIFACTS, top_k: int = TOP_K, redo: bool = False) -> dict[str, Any]:
    settings = settings or Settings.from_env()
    work_dir = Path(work_dir)
    entries = {e["entry_id"]: e for e in _jsonl(work_dir / "extract" / "entries.jsonl")}
    pages = {int(p.stem): json.loads(p.read_text()) for p in (work_dir / "extract" / "pages").glob("*.json") if p.stem.isdigit()}
    pairs_dir = work_dir / "compare" / "pairs"
    pairs = {p.stem: json.loads(p.read_text()) for p in sorted(pairs_dir.glob("*.json"))}

    targets = collect_targets(work_dir, top_k=top_k)
    with ChatClient(settings.super_base_url, settings.super_api_key, settings.super_model, timeout=180) as chat:
        chat.verify_model()
        with ThreadPoolExecutor(WORKERS) as pool:
            results = list(pool.map(lambda t: verify_one(chat, t, entries, pages, pairs, work_dir, redo=redo), targets))

    touched_stems: set[str] = set()
    for r in results:
        stem = r["pair_stem"]
        pair = pairs[stem]
        sec = r["section"]
        idx = r["index"]
        sc = r["scan_check"]
        pair[sec][idx]["scan_check"] = sc
        if sec == "term_pairs":
            old_val, new_val = pair[sec][idx].get("old"), pair[sec][idx].get("new")
            for ltp in pair.get("drift", {}).get("lexical", {}).get("term_pairs", []):
                if ltp.get("old") == old_val and ltp.get("new") == new_val:
                    ltp["scan_check"] = sc
            for otp in pair.get("drift", {}).get("lexical", {}).get("likely_ocr_or_spelling", []):
                if otp.get("old") == old_val and otp.get("new") == new_val:
                    otp["scan_check"] = sc
        touched_stems.add(stem)

    for stem in sorted(touched_stems):
        (pairs_dir / f"{stem}.json").write_text(json.dumps(pairs[stem], ensure_ascii=False, indent=1))

    by_kind_summary: dict[str, dict[str, int]] = {}
    ocr_illusions: list[dict[str, Any]] = []
    confirmed_shifts: list[dict[str, Any]] = []

    for r in results:
        k = r["kind"]
        sc = r["scan_check"]
        bucket = by_kind_summary.setdefault(k, {"checked": 0, "confirmed": 0, "ocr_error": 0})
        bucket["checked"] += 1
        bucket[sc["status"]] += 1
        item = r["item"]
        summary_row = {
            "check_id": r["check_id"],
            "entry_id": r["entry_id"],
            "scan_entry_id": r["scan_entry_id"],
            "cite_britannica": r["cite_britannica"],
            "cite_wikipedia": r["cite_wikipedia"],
            "wiki_title": r["wiki_title"],
            "rerank_margin": r["rerank_margin"],
            "kind": k,
            "rank": r["rank"],
            "old": item.get("old"),
            "new": item.get("new"),
            "claim": item.get("claim"),
            "quote_britannica": item.get("quote_britannica"),
            "quote_wikipedia": item.get("quote_wikipedia"),
            "scan_check": sc,
        }
        if sc["is_ocr_error"]:
            ocr_illusions.append(summary_row)
        else:
            confirmed_shifts.append(summary_row)

    report = {
        "model": settings.super_model,
        "prompt_version": PROMPT_VERSION,
        "total_checked": len(results),
        "confirmed_count": len(confirmed_shifts),
        "ocr_error_count": len(ocr_illusions),
        "ocr_error_rate": round(len(ocr_illusions) / max(1, len(results)), 3),
        "by_kind": by_kind_summary,
        "ocr_illusions": ocr_illusions,
        "confirmed_shifts": confirmed_shifts,
    }
    out_path = work_dir / "compare" / "drift_verification.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    drift_summary(work_dir)
    return {
        "total_checked": report["total_checked"],
        "confirmed_count": report["confirmed_count"],
        "ocr_error_count": report["ocr_error_count"],
        "by_kind": by_kind_summary,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
