"""Fixture tests for the compare stage and the agent tools. They prove setup behavior, not model quality."""
from collections import Counter
import json
from pathlib import Path

from PIL import Image
import pytest

from nemotron_challenge import agent_tools, compare
from nemotron_challenge.agent_runner import slug, summarize

ENTRY = {"entry_id": "B:7:0", "page_id": "britannica:x:train:7", "row_index": 7, "headword": "AIR",
         "text_raw": "AIR, a thin fluid. Fixed air is found in chalk and does extinguish flame.",
         "text_norm": "AIR, a thin fluid. Fixed air is found in chalk and does extinguish flame.",
         "norm_edits": 2, "chars": 72, "image_sha256": "abc"}
ARTICLE = {"page_id": "123", "revision_id": "456", "title": "Carbon dioxide", "url": "https://en.wikipedia.org/wiki/CO2",
           "text_sha256": "f00", "text": "Carbon dioxide is a chemical compound. It is found in limestone and chalk deposits."}
MATCH = {"entry_id": "B:7:0", "status": "matched", "wiki_page_id": "123", "wiki_title": "Carbon dioxide",
         "wiki_revision_id": "456", "wiki_url": ARTICLE["url"], "text_sha256": "f00", "rerank_logit": 2.0, "rerank_margin": 0.4}


@pytest.fixture
def work(tmp_path: Path) -> Path:
    (tmp_path / "extract" / "pages").mkdir(parents=True)
    (tmp_path / "match" / "articles").mkdir(parents=True)
    (tmp_path / "extract" / "entries.jsonl").write_text(json.dumps(ENTRY) + "\n")
    (tmp_path / "match" / "matches.jsonl").write_text(json.dumps(MATCH) + "\n")
    (tmp_path / "match" / "articles" / "123.json").write_text(json.dumps(ARTICLE))
    scan = tmp_path / "scan.jpg"
    Image.new("RGB", (100, 200), "white").save(scan)
    (tmp_path / "extract" / "pages" / "7.json").write_text(json.dumps(
        {"page_id": ENTRY["page_id"], "row_index": 7, "image_sha256": "abc", "scan_path": str(scan)}))
    return tmp_path


def test_quote_check_allows_whitespace_and_rejects_invented_text():
    src = compare.norm("Fixed air is found\n in  chalk")
    assert compare.quote_ok("fixed air is   found in chalk", src)
    assert not compare.quote_ok("fixed air is found in limestone", src)
    assert not compare.quote_ok("air", src)  # too short to count as evidence


def test_check_keeps_grounded_items_and_drift_counts_only_them():
    data = {
        "claims": [
            {"claim": "c1", "tag": "renamed", "quote_britannica": "Fixed air is found in chalk",
             "quote_wikipedia": "found in limestone and chalk"},
            {"claim": "c2", "tag": "dropped", "quote_britannica": "does extinguish flame", "quote_wikipedia": None},
            {"claim": "c3", "tag": "superseded", "quote_britannica": "invented words here", "quote_wikipedia": "Carbon dioxide is"},
            {"claim": "c4", "tag": "maybe", "quote_britannica": "a thin fluid", "quote_wikipedia": "Carbon dioxide is"},
        ],
        "term_pairs": [{"old": "fixed air", "new": "carbon dioxide", "quote_britannica": "Fixed air is found",
                        "quote_wikipedia": "Carbon dioxide is a chemical"}],
        "wiki_only_topics": [{"topic": "chemistry", "quote_wikipedia": "a chemical compound"}, {"quote_wikipedia": "x"}],
    }
    kept, rejected = compare.check(data, ENTRY["text_norm"], ARTICLE["text"])
    assert [c["claim"] for c in kept["claims"]] == ["c1", "c2"]
    assert len(rejected) == 3
    d = compare.drift(ENTRY, kept)
    assert d["lexical"]["renamed_share"] == 0.5 and d["coverage"]["dropped_share"] == 0.5
    assert d["knowledge"]["superseded_share"] == 0.0
    assert d["lexical"]["term_pairs"] == [{"old": "fixed air", "new": "carbon dioxide"}]
    assert d["orthographic"]["edits_per_100_words"] == round(200 / 14, 2)


def test_parse_json_strips_fences():
    assert compare.parse_json('```json\n{"claims": []}\n```') == {"claims": []}
    with pytest.raises(ValueError):
        compare.parse_json("no json")


