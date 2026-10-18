"""Inspect and rescue high-confidence threshold-miss matches (`B:1214:0`, `P:13`, `P:247`, `P:268`).

Reads:
  extract/entries.jsonl
  match/page_matches.jsonl
  match/candidates/B_1214_0.json
  match/vision_expand/{13,247,268}.json

Writes:
  match/articles/<wiki_page_id>.json           full Wikipedia article text, SHA-256 verified
  compare/raw/{B_1214_0,P_13,P_247,P_268}.json raw Super VL reply per rescued pair
  compare/pairs/{B_1214_0,P_13,P_247,P_268}.json checked comparison + drift signals + rescued_threshold_miss=True
  match/rescued_threshold_misses.json          summary report of the 4 rescued threshold-miss pairs
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .clients import ChatClient, WikiClient
from .compare import _jsonl, compare_pair, safe_id
from .config import Settings
from .match import SHORT_METHOD, TAU, fetch_article, rank


RESCUED_TARGETS: tuple[dict[str, Any], ...] = (
    {
        "entry_id": "B:1214:0",
        "level": "entry",
        "row_index": 1214,
        "candidate_source": "match/candidates/B_1214_0.json",
        "method": "bm25+embed+rerank",
        "expected_title": "Firedamp",
        "britannica_head": "DAMP (continuation on DAM page)",
        "rationale": (
            "Top-1 reranked candidate is Firedamp (BM25 rank 1, embed cosine 0.393, rerank logit -4.46, "
            "margin 0.48 over Blackdamp). The entry is a continuation without a printed headword on row 1214, "
            "so only the raw logit rule (TAU = -4.0) applied and missed by 0.46 logit."
        ),
    },
    {
        "entry_id": "P:13",
        "level": "page",
        "row_index": 13,
        "candidate_source": "match/vision_expand/13.json",
        "method": "vision_expand",
        "expected_title": "Shipbuilding",
        "britannica_head": "SHIP-BUILDING",
        "rationale": (
            "Top-1 vision-expanded reranked candidate is Shipbuilding (rerank logit -6.27, margin 0.37 over "
            "Longitudinal framing). Super VL read the running head SHIP-BUILDING and proposed Shipbuilding, "
            "which matches the treatise topic."
        ),
    },
    {
        "entry_id": "P:247",
        "level": "page",
        "row_index": 247,
        "candidate_source": "match/vision_expand/247.json",
        "method": "vision_expand",
        "expected_title": "Mount Etna",
        "britannica_head": "AETNA / ETN",
        "rationale": (
            "Top-1 vision-expanded reranked candidate is Mount Etna (rerank logit -4.75, margin 0.18 over "
            "Etna, Wisconsin). The 18th-century entry uses the Latin spelling AETNA (running head ETN); "
            "vision query expansion recovered Mount Etna at rank 1 just below TAU = -4.0."
        ),
    },
    {
        "entry_id": "P:268",
        "level": "page",
        "row_index": 268,
        "candidate_source": "match/vision_expand/268.json",
        "method": "vision_expand",
        "expected_title": "Laurus",
        "britannica_head": "LAURUS / LAU",
        "rationale": (
            "Top-1 vision-expanded reranked candidate is Laurus (rerank logit -7.32, margin 0.11 over "
            "Lauraceae). The page continues the botanical entry on the genus Laurus (bay, cinnamon, camphor, "
            "sassafras) under running head LAU."
        ),
    },
)


def inspect_target_candidate(work_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Load the candidate pool for a target entry or page and verify the top-1 reranked hit."""
    cand_path = work_dir / spec["candidate_source"]
    if not cand_path.is_file():
        raise FileNotFoundError(f"Missing candidate file: {cand_path}")
    record = json.loads(cand_path.read_text())
    rank_method = "bm25+embed+rerank" if spec["level"] == "entry" else SHORT_METHOD
    ranked = [h for h in rank(record, rank_method) if not h["title"].endswith("(disambiguation)")]
    if not ranked:
        raise ValueError(f"No reranked candidates in {cand_path}")
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    margin = round(best["rerank_logit"] - runner_up["rerank_logit"], 6) if runner_up else None
    if best["title"] != spec["expected_title"]:
        raise ValueError(
            f"Expected top-1 title {spec['expected_title']!r} for {spec['entry_id']}, got {best['title']!r}"
        )
    return {
        "entry_id": spec["entry_id"],
        "level": spec["level"],
        "row_index": spec["row_index"],
        "candidate_source": spec["candidate_source"],
        "method": spec["method"],
        "britannica_head": spec["britannica_head"],
        "wiki_page_id": str(best["page_id"]),
        "wiki_revision_id": str(best["revision_id"]),
        "wiki_title": best["title"],
        "wiki_url": best["url"],
        "text_sha256": best["text_sha256"],
        "bm25_rank": best.get("bm25_rank"),
        "embed_cos": best.get("embed_cos"),
        "rerank_logit": best["rerank_logit"],
        "rerank_margin": margin,
        "runner_up_title": runner_up["title"] if runner_up else None,
        "runner_up_logit": runner_up["rerank_logit"] if runner_up else None,
        "tau": TAU,
        "rationale": spec["rationale"],
    }


