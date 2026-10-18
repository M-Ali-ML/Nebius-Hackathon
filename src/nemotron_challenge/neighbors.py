"""Neighbor pages of a scan from the full source Parquet, with Parse 3.5 text for context.

The source Parquet has 2,573 rows. Rows of one volume are contiguous (column `id` is the volume id).
Each volume holds only a few scanned pages (about 13), so a neighbor row is the next scan in the
dataset, not always the next printed page. See runs/worker-site.md "Plates" for the order check.

Layout under the work dir:
  plates/neighbors/<row>/<neighbor_row>.jpg    neighbor scan (source bytes, unchanged)
  plates/neighbors/<row>/raw/<neighbor_row>.json  full Parse reply (never rewritten once valid)
  plates/neighbors/<row>/<neighbor_row>.blocks.json  parsed blocks
"""
from __future__ import annotations

import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from .clients import ParseClient, ServiceError
from .config import Settings
from .data import DATASET, REVISION, load_manifest
from .extract import parse_blocks

PARQUET_GLOB = "datasets--NationalLibraryOfScotland--encyclopaedia_britannica_illustrated/snapshots/*/data/*.parquet"


def parquet_path(cache_dir: Path) -> Path:
    manifest = load_manifest()
    hits = sorted(cache_dir.glob(PARQUET_GLOB.replace("*/data", f"{REVISION}/data")))
    hits = [h for h in hits if h.name == Path(manifest["source_file"]).name] or hits
    if not hits:
        raise FileNotFoundError(f"source Parquet not found under {cache_dir}; run `nemotron-challenge data fetch`")
    return hits[0]


@lru_cache(maxsize=2)
def _table(path: str):
    import pyarrow.parquet as pq

    return pq.read_table(path, columns=["image", "id", "label", "meta"])


def source_row(cache_dir: Path, row: int) -> dict[str, Any]:
    table = _table(str(parquet_path(cache_dir)))
    item = table.slice(row, 1).to_pylist()[0]
    data = item["image"]["bytes"]
    return {"row_index": row, "volume_id": str(item["id"]), "label": item["label"], "meta": item["meta"],
            "image_bytes": data, "image_sha256": hashlib.sha256(data).hexdigest(),
            "page_id": f"britannica:{REVISION}:train:{row}", "dataset": DATASET}


def neighbor_rows(cache_dir: Path, row: int, before: int = 2, after: int = 2) -> list[int]:
    """Rows next to `row` that belong to the same volume."""
    table = _table(str(parquet_path(cache_dir)))
    ids = table.column("id")
    volume = str(ids[row].as_py())
    rows = []
    for other in range(row - before, row + after + 1):
        if other != row and 0 <= other < table.num_rows and str(ids[other].as_py()) == volume:
            rows.append(other)
    return rows


def get_neighbors(row_index: int, before: int = 2, after: int = 2, *, work_dir: Path,
                  cache_dir: Path) -> list[dict[str, Any]]:
    """Save the adjacent scans of the same volume and return their records (without image bytes)."""
    out_dir = work_dir / "plates" / "neighbors" / str(row_index)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for other in neighbor_rows(cache_dir, row_index, before, after):
        item = source_row(cache_dir, other)
        path = out_dir / f"{other}.jpg"
        if not path.is_file():
            path.write_bytes(item.pop("image_bytes"))
        else:
            item.pop("image_bytes")
        records.append({**item, "offset": other - row_index, "image_path": str(path)})
    return records


def parse_neighbor(settings: Settings, neighbor: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Parse one neighbor scan. Keep the raw reply; log the error and return no blocks on failure."""
    raw_path = out_dir / "raw" / f"{neighbor['row_index']}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if not raw_path.is_file():
        image = Path(neighbor["image_path"])
        mime = "png" if image.suffix == ".png" else "jpeg"
        url = f"data:image/{mime};base64," + base64.b64encode(image.read_bytes()).decode()
        last_error = ""
        for attempt, max_tokens in enumerate((8744, 15500, 15500)):
            try:
                started = time.time()
                with ParseClient(settings.parse_base_url, settings.parse_api_key) as client:
                    reply = client.parse(url, max_tokens=max_tokens)
                reply["_run"] = {"seconds": round(time.time() - started, 2), "attempt": attempt,
                                 "max_tokens": max_tokens, "page_id": neighbor["page_id"],
                                 "image_sha256": neighbor["image_sha256"]}
                raw_path.write_text(json.dumps(reply, ensure_ascii=False, indent=1))
                break
            except (ServiceError, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(2 ** attempt)
        else:
            with (out_dir / "failures.jsonl").open("a") as log:
                log.write(json.dumps({"row_index": neighbor["row_index"], "error": last_error,
                                      "at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            return {**neighbor, "parse_status": "failed", "parse_error": last_error, "blocks": []}
    reply = json.loads(raw_path.read_text())
    blocks = parse_blocks(reply["choices"][0]["message"]["content"])
    (out_dir / f"{neighbor['row_index']}.blocks.json").write_text(json.dumps(blocks, ensure_ascii=False, indent=1))
    return {**neighbor, "parse_status": "ok", "parse_model": reply.get("model"),
            "finish_reason": reply["choices"][0].get("finish_reason"), "blocks": blocks}


def page_text(blocks: list[dict[str, Any]], limit: int = 6000) -> str:
    text = "\n".join(b["text"] for b in sorted(blocks, key=lambda b: b["order"]) if b["text"].strip())
    return text[:limit]


def running_head(blocks: list[dict[str, Any]]) -> str:
    heads = [b["text"] for b in blocks if b["cls"] == "Page-header" or (b["bbox"][3] < 0.07 and len(b["text"]) <= 30)]
    return " / ".join(h.replace("\n", " ") for h in heads)[:100]