def test_log_odds_sign():
    z = compare.log_odds(Counter({"phlogiston": 10, "fluid": 5}), Counter({"oxygen": 10, "fluid": 5}))
    assert z["phlogiston"] > 0 > z["oxygen"]


def test_wordfreq_and_pair_with_fake_model(work, monkeypatch):
    freq = compare.wordfreq(work)
    assert freq["wikipedia_docs"] == 1
    saved = json.loads((work / "compare" / "wordfreq.json").read_text())
    assert saved["wikipedia_articles"][0]["revision_id"] == "456"
    assert (work / "compare" / "wordfreq_top.png").exists()

    reply = {"model": "nvidia/Nemotron-3.5-Super-VL", "usage": {}, "choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps({"claims": [{"claim": "c", "tag": "enduring", "quote_britannica": "found in chalk",
                                           "quote_wikipedia": "limestone and chalk deposits"}]})}}]}

    class FakeChat:
        def complete(self, *args, **kwargs):
            return reply

    rec = compare.compare_pair(FakeChat(), ENTRY, MATCH, ARTICLE, work)
    assert rec["status"] == "ok" and rec["cite_wikipedia"] == "[W:123:456]"
    assert (work / "compare" / "raw" / "B_7_0.json").exists()
    summary = compare.drift_summary(work)
    assert summary["pairs"] == 1 and summary["claim_shares"]["enduring"] == 1.0
    assert (work / "compare" / "drift.png").exists()

    pair = agent_tools.get_pair("[B:7:0]", work)
    assert pair["status"] == "matched" and pair["cite_wikipedia"] == "[W:123:456]"
    assert pair["uncertain_match"] is True and pair["drift"]["claims_checked"] == 1


def test_compare_pair_logs_failed_model_call(work):
    from nemotron_challenge.clients import ServiceError

    class Broken:
        def complete(self, *args, **kwargs):
            raise ServiceError("boom", status_code=500)

    (work / "compare").mkdir()
    rec = compare.compare_pair(Broken(), ENTRY, MATCH, ARTICLE, work, attempts=1)
    assert rec["status"] == "error"
    assert not (work / "compare" / "pairs" / "B_7_0.json").exists()
    assert "boom" in (work / "compare" / "failures.jsonl").read_text()


def test_get_pair_unknown_and_view_scan_crop(work):
    assert "error" in agent_tools.get_pair("B:9:9", work)
    meta, data = agent_tools.view_scan("B:7:0", [0.0, 0.0, 0.5, 0.5], work)
    assert meta["row_index"] == 7 and data[:2] == b"\xff\xd8"
    with pytest.raises(ValueError):
        agent_tools.view_scan("7", [0.5, 0.5, 0.1, 0.1], work)


def test_runner_summary_pairs_tool_calls_with_results():
    events = [{"type": "system", "subtype": "init", "model": "nvidia/Nemotron-3.5-Super-VL"},
              {"type": "tool_use", "name": "get_pair", "input": {"entry_id": "B:1:0"}},
              {"type": "tool_result", "name": "get_pair", "output": "{}"},
              {"type": "result", "session_id": "s", "text": "answer [B:1:0]"}]
    s = summarize(events)
    assert s["model_ok"] and s["completed"] and s["tool_calls"][0]["output"] == "{}"
    assert slug("Did the Language change?") == "did-the-language-change"


def test_spelling_like_separates_ocr_from_new_terms():
    assert compare.spelling_like("prisoners of var", "prisoners of war")
    assert not compare.spelling_like("electric fire", "electric charge")
    assert not compare.spelling_like("fixed air", "carbon dioxide")


def test_find_drift_lists_items_with_both_citations(work):
    reply = {"model": "m", "usage": {}, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
        "term_pairs": [{"old": "fixed air", "new": "carbon dioxide", "quote_britannica": "Fixed air is found",
                        "quote_wikipedia": "Carbon dioxide is a chemical"}]})}}]}

    class FakeChat:
        def complete(self, *args, **kwargs):
            return reply

    compare.compare_pair(FakeChat(), ENTRY, MATCH, ARTICLE, work)
    out = agent_tools.find_drift("term_pairs", 5, work)
    assert out["total"] == 1 and out["items"][0]["cite_wikipedia"] == "[W:123:456]"
    with pytest.raises(ValueError):
        agent_tools.find_drift("other", 5, work)
