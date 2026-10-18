"""Vision query expansion for pages without an accepted match.

Super VL reads the scan (downscaled JPEG) and the Parse running head and returns the page subject and
3 to 5 Wikipedia search phrases. BM25 runs on each phrase. The new hits join the page's earlier candidate
pool. Embed VL ranks the pool against a short page query, Rerank VL scores the top 16, and the usual accept
rules decide. Super VL only proposes search terms; it never writes source text or decides a match.

Writes match/vision_expand/<row>.json (Super VL reply, candidates, scores) and match/vision_failures.jsonl.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import re
import time
from typing import Any

from .clients import ChatClient, RetrievalClient, ServiceError, WikiClient
from .config import Settings
from .match import (SHORT_METHOD, TAU, TfIdf, _hit, _safe, call, decide, doc_text, rank, rerank_short, short_query)

METHOD = "vision_expand"
MAX_SIDE = 1600
RERANK_TOP = 16
PROMPT = """This is a scanned page of the Encyclopaedia Britannica (1771 to 1797).
The running head printed at the top, as read by OCR, is: "{head}".
Read the page. Name its main subject (the article this page belongs to), and give 3 to 5 short search phrases
that would find the matching modern English Wikipedia article(s). Use modern spelling and modern names.
If the page holds several short dictionary entries, give one phrase per main entry.
Answer with JSON only: {{"subject": "...", "phrases": ["...", "..."]}}"""


def scan_data_url(path: Path) -> tuple[str, dict[str, Any]]:
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        scale = min(1.0, MAX_SIDE / max(image.size))
        if scale < 1.0:
            image = image.resize((int(image.width * scale), int(image.height * scale)))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=85)
    data = buffer.getvalue()
    return "data:image/jpeg;base64," + base64.b64encode(data).decode(), {"jpeg_bytes": len(data), "size": image.size}


def parse_reply(content: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError("Super VL reply has no JSON object")
    data = json.loads(match[0])
    phrases = [p.strip() for p in data.get("phrases", []) if isinstance(p, str) and p.strip()]
    if not phrases:
        raise ValueError("Super VL reply has no search phrases")
    return {"subject": str(data.get("subject") or "").strip(), "phrases": phrases[:5]}


def ask_super(settings: Settings, page: dict[str, Any], head: str) -> dict[str, Any]:
    url, image_meta = scan_data_url(Path(page["scan_path"]))
    messages = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT.format(head=head or "none")},
        {"type": "image_url", "image_url": {"url": url}},
    ]}]
    started = time.time()
    with ChatClient(settings.super_base_url, settings.super_api_key, settings.super_model, timeout=240) as chat:
        reply = call(lambda: chat.complete(messages, max_tokens=600, extra_body={
            "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}), "super vl")
    content = reply["choices"][0]["message"]["content"]
    return {"model": reply.get("model"), "finish_reason": reply["choices"][0].get("finish_reason"),
            "usage": reply.get("usage"), "seconds": round(time.time() - started, 2), "image": image_meta,
            "content": content, "parsed": _parse_or_explain(content)}


def _parse_or_explain(content: str) -> dict[str, Any]:
    try:
        return parse_reply(content)
    except ValueError as exc:
        raise ValueError(f"{exc}; reply: {content[:300]!r}") from None


def _old_pool(mdir: Path, row: int, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    page_path = mdir / "pages" / f"{row}.json"
    if page_path.is_file():
        return [dict(h) for h in rank(json.loads(page_path.read_text()), SHORT_METHOD)]
    hits = []
    for e in sorted(items, key=lambda e: -e["chars"]):
        path = mdir / "candidates_short" / f"{_safe(e['entry_id'])}.json"
        if path.is_file():
            hits += [dict(h) for h in rank(json.loads(path.read_text()), SHORT_METHOD)]
    return hits


def expand_page(settings: Settings, work_dir: Path, page: dict[str, Any], items: list[dict[str, Any]],
                tfidf: TfIdf | None = None) -> dict[str, Any]:
    mdir = work_dir / "match"
    row = page["row_index"]
    head = items[0].get("running_head") or ""
    record: dict[str, Any] = {"entry_id": f"P:{row}", "row_index": row, "page_id": page["page_id"],
                              "image_sha256": page["image_sha256"], "running_head": head, "method": METHOD,
                              "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    record["super_vl"] = ask_super(settings, page, head)
    subject, phrases = record["super_vl"]["parsed"]["subject"], record["super_vl"]["parsed"]["phrases"]
    pool, seen = [], set()
    body = " ".join(e["text_norm"] for e in items)
    searches = list(phrases)
    if tfidf is not None:
        # Bare titles rank short pages first in BM25; one longer query reaches long main articles.
        words = re.findall(r"[A-Za-z]+", " ".join([subject] * 2 + phrases))
        searches.append(" ".join((words + tfidf.top_terms(body, 20))[:40]))
    record["searches"] = searches
    with WikiClient(settings.wikipedia_api_url) as wiki:
        for phrase in searches:
            result = call(lambda: wiki.search(re.sub(r"[^\w\s'-]", " ", phrase)[:500], top_k=10, excerpt_chars=1000),
                          "wiki.search vision")
            for h in result.hits:
                if h.page_id not in seen:
                    seen.add(h.page_id)
                    pool.append({**_hit(h, "vision"), "vision_phrase": phrase})
    record["vision_hits"] = len(pool)
    for h in _old_pool(mdir, row, items):
        if h["page_id"] not in seen:
            seen.add(h["page_id"])
            pool.append({k: v for k, v in h.items() if k not in {"rerank_logit", "embed_cos", "rerank_long_logit"}}
                        | {"source": h.get("source") or "page_pool"})
    query = short_query(subject, body)
    record.update(subject=subject, phrases=phrases, short_query=query)
    with RetrievalClient(settings.retrieval_base_url, settings.retrieval_api_key) as retr:
        qvec = call(lambda: retr.embed([query[:1200]], "query"), "embed vision query")[0]
        docs = [doc_text(h) for h in pool]
        vecs: list[list[float]] = []
        for i in range(0, len(docs), 16):
            batch = docs[i:i + 16]
            vecs += call(lambda: retr.embed(batch, "document"), "embed vision docs")
        for h, v in zip(pool, vecs):
            h["embed_cos"] = round(sum(a * b for a, b in zip(qvec, v)), 6)
        top = sorted(pool, key=lambda h: -h["embed_cos"])[:RERANK_TOP]
        rerank_short(retr, query, top)
    record["hits"] = pool
    record["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return record


def subject_head(subject: str) -> str:
    """'Swift, Jonathan' -> 'Jonathan Swift'; drop a bracketed note."""
    subject = re.sub(r"\s*\(.*?\)", "", subject).strip()
    parts = [p.strip() for p in subject.split(",")]
    return f"{parts[1]} {parts[0]}" if len(parts) == 2 and all(parts) and len(parts[1].split()) <= 2 else subject


def vision_decide(record: dict[str, Any], chars: int) -> dict[str, Any]:
    d = decide(record, TAU, {"headword": subject_head(record.get("subject") or ""), "chars": chars}, method=METHOD)
    d["entry_id"] = record["entry_id"]
    return d


def run_vision(settings: Settings, work_dir: Path, workers: int = 3) -> dict[str, Any]:
    """Expand every non-plate page whose page-level status is no_clear_counterpart. Resumable."""
    mdir = work_dir / "match"
    out_dir = mdir / "vision_expand"
    out_dir.mkdir(exist_ok=True)
    v1 = mdir / "page_matches_v1.jsonl"
    source = v1 if v1.is_file() else mdir / "page_matches.jsonl"
    pages_rows = [json.loads(l) for l in source.read_text().splitlines() if l.strip()]
    entries = [json.loads(l) for l in (work_dir / "extract" / "entries.jsonl").read_text().splitlines() if l.strip()]
    tfidf = TfIdf([e["text_norm"] for e in entries])
    by_page: dict[int, list[dict[str, Any]]] = {}
    for e in entries:
        by_page.setdefault(e["row_index"], []).append(e)
    todo = [p["row_index"] for p in pages_rows if p["status"] != "matched" and p["page_kind"] != "plate"
            and not (out_dir / f"{p['row_index']}.json").is_file()]

    def one(row: int) -> dict[str, Any]:
        page = json.loads((work_dir / "extract" / "pages" / f"{row}.json").read_text())
        try:
            record = expand_page(settings, work_dir, page, by_page[row], tfidf)
            (out_dir / f"{row}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1))
            return {"row_index": row, "status": "ok"}
        except (ServiceError, ValueError, OSError) as exc:
            return {"row_index": row, "status": "error", "error": f"{type(exc).__name__}: {exc}",
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(one, todo))
    failures = [r for r in results if r["status"] == "error"]
    if failures:
        with (mdir / "vision_failures.jsonl").open("a") as f:
            for r in failures:
                f.write(json.dumps(r) + "\n")
    return {"todo": len(todo), "ok": len(results) - len(failures), "errors": len(failures)}


def apply_vision(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """page_matches_v1.jsonl + vision_expand records -> page_matches.jsonl. Only article fetches call services."""
    from .match import TfIdf, _art_ref, _article, explain

    mdir = work_dir / "match"
    rows = [json.loads(l) for l in (mdir / "page_matches_v1.jsonl").read_text().splitlines() if l.strip()]
    entries = [json.loads(l) for l in (work_dir / "extract" / "entries.jsonl").read_text().splitlines() if l.strip()]
    tfidf = TfIdf([e["text_norm"] for e in entries])
    failures = {}
    if (mdir / "vision_failures.jsonl").is_file():
        for line in (mdir / "vision_failures.jsonl").read_text().splitlines():
            r = json.loads(line)
            failures[r["row_index"]] = r["error"]
    errors: list[dict[str, Any]] = []
    tried = accepted = 0
    with WikiClient(settings.wikipedia_api_url) as wiki:
        for row in rows:
            path = mdir / "vision_expand" / f"{row['row_index']}.json"
            if row["status"] == "matched" or row["page_kind"] == "plate":
                continue
            if not path.is_file():
                if row["row_index"] in failures:
                    row["reason"] = f"{row.get('reason', '')}; vision_expand failed: {failures[row['row_index']]}"
                    row["why"] = (row.get("why") or "") + f" Vision expansion gave no search phrases ({failures[row['row_index']][-80:]})."
                continue
            tried += 1
            record = json.loads(path.read_text())
            chars = sum(e["chars"] for e in entries if e["row_index"] == row["row_index"])
            d = vision_decide(record, chars)
            head_entry = {"headword": subject_head(record["subject"]), "chars": chars, "is_continuation": False,
                          "text_norm": " ".join(e["text_norm"] for e in entries if e["row_index"] == row["row_index"])}
            text = _article(mdir / "articles", wiki, d, errors) if d["status"] == "matched" else None
            explain(d, record, head_entry, tfidf, text, TAU)
            prefix = f"Super VL subject '{record['subject']}', phrases {record['phrases']}. "
            row["vision_expand"] = {"subject": record["subject"], "phrases": record["phrases"],
                                    "status": d["status"], "best": d["wiki_title"], "rerank_logit": d["rerank_logit"],
                                    "rerank_margin": d["rerank_margin"], "reason": d["reason"]}
            if d["status"] == "matched":
                accepted += 1
                row.update({k: v for k, v in d.items() if k not in {"entry_id"}})
                row["why"] = prefix + d["why"]
                row["articles"] = [_art_ref(d, "vision_expand")]
            else:
                row["reason"] = f"{row.get('reason', '')}; vision_expand rejected: {d['reason']}"
                row["why"] = (row.get("why") or "") + " Vision expansion: " + prefix + d["why"]
    with (mdir / "page_matches.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    before = sum(1 for l in (mdir / "page_matches_v1.jsonl").read_text().splitlines() if json.loads(l)["status"] == "matched")
    after = sum(r["status"] == "matched" for r in rows)
    report = {"pages_tried": tried, "pages_failed": len(failures), "pages_accepted": accepted,
              "pages_matched_before": before, "pages_matched_after": after, "article_errors": len(errors),
              "recall": vision_recall(work_dir)}
    (mdir / "vision_summary.json").write_text(json.dumps(report, indent=1))
    cov_path = work_dir / "extract" / "coverage.json"
    cov = json.loads(cov_path.read_text())
    cov.setdefault("match_coverage", {})["vision_expand"] = {k: v for k, v in report.items() if k != "recall"}
    cov["match_coverage"]["pages_matched_final"] = after
    cov_path.write_text(json.dumps(cov, ensure_ascii=False, indent=1))
    return report


def vision_recall(work_dir: Path) -> dict[str, Any]:
    """On labeled entries whose page was expanded: does the gold article enter the pool / top 10 more often?"""
    mdir = work_dir / "match"
    labels_path = mdir / "labels.jsonl"
    if not labels_path.is_file():
        return {}
    items = []
    for l in map(json.loads, labels_path.read_text().splitlines()):
        row = int(l["entry_id"].split(":")[1])
        path = mdir / "vision_expand" / f"{row}.json"
        if not l["has_counterpart"] or not path.is_file():
            continue
        record = json.loads(path.read_text())
        gold_titles = set(l["gold_titles"])
        old_path = mdir / "candidates_short" / f"{_safe(l['entry_id'])}.json"
        old = rank(json.loads(old_path.read_text()), SHORT_METHOD) if old_path.is_file() else []
        long_path = mdir / "candidates" / f"{_safe(l['entry_id'])}.json"
        old_pool = old + (json.loads(long_path.read_text())["hits"] if long_path.is_file() else [])
        new = rank(record, SHORT_METHOD)
        items.append({"entry_id": l["entry_id"], "gold": l["gold_titles"],
                      "in_pool_before": any(h["title"] in gold_titles for h in old_pool),
                      "in_pool_after": any(h["title"] in gold_titles for h in record["hits"]),
                      "top10_before": any(h["title"] in gold_titles for h in old[:10]),
                      "top10_after": any(h["title"] in gold_titles for h in new[:10]),
                      "top1_after": bool(new) and new[0]["title"] in gold_titles})
    n = len(items)
    count = lambda k: sum(i[k] for i in items)
    return {"labeled_positives_on_expanded_pages": n,
            "gold_in_pool_before": count("in_pool_before"), "gold_in_pool_after": count("in_pool_after"),
            "recall_at_10_before": count("top10_before"), "recall_at_10_after": count("top10_after"),
            "top1_after": count("top1_after"), "items": items}