def ensure_article(wiki: WikiClient, work_dir: Path, match_info: dict[str, Any]) -> dict[str, Any]:
    """Fetch or load the Wikipedia article and verify its SHA-256 checksum."""
    art_dir = work_dir / "match" / "articles"
    art_dir.mkdir(parents=True, exist_ok=True)
    page_id = match_info["wiki_page_id"]
    expected_sha = match_info["text_sha256"]
    art_path = art_dir / f"{page_id}.json"
    if art_path.is_file():
        article = json.loads(art_path.read_text())
        if article.get("text_sha256") != expected_sha:
            raise ValueError(
                f"Checksum mismatch in existing article {art_path}: {article.get('text_sha256')} != {expected_sha}"
            )
        return article
    article = fetch_article(wiki, page_id, expected_sha)
    art_path.write_text(json.dumps(article, ensure_ascii=False))
    return article


def build_britannica_side(
    work_dir: Path,
    entries_by_id: dict[str, dict[str, Any]],
    page_matches_by_id: dict[str, dict[str, Any]],
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Build the Britannica entry or synthetic page record expected by compare_pair."""
    eid = spec["entry_id"]
    if spec["level"] == "entry":
        if eid not in entries_by_id:
            raise KeyError(f"Entry {eid} not found in extract/entries.jsonl")
        return entries_by_id[eid]

    pm = page_matches_by_id.get(eid)
    if pm is None:
        raise KeyError(f"Page {eid} not found in match/page_matches.jsonl")
    parts = [entries_by_id[e] for e in pm["entry_ids"] if e in entries_by_id and entries_by_id[e]["text_norm"].strip()]
    if not parts:
        raise ValueError(f"Page {eid} has no non-empty entry parts")
    return {
        "entry_id": pm["entry_id"],
        "page_id": pm["page_id"],
        "row_index": pm["row_index"],
        "image_sha256": parts[0].get("image_sha256"),
        "headword": None,
        "topic_hint": pm.get("page_topic") or parts[0].get("topic_hint") or parts[0].get("running_head"),
        "page_kind": pm.get("page_kind"),
        "entry_ids": [e["entry_id"] for e in parts],
        "text_raw": "\n\n".join(e["text_raw"] for e in parts),
        "text_norm": "\n\n".join(e["text_norm"] for e in parts),
        "norm_edits": sum(e.get("norm_edits", 0) for e in parts),
        "parts": parts,
    }


def run_rescue(settings: Settings, work_dir: Path, redo: bool = False) -> dict[str, Any]:
    """Inspect, fetch articles, run compare_pair with quote verification, and write summary report."""
    work_dir = Path(work_dir)
    entries = _jsonl(work_dir / "extract" / "entries.jsonl")
    entries_by_id = {e["entry_id"]: e for e in entries}
    page_matches = _jsonl(work_dir / "match" / "page_matches.jsonl")
    page_matches_by_id = {m["entry_id"]: m for m in page_matches}

    inspected: list[dict[str, Any]] = []
    articles_by_page_id: dict[str, dict[str, Any]] = {}

    with WikiClient(settings.wikipedia_api_url) as wiki:
        for spec in RESCUED_TARGETS:
            info = inspect_target_candidate(work_dir, spec)
            article = ensure_article(wiki, work_dir, info)
            articles_by_page_id[info["wiki_page_id"]] = article
            inspected.append(info)

    pairs_dir = work_dir / "compare" / "pairs"
    pairs_dir.mkdir(parents=True, exist_ok=True)
    pair_records: list[dict[str, Any]] = []

    with ChatClient(settings.super_base_url, settings.super_api_key, settings.super_model, timeout=300) as chat:
        chat.verify_model()
        for spec, info in zip(RESCUED_TARGETS, inspected):
            eid = info["entry_id"]
            pair_path = pairs_dir / f"{safe_id(eid)}.json"
            if pair_path.is_file() and not redo:
                record = json.loads(pair_path.read_text())
            else:
                b_side = build_britannica_side(work_dir, entries_by_id, page_matches_by_id, spec)
                article = articles_by_page_id[info["wiki_page_id"]]
                record = compare_pair(chat, b_side, info, article, work_dir)
            if record.get("status") == "ok":
                record["rescued_threshold_miss"] = True
                record["rescue_metadata"] = {
                    "candidate_source": info["candidate_source"],
                    "method": info["method"],
                    "tau": info["tau"],
                    "rerank_logit": info["rerank_logit"],
                    "rerank_margin": info["rerank_margin"],
                    "runner_up_title": info["runner_up_title"],
                    "runner_up_logit": info["runner_up_logit"],
                    "rationale": info["rationale"],
                }
                pair_path.write_text(json.dumps(record, ensure_ascii=False, indent=1))
            pair_records.append(record)

    summary_items = []
    for info, rec in zip(inspected, pair_records):
        article = articles_by_page_id[info["wiki_page_id"]]
        drift_info = rec.get("drift", {})
        summary_items.append({
            "entry_id": info["entry_id"],
            "level": info["level"],
            "row_index": info["row_index"],
            "britannica_head": info["britannica_head"],
            "candidate_source": info["candidate_source"],
            "method": info["method"],
            "wiki_page_id": info["wiki_page_id"],
            "wiki_revision_id": info["wiki_revision_id"],
            "wiki_title": info["wiki_title"],
            "wiki_url": info["wiki_url"],
            "text_sha256": info["text_sha256"],
            "article_total_chars": article.get("total_chars"),
            "bm25_rank": info["bm25_rank"],
            "embed_cos": info["embed_cos"],
            "rerank_logit": info["rerank_logit"],
            "rerank_margin": info["rerank_margin"],
            "runner_up_title": info["runner_up_title"],
            "runner_up_logit": info["runner_up_logit"],
            "tau": info["tau"],
            "rationale": info["rationale"],
            "compare_status": rec.get("status"),
            "pair_file": f"compare/pairs/{safe_id(info['entry_id'])}.json",
            "raw_file": f"compare/raw/{safe_id(info['entry_id'])}.json",
            "article_file": f"match/articles/{info['wiki_page_id']}.json",
            "rescued_threshold_miss": rec.get("rescued_threshold_miss", False),
            "quote_check": rec.get("quote_check"),
            "claim_counts": drift_info.get("claim_counts"),
            "claims_checked": drift_info.get("claims_checked"),
            "superseded_share": drift_info.get("knowledge", {}).get("superseded_share"),
            "renamed_share": drift_info.get("lexical", {}).get("renamed_share"),
            "enduring_share": drift_info.get("enduring_share"),
            "dropped_share": drift_info.get("coverage", {}).get("dropped_share"),
            "term_pairs": drift_info.get("lexical", {}).get("term_pairs", []),
            "wiki_only_topics": drift_info.get("coverage", {}).get("wiki_only_topics", []),
        })

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tau": TAU,
        "count": len(summary_items),
        "ok": sum(1 for item in summary_items if item["compare_status"] == "ok"),
        "total_quotes_kept": sum((item["quote_check"] or {}).get("kept", 0) for item in summary_items),
        "total_quotes_rejected": sum((item["quote_check"] or {}).get("rejected", 0) for item in summary_items),
        "note": (
            "These 4 pairs ranked the exact counterpart Wikipedia article at top-1 in reranking, "
            "but their raw rerank logits fell below TAU = -4.0 because they lacked an exact-matching "
            "printed entry headword for the exact-title fallback rule. Each pair is saved with "
            "rescued_threshold_miss=true so get_pair and downstream inspection preserve full provenance "
            "and threshold transparency."
        ),
        "rescued_pairs": summary_items,
    }
    out_path = work_dir / "match" / "rescued_threshold_misses.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> None:
    settings = Settings.from_env()
    work_dir = Path("artifacts")
    report = run_rescue(settings, work_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
