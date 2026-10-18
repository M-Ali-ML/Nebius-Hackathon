"""Multimodal atlas: scan images, plate crops, Britannica entries and Wikipedia chunks in one Embed VL space.

Stage 1 (embed): embed the 100 scan images and the Picture-block crops as image documents
  (input_type=document). Text vectors are reused from match/vectors/ (also input_type=document),
  so every distance on the map compares a document with a document.
Stage 2 (project): UMAP to 2D and 3D (cosine, fixed seed), edges, nearest-neighbour agreement numbers.
Stage 3 (page): site/atlas.html, a self-contained canvas page with the points inlined.

Files: artifacts/atlas/{vectors.npz, ids.json, failures.jsonl, points.json, summary.json, thumbs/}.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np

from .clients import RetrievalClient, ServiceError
from .config import EMBED_DIMENSIONS, EMBED_MODEL, EMBED_REVISION, Settings
from .match import call

MAX_SIDE = 1024          # the scans are about 600 x 760, so this keeps them at full size
MIN_CROP_PX = 48         # Picture boxes smaller than this are ornaments, not plates
THUMB_SIDE = 96


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _data_url(image) -> str:
    image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def _scan(root: Path, record: dict[str, Any]) -> Path:
    path = Path(record["scan_path"])
    return path if path.is_absolute() else root / path


def image_items(work: Path, root: Path) -> list[dict[str, Any]]:
    """One item per scan image and per Picture crop, with provenance. No network."""
    from PIL import Image

    thumbs = work / "atlas" / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    items = []
    for page in sorted((work / "extract" / "pages").glob("*.json"), key=lambda p: int(p.stem)):
        record = json.loads(page.read_text())
        row, scan = record["row_index"], _scan(root, record)
        with Image.open(scan) as image:
            image = image.convert("RGB")
            thumb = image.copy()
            thumb.thumbnail((THUMB_SIDE, THUMB_SIDE))
            thumb.save(thumbs / f"scan_{row}.jpg", "JPEG", quality=80)
            items.append({"id": f"S:{row}", "kind": "scan_image", "row": row, "page_id": record["page_id"],
                          "image_sha256": record["image_sha256"], "thumb": f"thumbs/scan_{row}.jpg",
                          "data_url": _data_url(image)})
            w, h = image.size
            for block in record["blocks"]:
                if block["cls"] != "Picture":
                    continue
                x1, y1, x2, y2 = block["bbox"]
                box = (int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h))
                if box[2] - box[0] < MIN_CROP_PX or box[3] - box[1] < MIN_CROP_PX:
                    continue
                crop = image.crop(box)
                key = f"crop_{row}_{block['order']}"
                small = crop.copy()
                small.thumbnail((THUMB_SIDE, THUMB_SIDE))
                small.save(thumbs / f"{key}.jpg", "JPEG", quality=80)
                items.append({"id": f"C:{row}:{block['order']}", "kind": "plate_crop", "row": row,
                              "page_id": record["page_id"], "image_sha256": record["image_sha256"],
                              "bbox": block["bbox"], "caption": block["text"][:200], "thumb": f"thumbs/{key}.jpg",
                              "data_url": _data_url(crop)})
    return items


def embed(settings: Settings, work: Path, root: Path) -> dict[str, Any]:
    """Embed scan images and crops as image documents. Resumable: cached ids are skipped."""
    out = work / "atlas"
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "image_vectors.jsonl"
    done = {row["id"] for row in _jsonl(cache)}
    items = [it for it in image_items(work, root) if it["id"] not in done]
    retr = RetrievalClient(settings.retrieval_base_url, settings.retrieval_api_key, timeout=300)
    failures = 0
    with cache.open("a") as fh, (out / "failures.jsonl").open("a") as fail:
        for it in items:
            try:
                vec = call(lambda: retr.embed([{"image": it["data_url"]}], "document"), f"embed {it['id']}")[0]
            except (ServiceError, ValueError) as exc:
                failures += 1
                fail.write(json.dumps({"id": it["id"], "error": str(exc), "status_code": getattr(exc, "status_code", None),
                                       "time": dt.datetime.now().isoformat(timespec="seconds")}) + "\n")
                continue
            meta = {k: v for k, v in it.items() if k != "data_url"}
            meta["input_sha256"] = hashlib.sha256(it["data_url"].encode()).hexdigest()
            fh.write(json.dumps({**meta, "vector": vec}) + "\n")
            fh.flush()
    retr.close()
    return {"embedded": len(items) - failures, "cached": len(done), "failures": failures}


def embed_plate_articles(settings: Settings, work: Path) -> dict[str, Any]:
    """Fetch and embed (document) the chunks of matched plate articles that match/vectors/ lacks."""
    from .clients import WikiClient
    from .index import chunk_text

    out = work / "atlas"
    have = {r["id"].split(":")[1] for r in _jsonl(work / "match/vectors/wiki_chunks.jsonl")}
    cache = out / "plate_article_vectors.jsonl"
    done = {r["id"] for r in _jsonl(cache)}
    added = 0
    with WikiClient(settings.wikipedia_api_url) as wiki, \
            RetrievalClient(settings.retrieval_base_url, settings.retrieval_api_key, timeout=300) as retr, cache.open("a") as fh:
        for path in sorted((work / "plates").glob("*.json")):
            plate = json.loads(path.read_text())
            page = plate.get("wiki_page_id")
            if plate.get("status") != "matched" or page in have:
                continue
            art = wiki.article(page, max_chars=20000)
            rev_ok = str(art.revision_id) == str(plate["wiki_revision_id"])
            (out / "articles").mkdir(exist_ok=True)
            (out / "articles" / f"{page}.json").write_text(json.dumps(art.model_dump(mode="json"), ensure_ascii=False))
            for n, (_, text) in enumerate(chunk_text(art.text)):
                cid = f"W:{page}:{art.revision_id}:{n}"
                if cid in done:
                    continue
                vec = call(lambda: retr.embed([f"{art.title}\n{text}"], "document"), f"embed {cid}")[0]
                fh.write(json.dumps({"id": cid, "title": art.title, "text": text, "revision_matches_plate": rev_ok,
                                     "text_sha256": art.provenance.text_sha256, "vector": vec}) + "\n")
                added += 1
    return {"plate_article_chunks": added}


def pack_vectors(work: Path) -> dict[str, Any]:
    """Write atlas/vectors.npz and atlas/ids.json from the image cache and match/vectors/."""
    out = work / "atlas"
    rows = [{"id": r["id"], "kind": r["kind"], "vector": r["vector"]} for r in _jsonl(out / "image_vectors.jsonl")]
    rows += [{"id": r["id"], "kind": "britannica_entry", "vector": r["vector"]} for r in _jsonl(work / "match/vectors/entries.jsonl")]
    rows += [{"id": r["id"], "kind": "wikipedia_chunk", "vector": r["vector"]} for r in _jsonl(work / "match/vectors/wiki_chunks.jsonl")]
    rows += [{"id": r["id"], "kind": "wikipedia_chunk", "vector": r["vector"]} for r in _jsonl(out / "plate_article_vectors.jsonl")]
    seen, unique = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"])
            unique.append(r)
    matrix = np.asarray([r["vector"] for r in unique], dtype=np.float32)
    assert matrix.shape[1] == EMBED_DIMENSIONS
    np.savez_compressed(out / "vectors.npz", vectors=matrix)
    meta = {"model": EMBED_MODEL, "model_revision": EMBED_REVISION, "dimensions": EMBED_DIMENSIONS,
            "input_type": "document (all kinds)", "created": dt.datetime.now().isoformat(timespec="seconds"),
            "ids": [r["id"] for r in unique], "kinds": [r["kind"] for r in unique]}
    (out / "ids.json").write_text(json.dumps(meta))
    return {"vectors": len(unique)}


DRIFT_TAGS = ("enduring", "renamed", "superseded", "dropped")
SEED = 20261018


def _read(path: Path) -> Any:
    return json.loads(path.read_text()) if path.is_file() else None


def _unit(matrix: np.ndarray) -> np.ndarray:
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def agreement(ids: list[str], kinds: list[str], vectors: np.ndarray, matched: dict[str, str]) -> dict[str, Any]:
    """Nearest-neighbour checks in the full 2048-d space (cosine, document vs document).

    entry_to_wiki: share of matched entries whose nearest Wikipedia chunk belongs to the matched article.
    scan_to_text: share of scan images whose nearest text point (entry or chunk) is one of its own entries.
    scan_to_entry: same, nearest Britannica entry only. Chance level = mean entries per page / all entries.
    """
    unit = _unit(vectors)
    kinds_a = np.asarray(kinds)
    wiki = np.where(kinds_a == "wikipedia_chunk")[0]
    ents = np.where(kinds_a == "britannica_entry")[0]
    text = np.concatenate([ents, wiki])
    scans = np.where(kinds_a == "scan_image")[0]
    index = {i: n for n, i in enumerate(ids)}
    hits = []
    for eid, page in matched.items():
        if eid not in index:
            continue
        sims = unit[wiki] @ unit[index[eid]]
        hits.append(ids[wiki[int(np.argmax(sims))]].split(":")[1] == page)
    by_row: dict[str, int] = {}
    for i in ents:
        by_row[ids[i].split(":")[1]] = by_row.get(ids[i].split(":")[1], 0) + 1
    t_hits, e_hits, ranks, chance = [], [], [], []
    for i in scans:
        row = ids[i].split(":")[1]
        if row not in by_row:
            continue
        sims_t = unit[text] @ unit[i]
        sims_e = unit[ents] @ unit[i]
        nearest_t = ids[text[int(np.argmax(sims_t))]]
        t_hits.append(nearest_t.startswith(f"B:{row}:"))
        e_hits.append(ids[ents[int(np.argmax(sims_e))]].startswith(f"B:{row}:"))
        order = [ids[ents[j]] for j in np.argsort(-sims_e)]
        ranks.append(next(r for r, x in enumerate(order, 1) if x.startswith(f"B:{row}:")))
        chance.append(by_row[row] / len(ents))
    mean = lambda xs: round(float(np.mean(xs)), 4) if xs else None
    return {"entry_to_wiki": {"n": len(hits), "share": mean(hits)},
            "scan_to_text": {"n": len(t_hits), "share": mean(t_hits)},
            "scan_to_entry": {"n": len(e_hits), "share": mean(e_hits), "chance": mean(chance),
                              "median_rank_of_own_entry": float(np.median(ranks)) if ranks else None,
                              "top5_share": mean([r <= 5 for r in ranks]), "entries": len(ents)}}


def project(work: Path) -> dict[str, Any]:
    """UMAP 2D, labels, edges and agreement numbers. Writes atlas/points.json and atlas/summary.json."""
    import umap

    from .index import chunk_text

    out = work / "atlas"
    meta = json.loads((out / "ids.json").read_text())
    ids, kinds = meta["ids"], meta["kinds"]
    vectors = np.load(out / "vectors.npz")["vectors"]
    reducer = umap.UMAP(n_components=2, metric="cosine", n_neighbors=15, min_dist=0.12, random_state=SEED)
    xy = reducer.fit_transform(vectors)
    xy = (xy - xy.mean(0)) / xy.std(0)

    images = {r["id"]: r for r in _jsonl(out / "image_vectors.jsonl")}
    entries = {e["entry_id"]: e for e in _jsonl(work / "extract/entries.jsonl")}
    matches = {m["entry_id"]: m for m in _jsonl(work / "match/matches.jsonl")}
    pages = {str(m["row_index"]): m for m in _jsonl(work / "match/page_matches.jsonl")}
    articles = {p.stem: json.loads(p.read_text()) for p in (work / "match/articles").glob("*.json")}
    for p in (out / "articles").glob("*.json"):
        art = json.loads(p.read_text())
        articles.setdefault(p.stem, {"title": art["title"], "revision_id": art["revision_id"], "text": art["text"]})
    topics = _read(work / "compare/topics.json") or {}
    cluster = {p["id"]: p.get("cluster_id") for p in topics.get("points", [])}
    cluster_labels = {str(c["cluster_id"]): c.get("super_label") or c.get("short_tag") for c in topics.get("clusters", [])}
    chunks = {}
    for pid, art in articles.items():
        for n, (offset, text) in enumerate(chunk_text(art["text"])):
            chunks[f"W:{pid}:{art['revision_id']}:{n}"] = text
    matched = {e: m["wiki_page_id"] for e, m in matches.items() if m.get("status") == "matched"}

    points = []
    for n, (pid, kind) in enumerate(zip(ids, kinds)):
        p: dict[str, Any] = {"id": pid, "kind": kind, "x": round(float(xy[n, 0]), 4), "y": round(float(xy[n, 1]), 4)}
        if kind in {"scan_image", "plate_crop"}:
            img = images[pid]
            row = str(img["row"])
            heads = [e["headword"] for e in entries.values() if str(e["row_index"]) == row and e.get("headword")]
            pm = pages.get(row, {})
            p.update(row=img["row"], page_id=img["page_id"], thumb=img["thumb"],
                     label=(img.get("caption") or "").strip() or (", ".join(heads[:3]) or entries.get(f"B:{row}:0", {}).get("running_head") or f"Page {row}"),
                     status=pm.get("status"), wiki_title=pm.get("wiki_title"), wiki_page_id=pm.get("wiki_page_id"),
                     wiki_revision_id=pm.get("wiki_revision_id"))
            plate = _read(work / "plates" / f"{row}.json")
            if plate and plate.get("status") == "matched":
                p.update(status="matched", wiki_title=plate["wiki_title"], wiki_page_id=plate["wiki_page_id"],
                         wiki_revision_id=plate["wiki_revision_id"], plate_match=True, rerank_logit=plate.get("rerank_logit"))
        elif kind == "britannica_entry":
            e, m = entries.get(pid, {}), matches.get(pid, {})
            pair = _read(work / "compare/pairs" / f"{pid.replace(':', '_')}.json")
            counts = ((pair or {}).get("drift") or {}).get("claim_counts")
            total = sum(counts.values()) if counts else 0
            p.update(row=e.get("row_index"), page_id=e.get("page_id"),
                     label=e.get("headword") or f"{e.get('running_head') or 'continuation'} (cont.)",
                     excerpt=(e.get("text_norm") or "")[:220], status=m.get("status"),
                     wiki_title=m.get("wiki_title"), wiki_page_id=m.get("wiki_page_id"),
                     wiki_revision_id=m.get("wiki_revision_id"), rerank_logit=m.get("rerank_logit"),
                     embed_cos=m.get("embed_cos"), cluster=cluster.get(pid),
                     drift={t: round(counts[t] / total, 3) for t in DRIFT_TAGS} if total else None)
        else:
            _, page, rev, k = pid.split(":")
            art = articles.get(page, {})
            p.update(wiki_page_id=page, wiki_revision_id=rev, chunk=int(k), label=art.get("title", page),
                     excerpt=chunks.get(pid, "")[:220], cluster=cluster.get(f"W:{page}"))
        points.append(p)

    # edges: entry -> nearest chunk of its matched article; image -> entries on its page; crop -> plate match
    unit = _unit(vectors)
    index = {i: n for n, i in enumerate(ids)}
    by_page: dict[str, list[int]] = {}
    for n, pid in enumerate(ids):
        if kinds[n] == "wikipedia_chunk":
            by_page.setdefault(pid.split(":")[1], []).append(n)

    def nearest_chunk(n: int, page: str | None) -> int | None:
        cands = by_page.get(str(page), [])
        return max(cands, key=lambda c: float(unit[c] @ unit[n])) if cands else None

    edges = []
    for n, p in enumerate(points):
        if p["kind"] == "britannica_entry" and p.get("wiki_page_id") and p.get("status") in {"matched", "no_clear_counterpart"}:
            c = nearest_chunk(n, p["wiki_page_id"])
            if c is not None:
                dom = max(p["drift"], key=p["drift"].get) if p.get("drift") else None
                edges.append({"a": n, "b": c, "type": "entry_wiki", "status": p["status"], "drift": dom})
        elif p["kind"] == "scan_image":
            for eid in [i for i in ids if i.startswith(f"B:{p['row']}:")]:
                edges.append({"a": n, "b": index[eid], "type": "scan_entry", "status": "own_page"})
        elif p["kind"] == "plate_crop" and p.get("plate_match"):
            c = nearest_chunk(n, p["wiki_page_id"])
            if c is not None:
                edges.append({"a": n, "b": c, "type": "plate_wiki", "status": "matched"})

    stats = agreement(ids, kinds, vectors, matched)
    summary = {"model": meta["model"], "model_revision": meta["model_revision"], "dimensions": meta["dimensions"],
               "input_type": meta["input_type"], "umap": {"metric": "cosine", "n_neighbors": 15, "min_dist": 0.12, "seed": SEED},
               "counts": {k: kinds.count(k) for k in sorted(set(kinds))}, "edges": len(edges),
               "clusters_from": "compare/topics.json" if topics else None, "agreement": stats,
               "created": dt.datetime.now().isoformat(timespec="seconds")}
    (out / "points.json").write_text(json.dumps({"points": points, "edges": edges, "clusters": cluster_labels}))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary
