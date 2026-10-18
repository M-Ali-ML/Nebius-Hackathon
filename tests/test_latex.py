import json

from PIL import Image

from nemotron_challenge.latex import escape, join_lines, page_tex, table_rows, two_columns


def test_escape_special_and_unknown_chars():
    unknown = []
    out = escape("50% of $x & {y} #1 ſ 发", unknown)
    assert r"50\% of \$x \& \{y\} \#1 s \unk{53D1}" == out
    assert unknown == ["发"]


def test_join_hyphenated_line_breaks():
    assert join_lines("ana-\ntomy and\nmore") == "anatomy and more"


def test_table_rows_drop_tabular_commands():
    rows = table_rows("\\begin{tabular}{cc}\n**A** & B\\\\\n1 & 2\\\\\n\\end{tabular}")
    assert rows == [["**A**", "B"], ["1", "2"]]


def test_two_columns_needs_both_halves():
    left = {"cls": "Text", "bbox": [0.05, 0.1, 0.45, 0.5]}
    right = {"cls": "Text", "bbox": [0.55, 0.1, 0.95, 0.5]}
    assert two_columns([left, right]) and not two_columns([left])


def test_page_tex_keeps_reading_order_and_provenance(tmp_path):
    scan = tmp_path / "scan.jpg"
    Image.new("RGB", (100, 100), "white").save(scan)
    record = {"page_id": "britannica:x:1", "row_index": 1, "image_sha256": "abc", "filename": "scan.jpg",
              "scan_path": str(scan), "parse_model": "nvidia/nemotron-3.5-parse", "finish_reason": "stop",
              "blocks": [
                  {"order": 0, "cls": "Page-header", "bbox": [0.3, 0.01, 0.7, 0.04], "text": "ANATOMY."},
                  {"order": 1, "cls": "Section-header", "bbox": [0.05, 0.1, 0.45, 0.12], "text": "Bones"},
                  {"order": 2, "cls": "Text", "bbox": [0.05, 0.13, 0.45, 0.5], "text": "First & left."},
                  {"order": 3, "cls": "Picture", "bbox": [0.55, 0.1, 0.95, 0.4], "text": ""},
                  {"order": 4, "cls": "Footnote", "bbox": [0.55, 0.9, 0.95, 0.95], "text": "A note."},
              ]}
    tex, stats = page_tex(record, tmp_path)
    assert stats["two_column"] and stats["pictures"] == 1
    assert "\\fancyhead[C]{\\small ANATOMY.}" in tex
    assert tex.index("\\subsection*{Bones}") < tex.index("First \\& left.") < tex.index("img/1-3.jpg")
    assert tex.index("img/1-3.jpg") < tex.index("A note.")
    assert "britannica:x:1" in tex and "abc" in tex
    assert (tmp_path / "latex" / "img" / "1-3.jpg").is_file()
    json.dumps(stats)
