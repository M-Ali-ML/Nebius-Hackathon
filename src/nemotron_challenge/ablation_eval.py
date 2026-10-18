"""Retrieval ablation on a small hand-labeled set. Uses saved candidates only; makes no model calls.

Reads  match/labels.jsonl, match/candidates/, match/candidates_short/, match/matches.jsonl, match/matches_short.jsonl
Writes match/ablation_summary.json, match/ablation.png

Labels are our own judgment (one reader), not a gold standard.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .match import SHORT_METHOD, _safe, rank

METHODS = {
    "bm25": ("candidates", "bm25"),
    "bm25+embed": ("candidates", "bm25+embed"),
    "bm25+embed+rerank (long query)": ("candidates", "bm25+embed+rerank"),
    "bm25+embed+rerank (short query)": ("candidates_short", SHORT_METHOD),
}
DECISION_FILES = {"bm25+embed+rerank (long query)": "matches.jsonl", "bm25+embed+rerank (short query)": "matches_short.jsonl"}
LABELER = "match worker (Claude Opus 5.5), own judgment from entry text vs candidate excerpts"


def _records(mdir: Path, entry_id: str) -> dict[str, dict[str, Any]]:
    out = {}
    for folder in ("candidates", "candidates_short"):
        path = mdir / folder / f"{_safe(entry_id)}.json"
        out[folder] = json.loads(path.read_text()) if path.is_file() else {"hits": []}
    return out


def build_labels(source: list[list[Any]], work_dir: Path) -> list[dict[str, Any]]:
    """source rows: [entry_id, gold_titles, has_counterpart, note, origin]. Resolves titles to page ids in the pool."""
    mdir = work_dir / "match"
    rows = []
    for entry_id, titles, has_counterpart, note, origin in source:
        recs = _records(mdir, entry_id)
        pool = {h["title"]: h["page_id"] for r in recs.values() for h in r["hits"]}
        ids = [pool[t] for t in titles if t in pool]
        rows.append({"entry_id": entry_id, "has_counterpart": has_counterpart, "gold_titles": titles,
                     "gold_page_ids": ids, "gold_in_pool": bool(ids), "note": note, "origin": origin, "labeler": LABELER})
    with (mdir / "labels.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def _first_rank(ranked: list[dict[str, Any]], gold: set[str], k: int = 10) -> int | None:
    for i, h in enumerate(ranked[:k]):
        if h["page_id"] in gold:
            return i + 1
    return None


def evaluate(work_dir: Path) -> dict[str, Any]:
    mdir = work_dir / "match"
    labels = [json.loads(l) for l in (mdir / "labels.jsonl").read_text().splitlines() if l.strip()]
    decisions = {m: {d["entry_id"]: d for d in map(json.loads, (mdir / f).read_text().splitlines())}
                 for m, f in DECISION_FILES.items()}
    positives = [l for l in labels if l["has_counterpart"]]
    in_pool = [l for l in positives if l["gold_in_pool"]]
    negatives = [l for l in labels if not l["has_counterpart"]]
    per_item: dict[str, dict[str, Any]] = {}
    methods: dict[str, Any] = {}
    for name, (folder, method) in METHODS.items():
        ranks = {}
        for l in labels:
            ranked = rank(_records(mdir, l["entry_id"])[folder], method)
            ranks[l["entry_id"]] = {"rank": _first_rank(ranked, set(l["gold_page_ids"])),
                                    "top1": {"page_id": ranked[0]["page_id"], "title": ranked[0]["title"]} if ranked else None,
                                    "pool_size": len(ranked)}
            per_item.setdefault(l["entry_id"], {})[name] = ranks[l["entry_id"]]
        hit1 = lambda ls: sum(ranks[l["entry_id"]]["rank"] == 1 for l in ls)
        rr = lambda ls: sum(1 / ranks[l["entry_id"]]["rank"] for l in ls if ranks[l["entry_id"]]["rank"])
        at10 = lambda ls: sum(ranks[l["entry_id"]]["rank"] is not None for l in ls)
        stats = {
            "p_at_1_all_positives": round(hit1(positives) / len(positives), 3),
            "p_at_1_gold_in_pool": round(hit1(in_pool) / len(in_pool), 3),
            "mrr_at_10_gold_in_pool": round(rr(in_pool) / len(in_pool), 3),
            "recall_at_10_all_positives": round(at10(positives) / len(positives), 3),
            "ranked_list_size_median": sorted(r["pool_size"] for r in ranks.values())[len(ranks) // 2],
        }
        if name in decisions:
            d = decisions[name]
            neg_ok = sum(d.get(l["entry_id"], {}).get("status") != "matched" for l in negatives)
            correct = 0
            for l in labels:
                dec = d.get(l["entry_id"], {})
                if dec.get("status") == "matched":
                    correct += dec.get("wiki_page_id") in l["gold_page_ids"]
                else:
                    correct += not l["gold_in_pool"]  # rejecting is right when no right article is available
            stats["no_match_accuracy"] = round(neg_ok / len(negatives), 3)
            stats["decision_accuracy_all_labels"] = round(correct / len(labels), 3)
            stats["accepted"] = sum(d.get(l["entry_id"], {}).get("status") == "matched" for l in labels)
            stats["accepted_correct"] = sum(d.get(l["entry_id"], {}).get("status") == "matched"
                                            and d[l["entry_id"]].get("wiki_page_id") in l["gold_page_ids"] for l in labels)
        else:
            stats["no_match_accuracy"] = 0.0
            stats["no_match_note"] = "no rejection step: top-1 is always returned"
        methods[name] = stats
    pool_recall = round(len(in_pool) / len(positives), 3)
    examples = _examples(labels, per_item)
    summary = {
        "labels": len(labels), "positives": len(positives), "gold_in_pool": len(in_pool), "negatives": len(negatives),
        "candidate_pool_recall": pool_recall,
        "pool_misses": [{"entry_id": l["entry_id"], "gold": l["gold_titles"]} for l in positives if not l["gold_in_pool"]],
        "methods": methods, "examples": examples, "labeler": LABELER,
        "caveat": "40 items labeled by one reader; small sample, no inter-annotator check.",
        "per_item": per_item,
    }
    (mdir / "ablation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    _chart(methods, pool_recall, mdir / "ablation.png", len(in_pool), len(positives), len(negatives))
    return {k: v for k, v in summary.items() if k != "per_item"}


def _examples(labels: list[dict[str, Any]], per_item: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    long, fixed, broke = "bm25+embed+rerank (long query)", [], []
    for l in labels:
        if not l["gold_in_pool"]:
            continue
        r = per_item[l["entry_id"]]
        row = {"entry_id": l["entry_id"], "gold": l["gold_titles"], "gold_page_ids": l["gold_page_ids"],
               **{m: {"rank": v["rank"], "top1": v["top1"]} for m, v in r.items()}}
        if r[long]["rank"] == 1 and r["bm25"]["rank"] != 1 and r["bm25+embed"]["rank"] != 1:
            fixed.append(row)
        if r[long]["rank"] != 1 and (r["bm25"]["rank"] == 1 or r["bm25+embed"]["rank"] == 1):
            broke.append(row)
    return {"rerank_fixed": fixed, "rerank_broke": broke}


def _chart(methods: dict[str, Any], pool_recall: float, path: Path, n_pool: int, n_pos: int, n_neg: int) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(methods)
    labels = ["BM25", "BM25 + embed", "+ rerank\n(long query)", "+ rerank\n(short query)"]
    metrics = [("p_at_1_gold_in_pool", f"P@1 (gold in pool, n={n_pool})"),
               ("mrr_at_10_gold_in_pool", "MRR@10 (gold in pool)"),
               ("no_match_accuracy", f"No-match accuracy (n={n_neg})")]
    colors = ["#4C78A8", "#F58518", "#54A24B"]
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    width = 0.26
    for j, (key, label) in enumerate(metrics):
        values = [methods[n][key] for n in names]
        bars = ax.bar([i + (j - 1) * width for i in range(len(names))], values, width, label=label, color=colors[j])
        for b, v in zip(bars, values):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", fontsize=7)
    ax.axhline(pool_recall, color="#888", linestyle="--", linewidth=1)
    ax.text(1.0, pool_recall + 0.015, f"candidate pool recall {pool_recall:.2f} (gold anywhere in pool, n={n_pos})",
            ha="center", fontsize=7, color="#555")
    ax.set_xticks(range(len(names)), labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("score")
    ax.set_title("Retrieval ablation on 40 hand-labeled Britannica entries (own labels)", fontsize=9)
    ax.legend(fontsize=7, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
