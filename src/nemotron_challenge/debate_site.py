"""Build site/debate.html: a chat replay of the saved time-travel debates (artifacts/debate/*.json)."""
from __future__ import annotations

import html
import json
from pathlib import Path
import re
import shutil
import time
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .debate import CITE, ROLES, TAGS, Sources
from .site import TEMPLATES, revision_url

LABELS = {"scholar": "The Scholar of 1790", "wikipedian": "The Wikipedian", "judge": "The Judge"}
STAGES = {"opening": "Opening statement", "rebuttal": "Rebuttal", "verdict": "Verdict"}
CITE_IN_TEXT = re.compile(r"\[((?:[BW]:\d+:\d+(?::\d+)?)(?:\s*[,;]\s*[BW]:\d+:\d+(?::\d+)?)*)\]|\b([BW]:\d+:\d+(?::\d+)?)\b")


def winner_of(text: Any) -> str:
    t = str(text or "").lower()
    if "scholar" in t or "britannica" in t or "1790" in t:
        return "scholar"
    if "wikipedia" in t:
        return "wikipedian"
    return "draw"


def clean(text: str) -> str:
    lines = [l for l in (text or "").splitlines() if not re.match(r"\s*(session_id:|word count)", l, re.I)]
    return "\n".join(lines).strip()


def _inline(text: str) -> str:
    """Escape, then turn **bold** into <strong> and citation ids into data-cite pills."""
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)\*(?!\w)", r"<em>\1</em>", out)

    def pill(m: re.Match) -> str:
        ids = re.findall(r"[BW]:\d+:\d+(?::\d+)?", m.group(0))
        return "".join(f'<a class="cite" data-cite="{i}">{i}</a>' for i in ids)

    return CITE_IN_TEXT.sub(pill, out)


def _ref(text: str) -> str:
    """Citation pills without a check mark: the judge's flags and inferences are not checked sentence by sentence."""
    return _inline(str(text)).replace('class="cite" data-cite=', 'class="cite" data-st="ref" data-cite=')


def render_text(text: str, checks: list[dict[str, Any]]) -> str:
    """HTML for one turn: paragraphs, sentences marked with their check status, words wrapped for the typing replay."""
    status = {c["sentence"]: c for c in checks}
    paras = []
    for para in re.split(r"\n\s*\n", clean(text)):
        para = re.sub(r"^\s*[-*]\s+", "• ", para, flags=re.M).replace("\n", " ")
        from .debate import sentences

        parts = []
        for sent in sentences(para) or [para]:
            body = _inline(sent)
            c = status.get(sent)
            if sent.lower().startswith("inference"):
                body = f'<span class="infer">{body}</span>'
            if c:
                body = body.replace('class="cite" data-cite=', f'class="cite" data-st="{c["status"]}" data-cite=')
                tip = html.escape(f"{c['status']}: {c['why']}")
                body = f'<span class="s {c["status"]}" title="{tip}">{body}</span>'
            parts.append(body)
        paras.append("<p>" + " ".join(parts) + "</p>")
    return wrap_words("".join(paras))


def wrap_words(markup: str) -> str:
    """Wrap each visible word (and each citation pill) in <i class="w"> so the replay can reveal them one by one."""
    out, i = [], 0
    for m in re.finditer(r"<a class=\"cite\"[^>]*>.*?</a>|<[^>]+>|[^<\s]+|\s+", markup):
        tok = m.group(0)
        if tok.startswith("<a class=\"cite\""):
            out.append(f'<i class="w">{tok}</i>')
        elif tok.startswith("<") or tok.isspace():
            out.append(tok)
        else:
            out.append(f'<i class="w">{tok}</i>')
        i += 1
    return "".join(out)


