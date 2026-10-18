import json

from PIL import Image

from nemotron_challenge.site import build_site


def _work_dir(tmp_path, with_matches):
    work = tmp_path / "artifacts"
    (work / "extract" / "pages").mkdir(parents=True)
    scan = tmp_path / "scan.jpg"
    Image.new("RGB", (60, 90), "white").save(scan)
    record = {"page_id": "britannica:x:7", "row_index": 7, "image_sha256": "abc", "filename": "scan.jpg",
              "scan_path": str(scan), "width": 60, "height": 90, "parse_model": "nvidia/nemotron-3.5-parse",
              "finish_reason": "stop", "blocks": [
                  {"order": 0, "cls": "Page-header", "bbox": [0.3, 0.01, 0.7, 0.04], "text": "ANATOMY."},
                  {"order": 1, "cls": "Text", "bbox": [0.05, 0.1, 0.95, 0.5], "text": "ANATOMY, the art <of> dissecting."}]}
    (work / "extract" / "pages" / "7.json").write_text(json.dumps(record))
    entry = {"entry_id": "B:7:0", "page_id": "britannica:x:7", "row_index": 7, "headword": "ANATOMY",
             "is_continuation": False, "block_orders": [1], "bboxes": [[0.05, 0.1, 0.95, 0.5]],
             "text_raw": "ANATOMY, the art of dissecting.", "text_norm": "", "norm_edits": 0, "chars": 30}
    (work / "extract" / "entries.jsonl").write_text(json.dumps(entry) + "\n")
    if with_matches:
        (work / "match").mkdir()
        match = {"entry_id": "B:7:0", "status": "no_clear_counterpart", "wiki_page_id": 1, "wiki_title": "Anatomy",
                 "wiki_revision_id": 9, "wiki_url": "https://en.wikipedia.org/wiki/Anatomy", "text_sha256": "x",
                 "bm25_rank": 1, "embed_cos": 0.5, "rerank_logit": -1.2, "rerank_margin": 0.1,
                 "method": "bm25+embed+rerank", "reason": "low logit"}
        (work / "match" / "matches.jsonl").write_text(json.dumps(match) + "\n")
    return work


def test_site_renders_without_match_output(tmp_path):
    work = _work_dir(tmp_path, with_matches=False)
    result = build_site(work)
    site = tmp_path / "site"
    page = (site / "pages" / "7.html").read_text()
    assert result["pages"] == 1 and result["matches"] == 0
    assert "Match output is not available yet" in page
    assert "the art &lt;of&gt; dissecting" in page  # source text is escaped
    assert (site / "scans" / "scan.jpg").is_file() and (site / "analysis.html").is_file()
    assert 'href="pages/7.html"' in (site / "index.html").read_text()


def test_site_marks_no_clear_counterpart_as_uncertain(tmp_path):
    work = _work_dir(tmp_path, with_matches=True)
    build_site(work)
    page = (tmp_path / "site" / "pages" / "7.html").read_text()
    assert "uncertain: no clear counterpart" in page
    assert "rerank -1.20" in page and 'data-orders="1"' in page


def test_page_drift_counts_tags_and_picks_varied_examples():
    from nemotron_challenge.site import page_drift, reason_group
    pair = {"cite_britannica": "[B:7:0]", "cite_wikipedia": "[W:1:9]", "model": "m", "claims": [
        {"claim": "a", "tag": "enduring", "quote_britannica": "x", "quote_wikipedia": "y"},
        {"claim": "b", "tag": "enduring", "quote_britannica": "x", "quote_wikipedia": "y"},
        {"claim": "c", "tag": "superseded", "quote_britannica": "x", "quote_wikipedia": "y"}],
        "term_pairs": [{"old": "gulph", "new": "gulf"}]}
    drift = page_drift([{"pair": pair}, {"pair": None}])
    assert drift["counts"] == {"enduring": 2, "renamed": 0, "superseded": 1, "dropped": 0}
    assert [c["claim"] for c in drift["examples"]] == ["c", "a", "b"]
    assert drift["terms"][0]["cite_b"] == "[B:7:0]"
    assert page_drift([{"pair": None}]) is None
    assert reason_group("top rerank logit -6.67 below the acceptance rules") == "rerank logit below the acceptance rules"


def test_explore_rows_link_both_sources_and_flag_ocr_terms(tmp_path):
    from nemotron_challenge.site import explore_rows
    pairs = tmp_path / "compare" / "pairs"
    pairs.mkdir(parents=True)
    pair = {"cite_britannica": "[B:7:0]", "cite_wikipedia": "[W:1:9]", "row_index": 7, "headword": "ANATOMY",
            "wiki_title": "Anatomy", "wiki_revision_id": "9",
            "claims": [{"claim": "c", "tag": "renamed", "quote_britannica": "x", "quote_wikipedia": "y"},
                       {"claim": "z", "tag": "bogus"}],
            "term_pairs": [{"old": "anatomie", "new": "anatomy"}, {"old": "gulph", "new": "gulf"}],
            "drift": {"lexical": {"likely_ocr_or_spelling": [{"old": "gulph", "new": "gulf"}]}}}
    (pairs / "B_7_0.json").write_text(json.dumps(pair))
    claims, terms = explore_rows(tmp_path)
    assert len(claims) == 1 and claims[0]["rev"] == "https://en.wikipedia.org/w/index.php?oldid=9"
    assert claims[0]["row"] == 7 and claims[0]["tag"] == "renamed"
    assert [t["ocr"] for t in terms] == [False, True]


def test_site_shows_uncertainty_cause_in_inspector_and_index(tmp_path):
    work = _work_dir(tmp_path, with_matches=True)
    cause = {"id": "B:7:0", "level": "entry", "cause": "pool_miss", "note": "never retrieved Anatomy"}
    (work / "match" / "uncertainty.jsonl").write_text(json.dumps(cause) + "\n")
    page_match = {"row_index": 7, "status": "no_clear_counterpart", "page_kind": "dictionary",
                  "uncertainty_cause": "threshold_miss", "uncertainty_note": "top 1 below tau"}
    (work / "match" / "page_matches.jsonl").write_text(json.dumps(page_match) + "\n")
    build_site(work)
    page = (tmp_path / "site" / "pages" / "7.html").read_text()
    index = (tmp_path / "site" / "index.html").read_text()
    assert "candidate pool miss" in page and "never retrieved Anatomy" in page
    assert "threshold miss" in page and "top 1 below tau" in page
    assert 'data-filter="cause-threshold_miss"' in index and "cause-threshold_miss" in index
