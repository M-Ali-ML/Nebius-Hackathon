"""Match Britannica entries to Wikipedia articles: BM25 -> embed -> rerank.

Reads  extract/entries.jsonl
Writes match/candidates/<entry_id>.json  all scores at every stage (resumable: existing files are skipped)
       match/matches.jsonl              one decision per processed entry
       match/articles/<page_id>.json    full article text, checksum verified
       match/ablation.jsonl             top-1 per method, computed from saved candidates
       match/failures.jsonl             failed entries with error details
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Any, Callable

from .clients import RetrievalClient, ServiceError, WikiClient
from .config import Settings

# Decision thresholds on raw rerank logits, set from the logit distribution and a 15-pair hand check
# (runs/match-threshold-check.md). Logits are low for long OCR queries, so a margin rule and an exact-title
# rule accept clear matches below TAU.
TAU = -4.0          # accept any candidate above this logit
TAU_MARGIN = -8.0   # entries with a headword: accept above this logit if margin >= MIN_MARGIN
MIN_MARGIN = 1.2
TAU_EXACT = -9.0    # entries with a headword: accept above this logit if the title equals the headword
MIN_CHARS = 40      # shorter entries (bare captions, fragments) are not judged
CAP_PER_PAGE = None  # 262 entries in total, so all are processed; set 3 for the MVP cap
BM25_K, EMBED_KEEP = 30, 10
QUERY_CHARS = 2000
METHODS = ("bm25", "bm25+embed", "bm25+embed+rerank")
STOP = set("""a an and are as at be but by for from had has have he her his i if in into is it its no not of on or
so such than that the their them then there these they this to was were which who will with see also may one
two three all any been being can more most other some upon our we you your what when where while would should
could do does did very only same same each those our out over under up after before between both how""".split())


def call(fn: Callable[[], Any], what: str, attempts: int = 6) -> Any:
    """Retry 429/503 and connection errors with Retry-After backoff. Other errors raise at once."""
    for attempt in range(attempts):
        try:
            return fn()
        except ServiceError as exc:
            transient = exc.status_code in {429, 502, 503, 504} or exc.status_code is None
            if not transient or attempt == attempts - 1:
                raise ServiceError(f"{what}: {exc}", status_code=exc.status_code) from exc
            try:
                wait = float(exc.retry_after) if exc.retry_after else 2 ** attempt
            except ValueError:
                wait = 2 ** attempt
            time.sleep(min(wait, 30))
    raise AssertionError("unreachable")


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP]


class TfIdf:
    def __init__(self, texts: list[str]):
        self.n = len(texts)
        self.df = Counter(w for t in texts for w in set(tokens(t)))

    def top_terms(self, text: str, k: int) -> list[str]:
        tf = Counter(tokens(text))
        score = {w: c * math.log((1 + self.n) / (1 + self.df[w])) for w, c in tf.items()}
        return sorted(score, key=lambda w: (-score[w], w))[:k]


def head_of(entry: dict[str, Any]) -> str:
    """Headword, or for a continuation the running-head topic (e.g. "BLOW-PIPE")."""
    return entry.get("headword") or (entry.get("topic_hint") if entry.get("is_continuation") else None) or ""


def bm25_query(entry: dict[str, Any], tfidf: TfIdf) -> str:
    head = re.sub(r"[^A-Za-z ]", " ", head_of(entry)).title()
    words = head.split() * 2 + [w for w in tfidf.top_terms(entry["text_norm"], 64) if w not in head.lower().split()]
    query = ""
    for word in words[:64]:
        if len(query) + len(word) + 1 > 512:
            break
        query = f"{query} {word}".strip()
    return query


def entry_query_text(entry: dict[str, Any]) -> str:
    head = head_of(entry)
    text = entry["text_norm"]
    if head and not text.upper().startswith(head.upper()):
        text = f"{head}. {text}"
    return text[:QUERY_CHARS]


def doc_text(hit: dict[str, Any]) -> str:
    return f"{hit['title']}\n{hit['excerpt']}"[:32000]


def select_entries(entries: list[dict[str, Any]], cap: int | None) -> list[dict[str, Any]]:
    if cap is None:
        return [e for e in entries if e["text_norm"].strip() or e["plate"]]
    by_page: dict[int, list[dict[str, Any]]] = {}
    for e in entries:
        by_page.setdefault(e["row_index"], []).append(e)
    chosen = []
    for row, items in by_page.items():
        plates = [e for e in items if e["plate"]]
        chosen += plates or sorted(items, key=lambda e: -e["chars"])[:cap]
    return sorted(chosen, key=lambda e: (e["row_index"], int(e["entry_id"].split(":")[2])))


def match_entry(entry: dict[str, Any], tfidf: TfIdf, wiki: WikiClient, retr: RetrievalClient) -> dict[str, Any]:
    timing: dict[str, float] = {}
    record: dict[str, Any] = {"entry_id": entry["entry_id"], "page_id": entry["page_id"], "row_index": entry["row_index"],
                              "headword": entry["headword"], "topic_hint": entry.get("topic_hint"),
                              "plate": entry["plate"]}
    query = bm25_query(entry, tfidf)
    record["bm25_query"] = query
    if not query:
        record.update(hits=[], reason="entry has no searchable text", timing=timing)
        return record
    t = time.time()
    result = call(lambda: wiki.search(query, top_k=BM25_K, excerpt_chars=1000), "wiki.search")
    hits = [{"page_id": h.page_id, "revision_id": h.revision_id, "title": h.title, "url": h.url,
             "text_sha256": h.provenance.text_sha256, "bm25_rank": h.rank, "bm25_score": h.bm25_score,
             "excerpt": h.excerpt, "excerpt_offset": h.excerpt_offset, "total_chars": h.total_chars} for h in result.hits]
    # Headword-only search adds the obvious title candidate when long queries drift.
    if head_of(entry):
        extra = call(lambda: wiki.search(head_of(entry).title(), top_k=5, excerpt_chars=1000), "wiki.search headword")
        seen = {h["page_id"] for h in hits}
        for h in extra.hits:
            if h.page_id not in seen:
                hits.append({"page_id": h.page_id, "revision_id": h.revision_id, "title": h.title, "url": h.url,
                             "text_sha256": h.provenance.text_sha256, "bm25_rank": None, "headword_rank": h.rank,
                             "bm25_score": h.bm25_score, "excerpt": h.excerpt, "excerpt_offset": h.excerpt_offset,
                             "total_chars": h.total_chars})
    timing["bm25_s"] = round(time.time() - t, 3)
    record["hits"] = hits
    if not hits:
        record.update(reason="BM25 returned no hits", timing=timing)
        return record

    t = time.time()
    qtext = entry_query_text(entry)
    # The embedder's query context is 512 tokens; dense OCR text can exceed it at 2,000 chars (HTTP 422).
    for limit in (QUERY_CHARS, 1200, 600):
        try:
            qvec = call(lambda: retr.embed([qtext[:limit]], "query"), "embed query")[0]
            break
        except ServiceError as exc:
            if exc.status_code != 422 or limit == 600:
                raise
    timing["embed_query_chars"] = limit
    dvecs: list[list[float]] = []
    docs = [doc_text(h) for h in hits]
    for i in range(0, len(docs), 16):
        batch = docs[i:i + 16]
        dvecs += call(lambda: retr.embed(batch, "document"), "embed documents")
    for h, v in zip(hits, dvecs):
        h["embed_cos"] = round(sum(a * b for a, b in zip(qvec, v)), 6)
    timing["embed_s"] = round(time.time() - t, 3)

    t = time.time()
    top = sorted(range(len(hits)), key=lambda i: -hits[i]["embed_cos"])[:EMBED_KEEP]
    rerank_query = qtext
    rows = call(lambda: retr.rerank(rerank_query, [docs[i] for i in top]), "rerank")
    for row in rows:
        hits[top[row["index"]]]["rerank_logit"] = round(row["relevance_score"], 6)
    timing["rerank_s"] = round(time.time() - t, 3)
    record.update(embed_query_chars=len(qtext), rerank_query_chars=len(rerank_query), timing=timing)
    return record


def rank(record: dict[str, Any], method: str) -> list[dict[str, Any]]:
    """Order saved candidates by one method. No model calls."""
    hits = record.get("hits") or []
    if method == "bm25":
        return sorted(hits, key=lambda h: (h["bm25_rank"] is None, h["bm25_rank"] or 0, -h["bm25_score"]))
    if method == "bm25+embed":
        return sorted([h for h in hits if "embed_cos" in h], key=lambda h: -h["embed_cos"])
    if method == "bm25+embed+rerank":
        return sorted([h for h in hits if "rerank_logit" in h], key=lambda h: -h["rerank_logit"])
    raise ValueError(f"unknown method {method}")


def decide(record: dict[str, Any], tau: float = TAU, entry: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = entry or {}
    ranked = [h for h in rank(record, "bm25+embed+rerank") if not h["title"].endswith("(disambiguation)")]
    out = {"entry_id": record["entry_id"], "status": "no_clear_counterpart", "wiki_page_id": None, "wiki_title": None,
           "wiki_revision_id": None, "wiki_url": None, "text_sha256": None, "bm25_rank": None, "embed_cos": None,
           "rerank_logit": None, "rerank_margin": None, "method": "bm25+embed+rerank", "tau": tau,
           "rule": None, "reason": record.get("reason", ""), "timing": record.get("timing", {})}
    if not ranked:
        out["reason"] = out["reason"] or "no reranked candidates"
        return out
    best = ranked[0]
    margin = best["rerank_logit"] - ranked[1]["rerank_logit"] if len(ranked) > 1 else None
    out.update(wiki_page_id=best["page_id"], wiki_title=best["title"], wiki_revision_id=best["revision_id"],
               wiki_url=best["url"], text_sha256=best["text_sha256"], bm25_rank=best["bm25_rank"],
               embed_cos=best["embed_cos"], rerank_logit=best["rerank_logit"],
               rerank_margin=round(margin, 6) if margin is not None else None)
    logit, head = best["rerank_logit"], head_of(entry) if entry else (record.get("headword") or "")
    chars = entry.get("chars", MIN_CHARS)
    relation = title_relation(head, best["title"], best["excerpt"][:400])
    if chars < MIN_CHARS:
        out["reason"] = f"entry has {chars} chars (< {MIN_CHARS}); too short to judge"
    elif logit > tau:
        out.update(status="matched", rule="logit", reason=f"top rerank logit {logit:.2f} > tau {tau}")
    elif head and logit > TAU_MARGIN and margin is not None and margin >= MIN_MARGIN:
        out.update(status="matched", rule="margin",
                   reason=f"logit {logit:.2f} > {TAU_MARGIN} and margin {margin:.2f} >= {MIN_MARGIN}")
    elif head and logit > TAU_EXACT and relation == "exact":
        out.update(status="matched", rule="exact_title", reason=f"logit {logit:.2f} > {TAU_EXACT} and title equals headword")
    else:
        out["reason"] = f"top rerank logit {logit:.2f} below the acceptance rules; best candidate kept for review"
    return out


def _norm_title(text: str) -> str:
    return re.sub(r"[^a-z ]", "", re.sub(r"\(.*?\)", "", text.lower()).replace("-", " ")).strip()


def title_relation(head: str, title: str, article_lead: str = "") -> str:
    """exact: same name; alias: headword named in the article lead; partial: shared word; none."""
    h, t = _norm_title(head), _norm_title(title)
    if not h:
        return "none"
    if h == t or h.rstrip("s") == t.rstrip("s"):
        return "exact"
    if re.search(rf"\b{re.escape(h)}\b", article_lead.lower()):
        return "alias"
    if set(h.split()) & set(t.split()) or (len(h) >= 5 and (h[:5] == t[:5])):
        return "partial"
    return "none"


def shared_terms(entry_text: str, article_text: str, tfidf: TfIdf, k: int = 5) -> list[str]:
    """Top-k terms in both texts, scored by entry TF-IDF times article term count (log)."""
    art = Counter(tokens(article_text))
    ent = Counter(tokens(entry_text))
    score = {w: c * math.log((1 + tfidf.n) / (1 + tfidf.df[w])) * math.log(1 + art[w]) for w, c in ent.items() if w in art}
    return sorted(score, key=lambda w: (-score[w], w))[:k]


def explain(decision: dict[str, Any], record: dict[str, Any], entry: dict[str, Any], tfidf: TfIdf,
            article_text: str | None, tau: float) -> None:
    """Add "why" and "shared_terms" from evidence only (no LLM)."""
    ranked = [h for h in rank(record, "bm25+embed+rerank") if not h["title"].endswith("(disambiguation)")]
    head = head_of(entry)
    if not ranked:
        decision.update(why=decision["reason"] or "no candidates to compare", shared_terms=[], title_relation="none")
        return
    best = ranked[0]
    source = article_text or best["excerpt"]
    terms = shared_terms(entry["text_norm"], source, tfidf)
    relation = title_relation(head, best["title"], source[:400])
    margin = decision.get("rerank_margin")
    scores = (f"BM25 rank {best['bm25_rank'] if best['bm25_rank'] is not None else 'headword search'}, "
              f"embed cos {best['embed_cos']:.3f}, rerank logit {best['rerank_logit']:.2f}"
              + (f", margin {margin:.2f} over '{ranked[1]['title']}'" if margin is not None else ""))
    decision.update(shared_terms=terms, title_relation=relation)
    head_text = f"headword '{head}'" if head else "no headword"
    if decision["status"] == "matched":
        decision["why"] = (f"{head_text} vs title '{best['title']}': {relation}. "
                           f"Shared distinctive terms ({'full article' if article_text else 'excerpt'}): "
                           f"{', '.join(terms) or 'none'}. Scores: {scores}.")
        return
    problems = []
    if entry.get("chars", MIN_CHARS) < MIN_CHARS:
        problems.append(f"entry too short ({entry.get('chars')} chars)")
    if best["rerank_logit"] <= tau:
        problems.append(f"low top rerank logit {best['rerank_logit']:.2f} <= tau {tau}")
    if margin is not None and margin < MIN_MARGIN:
        problems.append(f"flat margin {margin:.2f} between '{best['title']}' and '{ranked[1]['title']}'")
    top3 = ranked[:3]
    if head and all(title_relation(head, h["title"]) == "none" for h in top3):
        problems.append("top candidates have unrelated titles: " + "; ".join(h["title"] for h in top3))
    elif not head:
        problems.append("no headword to check titles against; top candidates: " + "; ".join(h["title"] for h in top3))
    decision["why"] = "Rejected: " + "; ".join(problems) + f". Best candidate scores: {scores}."


def fetch_article(wiki: WikiClient, page_id: str, expected_sha: str | None) -> dict[str, Any]:
    parts, offset, first = [], 0, None
    while True:
        page = call(lambda: wiki.article(page_id, offset=offset, max_chars=20000), "wiki.article")
        first = first or page
        parts.append(page.text)
        if page.next_offset is None:
            break
        offset = page.next_offset
    text = "".join(parts)
    sha = hashlib.sha256(text.encode()).hexdigest()
    if sha != first.provenance.text_sha256 or (expected_sha and sha != expected_sha):
        raise ServiceError(f"article {page_id} checksum differs after concatenation")
    return {"page_id": page_id, "revision_id": first.revision_id, "title": first.title, "url": first.url,
            "text_sha256": sha, "total_chars": len(text), "license": first.license,
            "provenance": first.provenance.model_dump(), "text": text,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def ablation(work_dir: Path) -> dict[str, Any]:
    """Top-1 per method per entry from saved candidates. No model calls."""
    cand_dir = work_dir / "match" / "candidates"
    rows = []
    for path in sorted(cand_dir.glob("*.json")):
        record = json.loads(path.read_text())
        row = {"entry_id": record["entry_id"], "headword": record.get("headword")}
        for method in METHODS:
            ranked = rank(record, method)
            row[method] = {"page_id": ranked[0]["page_id"], "title": ranked[0]["title"]} if ranked else None
        rows.append(row)
    with (work_dir / "match" / "ablation.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    agree = sum(1 for r in rows if r["bm25"] and r["bm25+embed+rerank"] and r["bm25"]["page_id"] == r["bm25+embed+rerank"]["page_id"])
    return {"entries": len(rows), "bm25_top1_equals_rerank_top1": agree}


def _safe(entry_id: str) -> str:
    return entry_id.replace(":", "_")


def run_match(settings: Settings, work_dir: Path, cap: int | None = CAP_PER_PAGE, tau: float = TAU) -> dict[str, Any]:
    entries = [json.loads(l) for l in (work_dir / "extract" / "entries.jsonl").read_text().splitlines() if l.strip()]
    tfidf = TfIdf([e["text_norm"] for e in entries])
    chosen = select_entries(entries, cap)
    mdir = work_dir / "match"
    cand_dir, art_dir = mdir / "candidates", mdir / "articles"
    cand_dir.mkdir(parents=True, exist_ok=True)
    art_dir.mkdir(parents=True, exist_ok=True)
    started, done, errors = time.time(), 0, []
    with WikiClient(settings.wikipedia_api_url) as wiki, RetrievalClient(settings.retrieval_base_url, settings.retrieval_api_key) as retr:
        for entry in chosen:
            path = cand_dir / f"{_safe(entry['entry_id'])}.json"
            if path.is_file():
                continue
            try:
                record = match_entry(entry, tfidf, wiki, retr)
                record["ran_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                path.write_text(json.dumps(record, ensure_ascii=False, indent=1))
                done += 1
            except (ServiceError, ValueError) as exc:
                errors.append({"entry_id": entry["entry_id"], "error": f"{type(exc).__name__}: {exc}",
                               "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        if errors:
            with (mdir / "failures.jsonl").open("a") as f:
                for e in errors:
                    f.write(json.dumps(e) + "\n")
        error_ids = {e["entry_id"]: e["error"] for e in errors}
        decisions, article_errors = [], []
        for entry in chosen:
            path = cand_dir / f"{_safe(entry['entry_id'])}.json"
            if not path.is_file():
                decisions.append({"entry_id": entry["entry_id"], "status": "error", "method": "bm25+embed+rerank",
                                  "reason": error_ids.get(entry["entry_id"], "no candidate file")})
                continue
            decision = decide(json.loads(path.read_text()), tau, entry)
            if decision["status"] == "matched" and not (art_dir / f"{decision['wiki_page_id']}.json").is_file():
                try:
                    article = fetch_article(wiki, decision["wiki_page_id"], decision["text_sha256"])
                    (art_dir / f"{decision['wiki_page_id']}.json").write_text(json.dumps(article, ensure_ascii=False))
                except (ServiceError, ValueError) as exc:
                    article_errors.append({"entry_id": entry["entry_id"], "page_id": decision["wiki_page_id"], "error": str(exc)})
                    decision["reason"] += f"; article fetch failed: {exc}"
            article_path = art_dir / f"{decision['wiki_page_id']}.json"
            article_text = json.loads(article_path.read_text())["text"] if decision["status"] == "matched" and article_path.is_file() else None
            explain(decision, json.loads(path.read_text()), entry, tfidf, article_text, tau)
            decisions.append(decision)
    with (mdir / "matches.jsonl").open("w") as f:
        for d in decisions:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    if article_errors:
        with (mdir / "failures.jsonl").open("a") as f:
            for e in article_errors:
                f.write(json.dumps(e) + "\n")
    summary = {
        "entries_total": len(entries), "entries_selected": len(chosen),
        "cap": f"{cap} longest entries per page plus every plate page" if cap else "all entries",
        "processed_this_run": done, "errors_this_run": len(errors), "article_errors": len(article_errors),
        "tau": tau, "status": dict(Counter(d["status"] for d in decisions)),
        "seconds": round(time.time() - started, 1),
        "ablation": ablation(work_dir),
    }
    (mdir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary
