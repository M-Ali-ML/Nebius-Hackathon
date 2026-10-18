"""Run Parse 3.5 on the shared scans and turn its output into page records.

Layout under the work dir:
  extract/raw/<row>.json     full Parse response, never rewritten once valid
  extract/pages/<row>.json   page record: scan identity + ordered blocks
  extract/failures.jsonl     failed Parse calls with error details
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import time
from typing import Any

from .clients import ParseClient, ServiceError
from .config import Settings
from .data import load_manifest

BLOCK = re.compile(
    r"<x_(?P<x1>[\d.]+)><y_(?P<y1>[\d.]+)>(?P<text>.*?)<x_(?P<x2>[\d.]+)><y_(?P<y2>[\d.]+)><class_(?P<cls>[^>]+)>",
    re.S,
)
MIME = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png"}


def parse_blocks(content: str) -> list[dict[str, Any]]:
    """Split Parse markup into blocks in model reading order. Coordinates are page fractions."""
    blocks = []
    for order, match in enumerate(BLOCK.finditer(content)):
        blocks.append({
            "order": order,
            "cls": match["cls"],
            "bbox": [float(match[k]) for k in ("x1", "y1", "x2", "y2")],
            "text": match["text"].strip(),
        })
    return blocks


def _parse_one(settings: Settings, page: dict[str, Any], scan_dir: Path, raw_dir: Path) -> dict[str, Any]:
    raw_path = raw_dir / f"{page['row_index']}.json"
    if raw_path.is_file():
        return {"row_index": page["row_index"], "status": "cached"}
    image = scan_dir / page["filename"]
    url = f"data:image/{MIME[image.suffix]};base64," + base64.b64encode(image.read_bytes()).decode()
    last_error = ""
    # Dense two-column pages can exceed the default output budget; the served context is 16,384 tokens.
    for attempt, max_tokens in enumerate((8744, 15500, 15500, 15500)):
        try:
            started = time.time()
            with ParseClient(settings.parse_base_url, settings.parse_api_key) as client:
                reply = client.parse(url, max_tokens=max_tokens)
            reply["_run"] = {"seconds": round(time.time() - started, 2), "attempt": attempt, "max_tokens": max_tokens,
                             "page_id": page["page_id"], "image_sha256": page["image_sha256"]}
            raw_path.write_text(json.dumps(reply, ensure_ascii=False, indent=1))
            return {"row_index": page["row_index"], "status": "parsed"}
        except (ServiceError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(2 ** attempt)
    try:
        reply = _parse_columns(settings, image)
        reply["_run"].update({"page_id": page["page_id"], "image_sha256": page["image_sha256"],
                              "full_page_error": last_error})
        raw_path.write_text(json.dumps(reply, ensure_ascii=False, indent=1))
        return {"row_index": page["row_index"], "status": "parsed_column_split", "error": last_error}
    except (ServiceError, ValueError) as exc:
        last_error += f" | column split: {type(exc).__name__}: {exc}"
    return {"row_index": page["row_index"], "status": "failed", "error": last_error}


def _parse_columns(settings: Settings, image: Path) -> dict[str, Any]:
    """Fallback for pages whose full-page output loops past the token limit: parse each half.

    Coordinates from each half are mapped back to full-page fractions so page records stay comparable.
    """
    import io
    from PIL import Image

    parts, contents = [], []
    with Image.open(image) as full:
        width, height = full.size
        for x0, x1 in ((0.0, 0.5), (0.5, 1.0)):
            buffer = io.BytesIO()
            full.crop((int(x0 * width), 0, int(x1 * width), height)).convert("RGB").save(buffer, "JPEG", quality=92)
            url = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
            with ParseClient(settings.parse_base_url, settings.parse_api_key) as client:
                reply = client.parse(url, max_tokens=15500)
            parts.append(reply)
            content = reply["choices"][0]["message"]["content"]
            contents.append(re.sub(r"<x_([\d.]+)>", lambda m: f"<x_{x0 + float(m[1]) * (x1 - x0):.4f}>", content))
    merged = dict(parts[0])
    merged["choices"] = [{**parts[0]["choices"][0], "message": {"role": "assistant", "content": "\n\n".join(contents)}}]
    merged["usage"] = {key: sum((p.get("usage") or {}).get(key) or 0 for p in parts)
                       for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    merged["_run"] = {"strategy": "column_split", "parts": parts}
    return merged


def run_parse(settings: Settings, work_dir: Path, scan_dir: Path, workers: int = 4) -> dict[str, Any]:
    manifest = load_manifest()
    raw_dir = work_dir / "extract" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(lambda p: _parse_one(settings, p, scan_dir, raw_dir), manifest["pages"]))
    failures = [r for r in results if r["status"] == "failed"]
    with (work_dir / "extract" / "failures.jsonl").open("a") as log:
        for failure in failures:
            log.write(json.dumps({**failure, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
    return {status: sum(r["status"] == status for r in results) for status in ("parsed", "parsed_column_split", "cached", "failed")}


def build_pages(work_dir: Path, scan_dir: Path) -> dict[str, Any]:
    from PIL import Image

    manifest = load_manifest()
    pages_dir = work_dir / "extract" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    built, blank, missing = 0, [], []
    for page in manifest["pages"]:
        raw_path = work_dir / "extract" / "raw" / f"{page['row_index']}.json"
        if not raw_path.is_file():
            missing.append(page["row_index"])
            continue
        reply = json.loads(raw_path.read_text())
        choice = reply["choices"][0]
        blocks = parse_blocks(choice["message"]["content"])
        with Image.open(scan_dir / page["filename"]) as image:
            width, height = image.size
        record = {
            **page,
            "scan_path": str(scan_dir / page["filename"]),
            "width": width, "height": height,
            "parse_model": reply.get("model"), "finish_reason": choice.get("finish_reason"),
            "usage": reply.get("usage"),
            "blocks": blocks,
        }
        if not any(b["cls"] not in {"Page-header", "Page-footer"} and b["text"] for b in blocks):
            blank.append(page["row_index"])
        (pages_dir / f"{page['row_index']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1))
        built += 1
    return {"pages_built": built, "blank_or_no_body": blank, "missing_raw": missing}
