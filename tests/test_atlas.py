import json

import numpy as np

from nemotron_challenge.atlas import agreement, build_page


def _vec(*hot):
    v = np.zeros(8, dtype=np.float32)
    for i, w in hot:
        v[i] = w
    return v


def test_agreement_counts_own_entry_and_matched_article():
    ids = ["S:1", "S:2", "B:1:0", "B:2:0", "W:10:5:0", "W:20:6:0"]
    kinds = ["scan_image", "scan_image", "britannica_entry", "britannica_entry", "wikipedia_chunk", "wikipedia_chunk"]
    vectors = np.stack([_vec((0, 1)), _vec((0, 1), (1, .2)),  # both scans nearest to B:1:0
                        _vec((0, 1), (2, .1)), _vec((3, 1)), _vec((2, 1), (0, .9)), _vec((3, 1), (4, .5))])
    stats = agreement(ids, kinds, vectors, {"B:1:0": "10", "B:2:0": "10"})
    assert stats["scan_to_entry"]["n"] == 2 and stats["scan_to_entry"]["share"] == 0.5
    assert stats["scan_to_entry"]["chance"] == 0.5
    assert stats["entry_to_wiki"] == {"n": 2, "share": 0.5}


def test_build_page_inlines_data_and_escapes_script(tmp_path):
    work = tmp_path / "artifacts"
    (work / "atlas" / "thumbs").mkdir(parents=True)
    (work / "atlas" / "thumbs" / "scan_1.jpg").write_bytes(b"\xff\xd8\xff")
    ids = ["S:1", "B:1:0"]
    np.savez_compressed(work / "atlas" / "vectors.npz", vectors=np.stack([_vec((0, 1)), _vec((0, 1), (1, .1))]))
    (work / "atlas" / "ids.json").write_text(json.dumps({"ids": ids, "kinds": ["scan_image", "britannica_entry"]}))
    points = [{"id": "S:1", "kind": "scan_image", "x": 0, "y": 0, "row": 1, "thumb": "thumbs/scan_1.jpg", "label": "Page 1"},
              {"id": "B:1:0", "kind": "britannica_entry", "x": 1, "y": 1, "row": 1, "label": "</script><b>X", "excerpt": "e"}]
    (work / "atlas" / "points.json").write_text(json.dumps({"points": points, "edges": [], "clusters": {}}))
    agree = {"scan_to_entry": {"n": 1, "share": 1.0, "chance": 0.5, "entries": 1}, "entry_to_wiki": {"n": 0, "share": 0.0}}
    (work / "atlas" / "summary.json").write_text(json.dumps({"model": "m", "model_revision": "r" * 40, "umap": {"seed": 1},
                                                             "agreement": agree}))
    result = build_page(work, tmp_path / "site")
    html = (tmp_path / "site" / "atlas.html").read_text()
    assert "One space for pictures and words" in html and "data:image/jpeg;base64," in html
    assert "</script><b>X" not in html
    assert result["tours"] == []
