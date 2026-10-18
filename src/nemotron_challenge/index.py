"""LanceDB evidence index: Britannica entries and chunks of matched Wikipedia articles.

Tables at settings.db_path (CHALLENGE_DB_PATH):
  entries      entry_id, page_id, row_index, headword, text_norm, text_raw, vector
  wiki_chunks  chunk_id, wiki_page_id, revision_id, title, url, text, text_sha256, offset, vector
Entries embed as documents (text_norm cut to 32,000 chars). Article chunks of about 1,500 chars embed as documents.
Vectors are cached in match/vectors/ so a rebuild makes no new calls.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .clients import RetrievalClient
from .config import EMBED_DIMENSIONS, Settings
from .match import call

CHUNK_CHARS = 1500


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[tuple[int, str]]:
    """Split at paragraph or sentence ends near `size` chars. Returns (offset, chunk)."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start + size // 2:end]
            cut = max(window.rfind("\n"), window.rfind(". "))
            if cut != -1:
                end = start + size // 2 + cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append((start, piece))
        start = end
    return chunks


def _embed_cached(retr: RetrievalClient, cache: Path, items: list[tuple[str, str]]) -> dict[str, list[float]]:
    """items: (key, text). Cached in a JSONL file keyed by id; only missing keys are embedded."""
    vectors: dict[str, list[float]] = {}
    if cache.is_file():
        for line in cache.read_text().splitlines():
            row = json.loads(line)
            vectors[row["id"]] = row["vector"]
    missing = [(k, t) for k, t in items if k not in vectors]
    with cache.open("a") as f:
        for i in range(0, len(missing), 16):
            batch = missing[i:i + 16]
            vecs = call(lambda: retr.embed([t for _, t in batch], "document"), "embed index documents")
            for (key, _), vec in zip(batch, vecs):
                vectors[key] = vec
                f.write(json.dumps({"id": key, "vector": vec}) + "\n")
    return vectors


def build_index(settings: Settings, work_dir: Path) -> dict[str, Any]:
    import lancedb

    entries = [json.loads(l) for l in (work_dir / "extract" / "entries.jsonl").read_text().splitlines() if l.strip()]
    entries = [e for e in entries if e["text_norm"].strip()]
    vec_dir = work_dir / "match" / "vectors"
    vec_dir.mkdir(parents=True, exist_ok=True)
    articles = [json.loads(p.read_text()) for p in sorted((work_dir / "match" / "articles").glob("*.json"))]
    chunks = []
    for art in articles:
        for n, (offset, text) in enumerate(chunk_text(art["text"])):
            chunks.append({"chunk_id": f"W:{art['page_id']}:{art['revision_id']}:{n}", "wiki_page_id": art["page_id"],
                           "revision_id": art["revision_id"], "title": art["title"], "url": art["url"],
                           "text_sha256": art["text_sha256"], "offset": offset, "text": text})
    with RetrievalClient(settings.retrieval_base_url, settings.retrieval_api_key) as retr:
        evec = _embed_cached(retr, vec_dir / "entries.jsonl", [(e["entry_id"], e["text_norm"][:32000]) for e in entries])
        cvec = _embed_cached(retr, vec_dir / "wiki_chunks.jsonl", [(c["chunk_id"], f"{c['title']}\n{c['text']}") for c in chunks])
    db = lancedb.connect(str(settings.db_path))
    entry_rows = [{"entry_id": e["entry_id"], "page_id": e["page_id"], "row_index": e["row_index"],
                   "headword": e["headword"] or "", "text_norm": e["text_norm"], "text_raw": e["text_raw"],
                   "vector": evec[e["entry_id"]]} for e in entries]
    chunk_rows = [{**c, "vector": cvec[c["chunk_id"]]} for c in chunks]
    db.create_table("entries", entry_rows, mode="overwrite")
    if chunk_rows:
        db.create_table("wiki_chunks", chunk_rows, mode="overwrite")
    return {"db_path": str(settings.db_path), "entries": len(entry_rows), "wiki_chunks": len(chunk_rows),
            "articles": len(articles), "dimensions": EMBED_DIMENSIONS}


def search(query: str, table: str = "entries", k: int = 5, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Embed the query (input_type=query) and return the k nearest rows by cosine distance, without vectors."""
    import lancedb

    settings = settings or Settings.from_env()
    if table not in {"entries", "wiki_chunks"}:
        raise ValueError("table must be entries or wiki_chunks")
    query = re.sub(r"\s+", " ", query).strip()[:2000]
    with RetrievalClient(settings.retrieval_base_url, settings.retrieval_api_key) as retr:
        vec = call(lambda: retr.embed([query], "query"), "embed search query")[0]
    rows = lancedb.connect(str(settings.db_path)).open_table(table).search(vec).metric("cosine").limit(k).to_list()
    for row in rows:
        row.pop("vector", None)
    return rows