def tool_summary(call: dict[str, Any]) -> dict[str, Any]:
    name, args, res = call.get("tool"), call.get("params") or {}, call.get("result") or {}
    if not isinstance(res, dict):
        res = {}
    if name == "search_sources":
        hits = res.get("results") or []
        detail = f"{len(hits)} hits" + (f", top {hits[0].get('cite')}" if hits else "")
        arg = f"“{args.get('query', '')}” · {args.get('side', 'both')}"
    elif name == "get_pair":
        arg, detail = args.get("entry_id", ""), (res.get("match") or {}).get("status") or "pair loaded"
    elif name == "view_scan":
        arg, detail = str(args.get("page", "")), "Super VL read the original scan"
    else:
        arg, detail = json.dumps(args)[:60], ""
    err = res.get("error") if isinstance(res, dict) else None
    return {"name": name, "arg": str(arg)[:80], "detail": err or detail, "error": bool(err),
            "page": str(args.get("page", "")) if name == "view_scan" else None}


def crop_for(entry_id: str, work_dir: Path, out: Path) -> str | None:
    """Save a crop of the first lines of a Britannica entry; return its site path."""
    from .agent_tools import view_scan

    dst = out / f"{entry_id.replace(':', '_')}.jpg"
    if dst.exists():
        return f"debate/{dst.name}"
    src = Sources(work_dir).entries.get(entry_id)
    if not src or not src.get("bboxes"):
        return None
    boxes = src["bboxes"][:3]
    box = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    try:
        _, data = view_scan(entry_id, box, work_dir=work_dir, max_side=560)
        dst.write_bytes(data)
        return f"debate/{dst.name}"
    except (OSError, ValueError):
        return None


def page_thumb(row: str, work_dir: Path, out: Path) -> str | None:
    from .agent_tools import view_scan

    dst = out / f"page-{row}.jpg"
    if not dst.exists():
        try:
            _, data = view_scan(row, None, work_dir=work_dir, max_side=420)
        except (OSError, ValueError):
            return None
        dst.write_bytes(data)
    return f"debate/{dst.name}"


