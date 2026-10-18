"""Segmentation and match-decision behavior on small fixtures. These do not measure OCR or retrieval quality."""
import json

import pytest

from nemotron_challenge import segment
from nemotron_challenge.cli import main
from nemotron_challenge.index import chunk_text
from nemotron_challenge.match import TfIdf, bm25_query, decide, rank, select_entries


def page(blocks, row=7):
    return {"page_id": f"britannica:x:train:{row}", "row_index": row, "image_sha256": "0" * 64,
            "blocks": [{"order": i, "cls": c, "bbox": [0, 0, 1, 1], "text": t} for i, (c, t) in enumerate(blocks)]}


def test_headwords_continuation_and_headers():
    entries = segment.segment_page(page([
        ("Page-header", "FAR [ 12 ] FAR"),
        ("Text", "and so the wri-\nter ended the former article."),
        ("Text", "FARM, a piece of land let for tillage, with houses and fields around it."),
        ("Section-header", "HEM"),
        ("Text", "FARMING, the art of working land. It is very old and well known."),
        ("Text", "In England this is done with horses and with oxen in some places."),
        ("Page-footer", "VOL. VII"),
    ]))
    assert [e["headword"] for e in entries] == [None, "FARM", "FARMING"]
    assert entries[0]["is_continuation"] and "writer ended" in entries[0]["text_raw"]
    assert entries[2]["block_orders"] == [4, 5]
    assert entries[0]["running_head"] == "FAR"
    assert all(e["entry_id"] == f"B:7:{i}" for i, e in enumerate(entries))


def test_roman_numeral_section_is_not_a_headword():
    assert segment.headword_of({"cls": "Section-header", "text": "## VII. In the Education of People"}) is None
    assert segment.headword_of({"cls": "Title", "text": "O R A T O R Y."}) == "ORATORY"
    assert segment.headword_of({"cls": "Text", "text": "HELSINGIC CHARACTER, a kind"}) == "HELSINGIC CHARACTER"


def test_plate_page_becomes_one_flagged_entry():
    entries = segment.segment_page(page([("Picture", ""), ("Caption", "MIDWIFERY PLATE CCCXLVII.")]))
    assert len(entries) == 1 and entries[0]["plate"] and entries[0]["headword"] is None
    assert entries[0]["text_raw"] == "MIDWIFERY PLATE CCCXLVII."


@pytest.mark.skipif(not segment.wordlist(), reason="needs /usr/share/dict/words")
def test_long_s_fixes_go_to_text_norm_only():
    norm, edits = segment.normalize("a town fituated on the fea, ufed for fishing")
    assert norm == "a town situated on the sea, used for fishing" and edits == 3
    assert segment.normalize("ﬁsh")[0] == "fish"


def test_extract_without_pages_fails_cleanly(tmp_path):
    assert main(["run", "extract", "--work-dir", str(tmp_path / "w")]) == 1


def hit(pid, bm25_rank, cos=None, logit=None):
    h = {"page_id": pid, "revision_id": "1", "title": f"T{pid}", "url": "u", "text_sha256": "a" * 64,
         "bm25_rank": bm25_rank, "bm25_score": 10.0 - bm25_rank, "excerpt": "x"}
    if cos is not None:
        h["embed_cos"] = cos
    if logit is not None:
        h["rerank_logit"] = logit
    return h


def test_decision_threshold_margin_and_ablation_ranking():
    record = {"entry_id": "B:1:0", "hits": [hit("1", 1, 0.2), hit("2", 2, 0.5, 3.0), hit("3", 3, 0.4, 1.0)]}
    assert [h["page_id"] for h in rank(record, "bm25")] == ["1", "2", "3"]
    assert [h["page_id"] for h in rank(record, "bm25+embed")] == ["2", "3", "1"]
    d = decide(record, tau=2.0)
    assert d["status"] == "matched" and d["wiki_page_id"] == "2" and d["rerank_margin"] == 2.0
    assert decide(record, tau=5.0)["status"] == "no_clear_counterpart"
    assert decide({"entry_id": "B:1:1", "hits": []})["status"] == "no_clear_counterpart"
    # margin rule needs a headword; exact-title rule; short entries; disambiguation pages are skipped
    low = {"entry_id": "B:1:2", "hits": [hit("2", 1, 0.5, -6.0), hit("3", 2, 0.4, -7.5)]}
    assert decide(low, entry={"headword": "T3", "chars": 500})["rule"] == "margin"
    assert decide(low, entry={"headword": None, "chars": 500})["status"] == "no_clear_counterpart"
    flat = {"entry_id": "B:1:3", "hits": [hit("2", 1, 0.5, -8.5), hit("3", 2, 0.4, -8.6)]}
    assert decide(flat, entry={"headword": "T2", "chars": 500})["rule"] == "exact_title"
    assert decide(record, tau=2.0, entry={"headword": "X", "chars": 10})["status"] == "no_clear_counterpart"
    dis = {"entry_id": "B:1:4", "hits": [{**hit("9", 1, 0.9, 9.0), "title": "Farm (disambiguation)"}, hit("2", 2, 0.5, 3.0)]}
    assert decide(dis, tau=2.0)["wiki_page_id"] == "2"


def test_cap_keeps_longest_entries_and_plates():
    es = [{"entry_id": f"B:1:{i}", "row_index": 1, "chars": i, "plate": False, "text_norm": "x"} for i in range(5)]
    es.append({"entry_id": "B:2:0", "row_index": 2, "chars": 0, "plate": True, "text_norm": ""})
    assert [e["entry_id"] for e in select_entries(es, 3)] == ["B:1:2", "B:1:3", "B:1:4", "B:2:0"]


def test_bm25_query_limits():
    entry = {"headword": "FARM", "text_norm": " ".join(f"word{i}x" for i in range(200)) + " tillage"}
    q = bm25_query(entry, TfIdf([entry["text_norm"], "other text"]))
    assert q.startswith("Farm Farm") and len(q) <= 512 and len(q.split()) <= 64


def test_chunks_cover_text():
    text = "Sentence one is here. " * 300
    chunks = chunk_text(text)
    assert all(len(c) <= 1500 for _, c in chunks) and chunks[0][0] == 0


def test_why_explains_match_and_rejection():
    from nemotron_challenge.match import explain, title_relation
    assert title_relation("THOMAS SYDENHAM", "Thomas Sydenham") == "exact"
    assert title_relation("SWIVELS", "Swivel gun") == "partial"
    assert title_relation("HELM", "Rudder", "A rudder, or helm, is") == "alias"
    entry = {"headword": "FARM", "text_norm": "FARM, land for tillage with fields and tillage tools", "is_continuation": False}
    record = {"entry_id": "B:1:0", "hits": [hit("2", 2, 0.5, 3.0), hit("3", 3, 0.4, 2.5)]}
    tfidf = TfIdf([entry["text_norm"], "other"])
    d = decide(record, tau=2.0)
    explain(d, record, entry, tfidf, "Farm land used for tillage and fields", 2.0)
    assert "tillage" in d["shared_terms"] and "rerank logit 3.00" in d["why"]
    d = decide(record, tau=5.0)
    explain(d, record, entry, tfidf, None, 5.0)
    assert d["why"].startswith("Rejected:") and "flat margin" in d["why"] and "unrelated titles" in d["why"]
