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
SHORT_METHOD = "bm25+embed+rerank_short"  # same candidates, rerank query = head + first SHORT_CHARS of text
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
    if method in ("bm25+embed+rerank", SHORT_METHOD):
        return sorted([h for h in hits if "rerank_logit" in h], key=lambda h: -h["rerank_logit"])
    raise ValueError(f"unknown method {method}")


def decide(record: dict[str, Any], tau: float = TAU, entry: dict[str, Any] | None = None,
           tau_margin: float = TAU_MARGIN, min_margin: float = MIN_MARGIN, tau_exact: float = TAU_EXACT,
           method: str = "bm25+embed+rerank") -> dict[str, Any]:
    entry = entry or {}
    ranked = [h for h in rank(record, "bm25+embed+rerank") if not h["title"].endswith("(disambiguation)")]
    out = {"entry_id": record["entry_id"], "status": "no_clear_counterpart", "wiki_page_id": None, "wiki_title": None,
           "wiki_revision_id": None, "wiki_url": None, "text_sha256": None, "bm25_rank": None, "embed_cos": None,
           "rerank_logit": None, "rerank_margin": None, "method": method, "tau": tau,
           "rule": None, "reason": record.get("reason", ""), "timing": record.get("timing", {})}
    if not ranked:
        out["reason"] = out["reason"] or "no reranked candidates"
        return out
    best = ranked[0]
    margin = best["rerank_logit"] - ranked[1]["rerank_logit"] if len(ranked) > 1 else None
    out.update(wiki_page_id=best["page_id"], wiki_title=best["title"], wiki_revision_id=best["revision_id"],
               wiki_url=best["url"], text_sha256=best["text_sha256"], bm25_rank=best["bm25_rank"],
               embed_cos=best.get("embed_cos"), rerank_logit=best["rerank_logit"],
               rerank_margin=round(margin, 6) if margin is not None else None)
    logit, head = best["rerank_logit"], head_of(entry) if entry else (record.get("headword") or "")
    chars = entry.get("chars", MIN_CHARS)
    relation = title_relation(head, best["title"], best["excerpt"][:400])
    if chars < MIN_CHARS:
        out["reason"] = f"entry has {chars} chars (< {MIN_CHARS}); too short to judge"
    elif logit > tau:
        out.update(status="matched", rule="logit", reason=f"top rerank logit {logit:.2f} > tau {tau}")
    elif head and logit > tau_margin and margin is not None and margin >= min_margin:
        out.update(status="matched", rule="margin",
                   reason=f"logit {logit:.2f} > {tau_margin} and margin {margin:.2f} >= {min_margin}")
    elif head and logit > tau_exact and relation == "exact":
        out.update(status="matched", rule="exact_title", reason=f"logit {logit:.2f} > {tau_exact} and title equals headword")
    else:
        out["reason"] = f"top rerank logit {logit:.2f} below the acceptance rules; best candidate kept for review"
    return out


def _norm_title(text: str) -> str:
    return re.sub(r"[^a-z ]", "", re.sub(r"\(.*?\)", "", text.lower()).replace("-", " ")).strip()


# A bracketed qualifier naming a creative work or a thing named after the topic ("Abyssinia (1906 musical)")
# does not make the title the same subject.
WORK_QUALIFIER = re.compile(r"\((?:[^)]*\b(?:film|fiction|album|song|musical|novel|band|character|comics|dc comics|play|tv|series|ship|magazine|newspaper|"
                            r"company|game|opera|poem|comics?|book|journal|surname|given name|\d{4})\b[^)]*)\)", re.I)


def title_relation(head: str, title: str, article_lead: str = "") -> str:
    """exact: same name; alias: headword named in the article lead; partial: shared word; none."""
    h, t = _norm_title(head), _norm_title(title)
    if not h:
        return "none"
    if (h == t or h.rstrip("s") == t.rstrip("s")) and not WORK_QUALIFIER.search(title):
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
              f"embed cos {best.get('embed_cos', float('nan')):.3f}, rerank logit {best['rerank_logit']:.2f}"
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
        short_path = work_dir / "match" / "candidates_short" / path.name
        if short_path.is_file():
            ranked = rank(json.loads(short_path.read_text()), SHORT_METHOD)
            row[SHORT_METHOD] = {"page_id": ranked[0]["page_id"], "title": ranked[0]["title"]} if ranked else None
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