def build(work_dir: Path, site_dir: Path) -> dict[str, Any]:
    out = site_dir / "debate"
    out.mkdir(parents=True, exist_ok=True)
    src = Sources(work_dir)
    articles: dict[str, dict[str, Any]] = {}
    cites: dict[str, dict[str, Any]] = {}
    debates = []
    for topic in __import__("nemotron_challenge.debate", fromlist=["TOPICS"]).TOPICS:
        path = work_dir / "debate" / f"{topic['slug']}.json"
        if not path.exists():
            continue
        rec = json.loads(path.read_text())
        steps, score = [], {"scholar": 0, "wikipedian": 0, "draw": 0}
        for turn in rec["turns"]:
            for c in turn.get("checks", []):
                for cid in c["cites"]:
                    entry = cites.setdefault(cid, {"quotes": [], "status": c["status"]})
                    entry["quotes"] += [q for q, ok in zip(c["quotes"], c["quotes_ok"]) if ok and q not in entry["quotes"]]
                    if c["status"] == "unverified":
                        entry["status"] = "unverified"
            tools = [tool_summary(t) for t in turn.get("tool_log", [])]
            for t in tools:
                if t["page"]:
                    m = re.search(r"\d+", t["page"].split(":")[1] if t["page"].startswith("B:") else t["page"])
                    t["img"] = page_thumb(m.group(0), work_dir, out) if m else None
            base = {"role": turn["role"], "stage": turn["stage"], "label": LABELS[turn["role"]],
                    "stage_label": STAGES[turn["stage"]], "status": turn["status"], "tools": tools,
                    "seconds": turn.get("seconds"), "tokens": (turn.get("tokens") or {}).get("total"),
                    "error": turn.get("error") or (turn.get("stderr", "")[-300:] if turn["status"] != "ok" else None),
                    "checks": {k: sum(c["status"] == k for c in turn.get("checks", [])) for k in ("verified", "cited", "unverified", "echo")}}
            v = turn.get("verdict") if turn["role"] == "judge" else None
            if turn["role"] != "judge" or not v:
                steps.append({**base, "kind": "turn", "html": render_text(turn.get("final_text") or "", turn.get("checks", []))})
                continue
            by_sentence = {c["sentence"]: c for c in turn.get("checks", [])}
            for i, p in enumerate(v["points"]):
                ruling = p.get("ruling") if p.get("ruling") in TAGS else "dropped"
                w = winner_of(p.get("winner"))
                score[w] += 1
                steps.append({**base, "kind": "point", "n": i + 1, "point": p.get("point", ""), "ruling": ruling,
                              "winner": w, "html": render_text(p.get("why", ""), list(by_sentence.values())),
                              "score": dict(score), "tools": tools if i == 0 else []})
            steps.append({**base, "kind": "final", "winner": winner_of(v.get("overall_winner")), "tools": [],
                          "html": render_text(v.get("overall_why", ""), list(by_sentence.values())),
                          "flags": [_ref(f) for f in v.get("flags") or []],
                          "inferences": [_ref(f) for f in v.get("inferences") or []], "score": dict(score)})
        eid = topic["entry_id"]
        pair = json.loads((work_dir / "compare" / "pairs" / f"{eid.replace(':', '_')}.json").read_text())
        row = eid.split(":")[1]
        ver = rec.get("verification") or {}
        debates.append({**topic, "row": row, "crop": crop_for(eid, work_dir, out), "thumb": page_thumb(row, work_dir, out),
                        "wiki_title": pair.get("wiki_title"), "wiki_url": revision_url(pair.get("wiki_revision_id")),
                        "cite_w": pair.get("cite_wikipedia"), "steps": steps, "final_score": score,
                        "stats": {"tokens": sum((t.get("tokens") or {}).get("total") or 0 for t in rec["turns"]),
                                  "seconds": rec.get("seconds"), "tool_calls": sum(len(t.get("tool_log", [])) for t in rec["turns"]),
                                  "turns_ok": sum(t["status"] == "ok" for t in rec["turns"]), "turns": len(rec["turns"]),
                                  **{k: ver.get(k) for k in ("verified", "cited", "unverified", "claims", "verified_share", "grounded_share")}},
                        "file": f"artifacts/debate/{topic['slug']}.json"})
    for cid, c in cites.items():
        kind, a, b = cid.split(":")[:3]
        if cid.count(":") > 2:
            c.update({"kind": kind, "href": None, "title": "Malformed citation id", "resolves": False, "img": None,
                      "sub": "an extra chunk number; the tools never issue this form"})
            continue
        if kind == "B":
            e = src.entries.get(cid)
            c.update({"kind": "B", "href": f"pages/{a}.html", "title": (e or {}).get("headword") or (e or {}).get("running_head") or f"Row {a}",
                      "sub": f"Britannica scan row {a}, entry {b}", "img": crop_for(cid, work_dir, out) if e else None,
                      "resolves": e is not None})
        else:
            art = work_dir / "match" / "articles" / f"{a}.json"
            title = json.loads(art.read_text())["title"] if art.exists() else None
            c.update({"kind": "W", "href": revision_url(b), "title": title or f"Wikipedia page {a}",
                      "sub": f"page {a}, revision {b}", "img": None, "resolves": True})
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    env.filters["tojson_safe"] = lambda value: Markup(json.dumps(value, ensure_ascii=False).replace("<", "\\u003c"))
    for asset in ("debate.css", "debate.js"):
        shutil.copy2(TEMPLATES / asset, site_dir / asset)
    page = env.get_template("debate.html").render(root="", active="debate.html", built=time.strftime("%Y-%m-%d %H:%M"),
                                                  data={"debates": debates, "cites": cites})
    (site_dir / "debate.html").write_text(page)
    return {"page": str(site_dir / "debate.html"), "debates": len(debates), "citations": len(cites)}
