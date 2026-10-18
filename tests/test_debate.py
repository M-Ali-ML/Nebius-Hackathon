import json
from pathlib import Path

from nemotron_challenge.debate import check_turn, parse_verdict, Sources
from nemotron_challenge.debate_site import render_text, winner_of


def _sources(tmp_path: Path) -> Sources:
    (tmp_path / "extract").mkdir()
    entry = {"entry_id": "B:7:0", "text_raw": "Lightning is the returning ftroke of electric fire.",
             "text_norm": "Lightning is the returning ftroke of electric fire."}
    (tmp_path / "extract" / "entries.jsonl").write_text(json.dumps(entry) + "\n")
    (tmp_path / "match" / "articles").mkdir(parents=True)
    (tmp_path / "match" / "articles" / "61344.json").write_text(
        json.dumps({"revision_id": 99, "text": "Lightning is a natural phenomenon of electrostatic discharge."}))
    return Sources(tmp_path)


def test_check_turn_statuses(tmp_path):
    src = _sources(tmp_path)
    text = ('Sir, it is "the returning ftroke of electric fire" [B:7:0]. '
            'Pray observe "a bolt sent by Jupiter himself" [B:7:0]. '
            'It is "a natural phenomenon of electrostatic discharge" [W:61344:99]. '
            'The page says more [W:61344:12]. '
            'Your "electric fire" is old [W:61344:99:3]. '
            'Your "returning ftroke" is a typo.')
    rows = check_turn(text, src, tool_text="", others='the "returning ftroke"')
    assert [r["status"] for r in rows] == ["verified", "unverified", "verified", "unverified", "unverified", "echo"]
    assert "malformed" in rows[4]["why"]


def test_verdict_parse_and_render():
    v = parse_verdict('ok {"points": [{"point": "x", "ruling": "superseded", "winner": "Wikipedian"}], "overall_winner": "The Scholar"}')
    assert v and v["points"][0]["ruling"] == "superseded"
    assert parse_verdict("no json here") is None
    assert winner_of("The Wikipedian") == "wikipedian" and winner_of("Scholar of 1790") == "scholar" and winner_of("tie") == "draw"
    html = render_text('It is "x <b>" [B:7:0].', [])
    assert 'data-cite="B:7:0"' in html and "<b>" not in html and 'class="w"' in html