# ---------------------------------------------------------------------------
# Short-query pass and page-level pass.
# Long noisy queries pull rerank logits down. These passes rerank with a short query:
# head (headword, cleaned page topic) + the first SHORT_CHARS of text.
# Outputs never overwrite the long-query results above:
#   match/candidates_short/<entry_id>.json, match/matches_short.jsonl
#   match/topics.json, match/pages/<row>.json, match/page_matches.jsonl

SHORT_CHARS = 600
# Thresholds for short-query logits; see runs/match-threshold-check.md (page-level section).
# Short-query logits have the same scale as long-query ones (median -7.1 vs -6.3), so the rules are the same.
S_TAU, S_TAU_MARGIN, S_MIN_MARGIN, S_TAU_EXACT = TAU, TAU_MARGIN, MIN_MARGIN, TAU_EXACT
PAGE_DOCS = 32


def short_query(head: str, text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if head and not text.upper().startswith(head.upper()):
        return f"{head}. {text[:SHORT_CHARS]}"
    return text[:SHORT_CHARS + len(head)]


def _hit(h: Any, source: str) -> dict[str, Any]:
    return {"page_id": h.page_id, "revision_id": h.revision_id, "title": h.title, "url": h.url,
            "text_sha256": h.provenance.text_sha256, "bm25_rank": h.rank, "bm25_score": h.bm25_score,
            "excerpt": h.excerpt, "excerpt_offset": h.excerpt_offset, "total_chars": h.total_chars, "source": source}


def clean_topic(wiki: WikiClient, raw: str, context: str = "") -> dict[str, Any]:
    """Fix OCR noise in a running-head topic: word-list correction ("UPTICS" -> "optics"),
    then BM25 title lookup for the exact article title ("Optics")."""
    from difflib import SequenceMatcher, get_close_matches

    from .segment import is_word, wordlist

    from .segment import is_word as _w, wordlist as _wl
    text = re.sub(r"([A-Za-z]+)-([A-Za-z]+)", lambda m: m[1] + m[2] if _w(m[1] + m[2], _wl()) else f"{m[1]} {m[2]}", raw)
    text = re.sub(r"[^A-Za-z ]", " ", text)
    if sum(len(w) == 1 for w in text.split()) >= 3:  # spaced letters "C H E M I S SI T R Y"
        text = text.replace(" ", "")
    words, fixed = wordlist(), []
    for word in text.lower().split():
        if is_word(word, words) or len(word) < 4:
            fixed.append(word)
        else:
            # OCR substitutes or inserts letters: try same-or-shorter words with the same first letter.
            pool = [w for w in words if 0 <= len(word) - len(w) <= 2 and (w[:1] == word[:1] or (w[:1] in "aeiou" and word[:1] in "aeiou"))]
            close = get_close_matches(word, pool, n=5, cutoff=0.8)
            # Ties ("indta" -> india / indra): prefer the word used most in the page text.
            close.sort(key=lambda w: -len(re.findall(rf"\b{w}\b", context.lower())))
            fixed.append(close[0] if close else word)
    query = " ".join(fixed).title()
    result = call(lambda: wiki.search(query, top_k=10, excerpt_chars=1000), "wiki.search topic")
    hits = [_hit(h, "topic") for h in result.hits]
    target = _norm_title(query)
    scored = sorted(((SequenceMatcher(None, target, _norm_title(h["title"])).ratio(), h["title"]) for h in hits), reverse=True)
    source = "wordlist" if query.lower() != re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", raw)).strip().lower() else "running_head"
    clean = query
    all_words = all(is_word(w, words) for w in query.lower().split())
    if (not all_words and scored and scored[0][0] >= 0.85 and not re.search(r"\d", scored[0][1])
            and scored[0][1][:1].lower() == query[:1].lower()):
        clean, source = re.sub(r"\s*\(.*?\)", "", scored[0][1]).strip(), "bm25_title"
    exact = next((h["title"] for h in hits if h["title"].lower() == clean.lower()), None)
    return {"raw": raw, "clean": clean, "source": source, "exact_title": exact,
            "ratio": round(scored[0][0], 3) if scored else 0.0, "hits": hits}


def rerank_short(retr: RetrievalClient, query: str, hits: list[dict[str, Any]]) -> None:
    rows = call(lambda: retr.rerank(query, [doc_text(h) for h in hits]), "rerank short")
    for row in rows:
        hits[row["index"]]["rerank_logit"] = round(row["relevance_score"], 6)


def _short_decide(record: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    return decide(record, S_TAU, entry, tau_margin=S_TAU_MARGIN, min_margin=S_MIN_MARGIN, tau_exact=S_TAU_EXACT,
                  method=SHORT_METHOD)


def _topics(wiki: WikiClient, entries: list[dict[str, Any]], path: Path) -> dict[str, dict[str, Any]]:
    topics = json.loads(path.read_text()) if path.is_file() else {}
    for raw in sorted({e["topic_hint"] for e in entries if e.get("topic_hint")}):
        if raw not in topics:
            context = " ".join(e["text_norm"] for e in entries if e.get("topic_hint") == raw)
            topics[raw] = clean_topic(wiki, raw, context)
    path.write_text(json.dumps(topics, ensure_ascii=False, indent=1))
    return topics


def collect_short(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Model calls for the short-query entry pass and the page pass. Resumable."""
    mdir = work_dir / "match"
    entries = [json.loads(l) for l in (work_dir / "extract" / "entries.jsonl").read_text().splitlines() if l.strip()]
    short_dir, page_dir = mdir / "candidates_short", mdir / "pages"
    short_dir.mkdir(exist_ok=True)
    page_dir.mkdir(exist_ok=True)
    errors, done = [], {"entries": 0, "pages": 0}
    with WikiClient(settings.wikipedia_api_url) as wiki, RetrievalClient(settings.retrieval_base_url, settings.retrieval_api_key) as retr:
        topics = _topics(wiki, entries, mdir / "topics.json")
        tfidf = TfIdf([e["text_norm"] for e in entries])
        for entry in entries:
            src, out = mdir / "candidates" / f"{_safe(entry['entry_id'])}.json", short_dir / f"{_safe(entry['entry_id'])}.json"
            if out.is_file() or not src.is_file():
                continue
            long_record = json.loads(src.read_text())
            hits = [{**{k: v for k, v in h.items() if k != "rerank_logit"}, "rerank_long_logit": h["rerank_logit"]}
                    for h in long_record.get("hits", []) if "rerank_logit" in h]
            topic = topics.get(entry.get("topic_hint") or "", {})
            head = entry.get("headword") or (topic.get("clean") if entry["is_continuation"] else None) or ""
            if entry["is_continuation"] and topic:
                seen = {h["page_id"] for h in hits}
                hits += [dict(h) for h in topic["hits"] if h["page_id"] not in seen]
            record = {**{k: v for k, v in long_record.items() if k != "hits"}, "short_head": head,
                      "short_query": short_query(head, entry["text_norm"]), "hits": hits[:PAGE_DOCS]}
            try:
                if hits:
                    rerank_short(retr, record["short_query"], record["hits"])
                record["ran_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                out.write_text(json.dumps(record, ensure_ascii=False, indent=1))
                done["entries"] += 1
            except (ServiceError, ValueError) as exc:
                errors.append({"entry_id": entry["entry_id"], "stage": "short", "error": f"{type(exc).__name__}: {exc}"})
        by_page: dict[int, list[dict[str, Any]]] = {}
        for e in entries:
            by_page.setdefault(e["row_index"], []).append(e)
        for row, items in sorted(by_page.items()):
            out = page_dir / f"{row}.json"
            raw = items[0].get("topic_hint")
            if out.is_file() or not raw or any(e["plate"] for e in items):
                continue
            topic = topics[raw]
            body = " ".join(e["text_norm"] for e in items)
            # Bare titles rank short pages first in BM25; add distinctive page terms to reach main articles.
            terms = bm25_query({"headword": topic["clean"], "text_norm": body}, tfidf)
            extra = call(lambda: wiki.search(" ".join(terms.split()[:24]), top_k=10, excerpt_chars=1000), "wiki.search page")
            hits, seen = [], set()
            for h in topic["hits"] + [_hit(x, "topic+terms") for x in extra.hits]:
                if h["page_id"] not in seen:
                    seen.add(h["page_id"])
                    hits.append(dict(h))
            for depth in range(3):  # top-3 of every entry, round robin
                for e in items:
                    path = short_dir / f"{_safe(e['entry_id'])}.json"
                    ranked = rank(json.loads(path.read_text()), SHORT_METHOD) if path.is_file() else []
                    if depth < len(ranked) and ranked[depth]["page_id"] not in seen:
                        seen.add(ranked[depth]["page_id"])
                        hits.append({k: v for k, v in ranked[depth].items() if k not in {"rerank_logit"}} | {"source": e["entry_id"]})
            record = {"entry_id": f"P:{row}", "row_index": row, "page_id": items[0]["page_id"], "topic": topic["clean"],
                      "topic_raw": raw, "short_query": short_query(topic["clean"], body), "hits": hits[:PAGE_DOCS]}
            try:
                rerank_short(retr, record["short_query"], record["hits"])
                record["ran_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                out.write_text(json.dumps(record, ensure_ascii=False, indent=1))
                done["pages"] += 1
            except (ServiceError, ValueError) as exc:
                errors.append({"entry_id": f"P:{row}", "stage": "page", "error": f"{type(exc).__name__}: {exc}"})
    if errors:
        with (mdir / "failures.jsonl").open("a") as f:
            for e in errors:
                f.write(json.dumps({**e, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
    return {**done, "errors": len(errors)}


PAGE_METHOD = "page_topic+rerank_short"
GUIDE_METHOD = "page_guide+rerank_short"


def _guide(running_head: str | None) -> str | None:
    """A 3-4 letter guide word ("LYR", "LOM") from the running head, else None."""
    if not running_head:
        return None
    letters = re.sub(r"[^A-Z]", "", running_head.upper())
    return letters[:3] if 3 <= len(letters) <= 4 else None


def _guide_decide(mdir: Path, row: int, entry: dict[str, Any], guide: str) -> dict[str, Any] | None:
    """Continuation pages: accept the best short-rerank candidate whose title has a word starting with the
    page guide word, if its logit is above TAU_MARGIN. The guide word comes from the print layout, so it is
    independent of the reranker."""
    page_path = mdir / "pages" / f"{row}.json"
    path = page_path if page_path.is_file() else mdir / "candidates_short" / f"{_safe(entry['entry_id'])}.json"
    if not path.is_file():
        return None
    record = json.loads(path.read_text())
    ranked = [h for h in rank(record, SHORT_METHOD) if "disambiguation" not in h["title"]][:10]
    for i, h in enumerate(ranked):
        if any(w.upper().startswith(guide) for w in re.findall(r"[A-Za-z]+", h["title"])) and h["rerank_logit"] > TAU_MARGIN:
            nxt = ranked[1]["rerank_logit"] if i == 0 and len(ranked) > 1 else ranked[0]["rerank_logit"]
            return {"entry_id": f"P:{row}", "status": "matched", "wiki_page_id": h["page_id"], "wiki_title": h["title"],
                    "wiki_revision_id": h["revision_id"], "wiki_url": h["url"], "text_sha256": h["text_sha256"],
                    "bm25_rank": h.get("bm25_rank"), "embed_cos": h.get("embed_cos"), "rerank_logit": h["rerank_logit"],
                    "rerank_margin": round(h["rerank_logit"] - nxt, 6), "method": GUIDE_METHOD, "tau": TAU_MARGIN,
                    "rule": "guide_word", "reason": f"rank {i + 1} title starts with guide '{guide}', logit {h['rerank_logit']:.2f} > {TAU_MARGIN}"}
    return None


def _article(art_dir: Path, wiki: WikiClient, decision: dict[str, Any], errors: list[dict[str, Any]]) -> str | None:
    """Return the article text for a matched decision, fetching it if needed."""
    path = art_dir / f"{decision['wiki_page_id']}.json"
    if not path.is_file():
        try:
            path.write_text(json.dumps(fetch_article(wiki, decision["wiki_page_id"], decision["text_sha256"]), ensure_ascii=False))
        except (ServiceError, ValueError) as exc:
            errors.append({"entry_id": decision.get("entry_id"), "page_id": decision["wiki_page_id"], "error": str(exc)})
            decision["reason"] += f"; article fetch failed: {exc}"
            return None
    return json.loads(path.read_text())["text"]


def _art_ref(d: dict[str, Any], source: str) -> dict[str, Any]:
    return {k: d.get(k) for k in ("wiki_page_id", "wiki_title", "wiki_revision_id", "wiki_url", "text_sha256",
                                  "rerank_logit", "rerank_margin", "method", "rule")} | {"source": source}


def finalize_short(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Decisions for the short-query entry pass and the page pass. Only article fetches call services."""
    mdir, art_dir = work_dir / "match", work_dir / "match" / "articles"
    entries = [json.loads(l) for l in (work_dir / "extract" / "entries.jsonl").read_text().splitlines() if l.strip()]
    tfidf = TfIdf([e["text_norm"] for e in entries])
    long = {d["entry_id"]: d for d in map(json.loads, (mdir / "matches.jsonl").read_text().splitlines())}
    errors: list[dict[str, Any]] = []
    short: dict[str, dict[str, Any]] = {}
    pages_out = []
    with WikiClient(settings.wikipedia_api_url) as wiki:
        for entry in entries:
            path = mdir / "candidates_short" / f"{_safe(entry['entry_id'])}.json"
            if not path.is_file():
                continue
            record = json.loads(path.read_text())
            head_entry = {**entry, "headword": record.get("short_head") or entry["headword"]}
            d = _short_decide(record, head_entry)
            text = _article(art_dir, wiki, d, errors) if d["status"] == "matched" else None
            explain(d, record, head_entry, tfidf, text, S_TAU)
            short[entry["entry_id"]] = d
        with (mdir / "matches_short.jsonl").open("w") as f:
            for d in short.values():
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

        by_page: dict[int, list[dict[str, Any]]] = {}
        for e in entries:
            by_page.setdefault(e["row_index"], []).append(e)
        for row, items in sorted(by_page.items()):
            ids = [e["entry_id"] for e in items]
            accepted = []
            for e in sorted(items, key=lambda e: -e["chars"]):
                d = long.get(e["entry_id"]) if long.get(e["entry_id"], {}).get("status") == "matched" else short.get(e["entry_id"])
                if d and d["status"] == "matched":
                    accepted.append((e, d))
            articles = [_art_ref(d, e["entry_id"]) for e, d in accepted]
            plate_path = work_dir / "plates" / f"{row}.json"
            page_record = mdir / "pages" / f"{row}.json"
            kind = "plate" if any(e["plate"] for e in items) else "treatise" if items[0].get("topic_hint") else "dictionary"
            base = {"entry_id": f"P:{row}", "row_index": row, "page_id": items[0]["page_id"], "page_kind": kind,
                    "entry_ids": ids}
            if kind == "plate":
                plate = json.loads(plate_path.read_text()) if plate_path.is_file() else None
                out = {**base, "page_topic": (plate or {}).get("plate_caption") or items[0]["text_raw"],
                       "status": "no_clear_counterpart", "method": "plate", "reason": "no plate result from the site worker"}
                if plate:
                    out.update({k: plate.get(k) for k in ("status", "wiki_page_id", "wiki_title", "wiki_revision_id", "wiki_url",
                                                         "text_sha256", "bm25_rank", "embed_cos", "rerank_logit",
                                                         "rerank_margin", "method", "reason")})
                    out["why"] = f"Plate result from artifacts/plates/{row}.json: {plate.get('reason')}"
                    if plate.get("status") == "matched":
                        articles = [_art_ref(plate, "plate")]
                out["articles"] = articles if out["status"] == "matched" else []
                pages_out.append(out)
                continue
            if kind == "treatise" and page_record.is_file():
                record = json.loads(page_record.read_text())
                body_chars = sum(e["chars"] for e in items)
                topic_entry = {"headword": record["topic"], "chars": body_chars, "text_norm": " ".join(e["text_norm"] for e in items)}
                d = _short_decide(record, topic_entry)
                d["method"] = PAGE_METHOD
                text = _article(art_dir, wiki, d, errors) if d["status"] == "matched" else None
                explain(d, record, topic_entry, tfidf, text, S_TAU)
                out = {**base, **d, "entry_id": f"P:{row}", "page_topic": record["topic"],
                       "page_topic_raw": record["topic_raw"]}
                if d["status"] == "matched":
                    articles = [_art_ref(d, "page_topic")] + [a for a in articles if a["wiki_page_id"] != d["wiki_page_id"]]
                elif articles:
                    out["reason"] = f"page topic rejected ({d['reason']}); page matched through its entries"
            else:
                out = {**base, "page_topic": [e["headword"] for e in items if e["headword"]] or None}
                lead = long.get(max(items, key=lambda e: e["chars"])["entry_id"], {})
                out.update({k: v for k, v in lead.items() if k not in {"entry_id"}})
            guide = _guide(items[0].get("running_head"))
            longest = max(items, key=lambda e: e["chars"])
            if out.get("status") != "matched" and not articles and guide and longest["is_continuation"]:
                gd = _guide_decide(mdir, row, longest, guide)
                if gd:
                    text = _article(art_dir, wiki, gd, errors)
                    src = page_record if page_record.is_file() else mdir / "candidates_short" / f"{_safe(longest['entry_id'])}.json"
                    explain(gd, json.loads(src.read_text()), {**longest, "headword": guide}, tfidf, text, S_TAU)
                    gd["why"] = f"Guide word '{guide}' in the running head matches the title. " + gd["why"]
                    out.update({k: v for k, v in gd.items() if k != "entry_id"})
                    articles = [_art_ref(gd, "guide_word")]
            if articles and out.get("status") != "matched":
                e, d = accepted[0]
                out.update({k: v for k, v in d.items() if k not in {"entry_id"}})
                out.update(status="matched", reason=f"matched through entry {e['entry_id']} ({d.get('rule')})",
                           why=f"Through entry {e['entry_id']}: {d.get('why', '')}")
            if len(articles) > 1:
                out["why"] = out.get("why", "") + " Other matched articles on this page: " + "; ".join(
                    f"{a['wiki_title']} [{a['source']}]" for a in articles[1:] if a["wiki_title"] != out.get("wiki_title"))
            out["articles"] = articles if out.get("status") == "matched" else []
            if out.get("status") != "matched":
                out["status"] = "no_clear_counterpart"
            pages_out.append(out)
    with (mdir / "page_matches.jsonl").open("w") as f:
        for p in pages_out:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    if errors:
        with (mdir / "failures.jsonl").open("a") as f:
            for e in errors:
                f.write(json.dumps({**e, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
    cont = [e["entry_id"] for e in entries if e["is_continuation"]]
    before_pages = {long[i]["entry_id"].split(":")[1] for i in long if long[i]["status"] == "matched"}
    long_matched = {i for i, d in long.items() if d["status"] == "matched"}
    short_matched = {i for i, d in short.items() if d["status"] == "matched"}
    report = {
        "pages": len(pages_out),
        "pages_with_match_entry_long_only": len(before_pages),
        "pages_matched_after_page_pass": sum(p["status"] == "matched" for p in pages_out),
        "pages_by_kind": dict(Counter(p["page_kind"] for p in pages_out)),
        "pages_matched_by_kind": dict(Counter(p["page_kind"] for p in pages_out if p["status"] == "matched")),
        "page_topic_matches": sum(1 for p in pages_out if p.get("method") == PAGE_METHOD and p["status"] == "matched"
                                  and p["articles"] and p["articles"][0]["source"] == "page_topic"),
        "entries_matched_long": len(long_matched),
        "entries_matched_short": len(short_matched),
        "entries_matched_either": len(long_matched | short_matched),
        "continuations": len(cont),
        "continuations_matched_long": len(long_matched & set(cont)),
        "continuations_matched_short": len(short_matched & set(cont)),
        "short_only_entries": sorted(short_matched - long_matched),
        "article_errors": len(errors),
    }
    (mdir / "summary_pages.json").write_text(json.dumps(report, indent=1))
    cov_path = work_dir / "extract" / "coverage.json"
    cov = json.loads(cov_path.read_text())
    cov["match_coverage"] = {k: v for k, v in report.items() if k != "short_only_entries"}
    cov_path.write_text(json.dumps(cov, ensure_ascii=False, indent=1))
    return report


def run_page_match(settings: Settings, work_dir: Path) -> dict[str, Any]:
    collected = collect_short(settings, work_dir)
    report = finalize_short(settings, work_dir)
    report["ablation"] = ablation(work_dir)
    mdir = work_dir / "match"
    if (mdir / "vision_expand").is_dir():
        # page_matches_v1.jsonl is the pass without vision; apply_vision writes page_matches.jsonl from it.
        from .vision_expand import apply_vision

        (mdir / "page_matches_v1.jsonl").write_text((mdir / "page_matches.jsonl").read_text())
        report["vision_expand"] = {k: v for k, v in apply_vision(settings, work_dir).items() if k != "recall"}
    from .uncertainty import run_uncertainty

    report["uncertainty"] = {k: v for k, v in run_uncertainty(work_dir).items() if k != "causes"}
    return {"collected": collected, **report}
