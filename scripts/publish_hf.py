"""Build and publish the Hugging Face Space and dataset for the team project.

Usage (from the repo root):

    uv run python scripts/publish_hf.py check             # token and org membership
    uv run python scripts/publish_hf.py build             # write build/hf/space and build/hf/dataset
    uv run python scripts/publish_hf.py screenshots       # refresh docs/hf/img/*.png with headless Chrome
    uv run python scripts/publish_hf.py publish           # build, upload both repos, verify
    uv run python scripts/publish_hf.py verify            # Space runtime + dataset viewer checks

Options: --root <checkout with artifacts/, runs/, site/> (default: this repo).
The script is idempotent: create_repo(exist_ok=True), then upload_folder with stale files removed.
HF_TOKEN comes from .env. The script never prints it.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from string import Template

ORG = "nebius-build-week"
SPACE_ID = f"{ORG}/britannica-across-time"
DATASET_ID = f"{ORG}/britannica-wikipedia-drift"
GITHUB = "https://github.com/M-Ali-ML/Nebius-Hackathon"
SPACE_URL = f"https://huggingface.co/spaces/{SPACE_ID}"
SPACE_APP_URL = "https://nebius-build-week-britannica-across-time.static.hf.space"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET_ID}"

REPO = Path(__file__).resolve().parents[1]
CARDS = REPO / "docs" / "hf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CASE_RE = re.compile(r"^Classification:\s*(\w+)", re.M)
RUN_RE = re.compile(r"runs/agent/[\w./-]+?\.json")


def token() -> str:
    tok = os.environ.get("HF_TOKEN")
    if not tok:
        env = REPO / ".env"
        for line in env.read_text().splitlines() if env.exists() else []:
            if line.startswith("HF_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip("'\"")
    if not tok:
        sys.exit("HF_TOKEN is not set in the environment or .env")
    return tok


def api():
    from huggingface_hub import HfApi

    return HfApi(token=token())


# ---------- dataset rows ----------


def clean(v):
    """Replace NaN and inf with None so every column has one JSON type."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [clean(x) for x in v]
    return v


def jl(path: Path):
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(clean(r), ensure_ascii=False) + "\n")
    return len(rows)


def as_json(v):
    return None if v in (None, {}, []) else json.dumps(clean(v), ensure_ascii=False)


def entries_rows(root: Path):
    keep = ["entry_id", "page_id", "row_index", "image_sha256", "headword", "is_continuation", "plate",
            "running_head", "topic_hint", "block_orders", "bboxes", "text_raw", "text_norm", "norm_edits", "chars"]
    return [{k: e.get(k) for k in keep} for e in jl(root / "artifacts/extract/entries.jsonl")]


MATCH_COLS = ["id", "level", "row_index", "page_id", "entry_ids", "headword", "page_kind", "page_topic",
              "status", "wiki_page_id", "wiki_title", "wiki_revision_id", "wiki_url", "text_sha256",
              "bm25_rank", "embed_cos", "rerank_logit", "rerank_margin", "method", "tau", "rule",
              "title_relation", "shared_terms", "reason", "why", "uncertainty_cause", "uncertainty_label",
              "uncertainty_note", "likely_article", "vision_expand_json"]


def matches_rows(root: Path):
    m = root / "artifacts/match"
    unc = {u["id"]: u for u in jl(m / "uncertainty.jsonl")}
    heads = {e["entry_id"]: e.get("headword") for e in jl(root / "artifacts/extract/entries.jsonl")}
    rows = []
    for r in jl(m / "matches.jsonl"):
        u = unc.get(r["entry_id"], {})
        rows.append({**r, "id": r["entry_id"], "level": "entry", "entry_ids": [r["entry_id"]],
                     "headword": heads.get(r["entry_id"]), "row_index": int(r["entry_id"].split(":")[1]),
                     "uncertainty_cause": u.get("cause"), "uncertainty_label": u.get("cause_label"),
                     "uncertainty_note": u.get("note"), "likely_article": u.get("right_article")})
    for r in jl(m / "page_matches.jsonl"):
        u = unc.get(r["entry_id"], {})
        rows.append({**r, "id": r["entry_id"], "level": "page",
                     "uncertainty_cause": r.get("uncertainty_cause") or u.get("cause"),
                     "uncertainty_label": u.get("cause_label"),
                     "uncertainty_note": r.get("uncertainty_note") or u.get("note"),
                     "likely_article": u.get("right_article"),
                     "vision_expand_json": as_json(r.get("vision_expand"))})
    out = []
    for r in rows:
        row = {k: r.get(k) for k in MATCH_COLS}
        for k in ("wiki_page_id", "wiki_revision_id", "rule"):
            row[k] = None if row[k] is None else str(row[k])
        for k in ("embed_cos", "rerank_logit", "rerank_margin", "tau"):
            row[k] = None if row[k] is None else float(row[k])
        out.append(row)
    return out


def candidates_rows(root: Path):
    rows = []
    for f in sorted(glob.glob(str(root / "artifacts/match/candidates/*.json"))):
        d = json.load(open(f))
        for h in d["hits"]:
            rows.append({"entry_id": d["entry_id"], "headword": d.get("headword"), "plate": d.get("plate"),
                         "bm25_query": d.get("bm25_query"), "wiki_page_id": str(h["page_id"]),
                         "wiki_revision_id": str(h["revision_id"]), "wiki_title": h["title"], "wiki_url": h["url"],
                         "text_sha256": h["text_sha256"], "bm25_rank": h["bm25_rank"],
                         "bm25_score": float(h["bm25_score"]), "headword_rank": h.get("headword_rank"),
                         "embed_cos": h.get("embed_cos"),
                         "rerank_logit": None if h.get("rerank_logit") is None else float(h["rerank_logit"]),
                         "excerpt": h["excerpt"], "excerpt_offset": h.get("excerpt_offset"),
                         "article_chars": h.get("total_chars")})
    return rows


def pair_files(root: Path):
    return [json.load(open(f)) for f in sorted(glob.glob(str(root / "artifacts/compare/pairs/*.json")))]


def pair_base(p):
    return {"entry_id": p["entry_id"], "level": p.get("level", "entry"), "headword": p.get("headword"),
            "cite_britannica": p["cite_britannica"], "cite_wikipedia": p["cite_wikipedia"],
            "wiki_title": p["wiki_title"], "wiki_page_id": str(p["wiki_page_id"]),
            "wiki_revision_id": str(p["wiki_revision_id"]), "wiki_url": p["wiki_url"]}


def claims_rows(root: Path):
    rows = []
    for p in pair_files(root):
        for c in p.get("claims", []):
            rows.append({**pair_base(p), "claim": c.get("claim"), "tag": c.get("tag"),
                         "quote_britannica": c.get("quote_britannica"), "quote_wikipedia": c.get("quote_wikipedia"),
                         "quote_check": "passed", "reject_reason": None})
        for r in p.get("rejected", []):
            if r.get("section") == "claims":
                c = r.get("item", {})
                rows.append({**pair_base(p), "claim": c.get("claim"), "tag": c.get("tag"),
                             "quote_britannica": c.get("quote_britannica"),
                             "quote_wikipedia": c.get("quote_wikipedia"),
                             "quote_check": "failed", "reject_reason": r.get("reason")})
    return rows


def term_pair_rows(root: Path):
    rows = []
    for p in pair_files(root):
        noisy = {(t["old"], t["new"]) for t in p.get("drift", {}).get("lexical", {}).get("likely_ocr_or_spelling", [])}
        for t in p.get("term_pairs", []):
            rows.append({**pair_base(p), "old": t.get("old"), "new": t.get("new"),
                         "likely_ocr": (t.get("old"), t.get("new")) in noisy,
                         "quote_britannica": t.get("quote_britannica"), "quote_wikipedia": t.get("quote_wikipedia")})
    return rows


def comparison_rows(root: Path):
    rows = []
    for p in pair_files(root):
        d = p.get("drift", {})
        rows.append({**pair_base(p), "model": p.get("model"), "finish_reason": p.get("finish_reason"),
                     "prompt_version": p.get("prompt_version"), "rerank_logit": p.get("rerank_logit"),
                     "rerank_margin": p.get("rerank_margin"),
                     "similarities": p.get("similarities", []), "differences": p.get("differences", []),
                     "wiki_only_topics": p.get("wiki_only_topics", []),
                     "quotes_kept": p.get("quote_check", {}).get("kept"),
                     "quotes_rejected": p.get("quote_check", {}).get("rejected"),
                     "orthographic_edits_per_100_words": d.get("orthographic", {}).get("edits_per_100_words"),
                     "enduring_share": d.get("enduring_share"),
                     "renamed_share": d.get("lexical", {}).get("renamed_share"),
                     "superseded_share": d.get("knowledge", {}).get("superseded_share"),
                     "dropped_share": d.get("coverage", {}).get("dropped_share"),
                     "claim_counts": d.get("claim_counts")})
    return rows


def label_rows(root: Path):
    m = root / "artifacts/match"
    preds = {a["entry_id"]: a for a in jl(m / "ablation.jsonl")}
    methods = ["bm25", "bm25+embed", "bm25+embed+rerank", "bm25+embed+rerank_short"]
    rows = []
    for lab in jl(m / "labels.jsonl"):
        p = preds.get(lab["entry_id"], {})
        row = {k: lab.get(k) for k in ("entry_id", "has_counterpart", "gold_titles", "gold_in_pool", "note",
                                         "origin", "labeler")}
        row["gold_page_ids"] = [str(x) for x in lab.get("gold_page_ids", [])]
        for meth in methods:
            top = p.get(meth) or {}
            key = meth.replace("+", "_")
            row[f"top1_{key}"] = top.get("title")
            row[f"correct_{key}"] = (str(top.get("page_id")) in row["gold_page_ids"]) if lab["has_counterpart"] else None
        rows.append(row)
    return rows


def ablation_rows(root: Path):
    rows = []
    s = json.load(open(root / "artifacts/match/ablation_summary.json"))
    for meth, v in s.get("methods", {}).items():
        rows.append({"study": "match_retrieval", "method": meth, "n_labels": s.get("labels"),
                     "metrics_json": json.dumps(v)})
    a = root / "runs/agent/ablation/summary.json"
    if a.exists():
        for mode, v in json.load(open(a)).get("by_mode", {}).items():
            rows.append({"study": "agent_search_mode", "method": mode, "n_labels": None,
                         "metrics_json": json.dumps(v)})
    return rows


def strip_images(v):
    if isinstance(v, str):
        if v.startswith("data:image") or (len(v) > 20000 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", v[:20000])):
            return "<image data removed>"
        v = re.sub(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+", "<image data removed>", v)
        # local checkout paths -> repo-relative paths
        v = re.sub(r"/Users/[^/\s\"]+/orca/workspaces/Nebius-Hackathon/[\w.-]+/", "", v)
        return re.sub(r"/Users/[^/\s\"]+/repos/Nebius-Hackathon/", "", v)
    if isinstance(v, dict):
        return {k: strip_images(x) for k, x in v.items()}
    if isinstance(v, list):
        return [strip_images(x) for x in v]
    return v


def case_map(root: Path):
    """Map run file name -> (case id, class, primary) from docs/cases/*.md."""
    out = {}
    for md in sorted((root / "docs/cases").glob("*-*.md")):
        text = md.read_text()
        cls = CASE_RE.search(text)
        record = re.search(r"^Run record:\s*`([^`]+)`", text, re.M)
        for i, run in enumerate(RUN_RE.findall(text)):
            name = Path(run).name
            primary = bool(record and Path(record.group(1)).name == name)
            if name not in out or primary:
                out[name] = (md.stem, cls.group(1).lower() if cls else None, primary)
    return out


def trajectory_rows(root: Path):
    cases = case_map(root)
    files = sorted(glob.glob(str(root / "runs/agent/*.json")))
    files += sorted(glob.glob(str(root / "runs/agent/ablation/*/*.json")))
    rows = []
    for f in files:
        p = Path(f)
        if p.name in ("questions.json", "summary.json"):
            continue
        d = strip_images(json.load(open(p)))
        if not isinstance(d, dict) or "question" not in d:
            continue
        mode = p.parent.name if p.parent.parent.name == "ablation" else None
        case, cls, primary = cases.get(p.name, (None, None, False)) if mode is None else (None, None, False)
        calls = [{"name": c.get("name"), "input_json": json.dumps(c.get("input"), ensure_ascii=False),
                  "output": c.get("output") if isinstance(c.get("output"), str) else json.dumps(c.get("output"))}
                 for c in d.get("tool_calls", [])]
        tok = d.get("tokens") or {}
        rows.append({"run_id": str(p.relative_to(root)), "question": d["question"], "started": d.get("started"),
                     "case_id": case, "case_class": cls, "case_primary_run": primary, "ablation_mode": mode,
                     "model": d.get("model"), "model_ok": d.get("model_ok"), "status": d.get("status"),
                     "completed": d.get("completed"), "exit_code": d.get("exit_code"),
                     "session_id": d.get("session_id"), "tool_calls": calls, "n_tool_calls": len(calls),
                     "final_text": d.get("final_text"), "tokens_input": tok.get("input"),
                     "tokens_output": tok.get("output"), "tokens_total": tok.get("total"),
                     "seconds": d.get("seconds"),
                     "tool_log_json": as_json(d.get("tool_log")), "events_json": as_json(d.get("events"))})
    return rows


def parse_rows(root: Path):
    rows = []
    for f in sorted(glob.glob(str(root / "artifacts/extract/pages/*.json")), key=lambda x: int(Path(x).stem)):
        d = json.load(open(f))
        rows.append({k: d.get(k) for k in ("page_id", "row_index", "volume_id", "filename", "image_sha256",
                                           "width", "height", "parse_model", "finish_reason")}
                    | {"usage_json": as_json(d.get("usage")),
                       "blocks": [{"order": b.get("order"), "cls": b.get("cls"), "bbox": b.get("bbox"),
                                   "text": b.get("text")} for b in d.get("blocks", [])]})
    return rows


CONFIGS = {
    "entries": entries_rows,
    "matches": matches_rows,
    "candidates": candidates_rows,
    "comparisons": comparison_rows,
    "claims": claims_rows,
    "term_pairs": term_pair_rows,
    "retrieval_labels": label_rows,
    "ablation_results": ablation_rows,
    "agent_trajectories": trajectory_rows,
    "parse_pages": parse_rows,
}


def stats(root: Path, counts: dict) -> dict:
    drift = json.load(open(root / "artifacts/compare/drift_summary.json"))
    sh = drift["claim_shares"]
    abl = json.load(open(root / "artifacts/match/ablation_summary.json"))["methods"]
    p1 = [abl[k]["p_at_1_gold_in_pool"] for k in ("bm25", "bm25+embed", "bm25+embed+rerank (long query)")]
    matches = jl(root / "artifacts/match/matches.jsonl")
    pages = jl(root / "artifacts/match/page_matches.jsonl")
    return {
        **{f"n_{k}": v for k, v in counts.items()},
        "pairs": drift["pairs"], "claims_checked": drift["claims_checked"],
        "enduring": f"{sh['enduring']:.0%}", "renamed": f"{sh['renamed']:.0%}",
        "superseded": f"{sh['superseded']:.0%}", "dropped": f"{sh['dropped']:.0%}",
        "quotes_kept": drift["quotes_kept"], "quotes_rejected": drift["quotes_rejected"],
        "p1_bm25": f"{p1[0]:.2f}", "p1_embed": f"{p1[1]:.2f}", "p1_rerank": f"{p1[2]:.2f}",
        "entries_matched": sum(m["status"] == "matched" for m in matches),
        "pages_matched": sum(m["status"] == "matched" for m in pages),
        "space_id": SPACE_ID, "dataset_id": DATASET_ID, "github": GITHUB, "space_url": SPACE_URL,
        "dataset_url": DATASET_URL, "app_url": SPACE_APP_URL,
    }


def build_dataset(root: Path, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    counts = {name: write_jsonl(out / "data" / f"{name}.jsonl", fn(root)) for name, fn in CONFIGS.items()}
    card = Template((CARDS / "dataset_card.md").read_text()).substitute(stats(root, counts))
    (out / "README.md").write_text(card)
    return counts


def build_space(root: Path, out: Path, counts: dict) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(root / "site", out, ignore=shutil.ignore_patterns(".DS_Store", "*.log"))
    shutil.copytree(CARDS / "img", out / "img_card", dirs_exist_ok=True)
    patch_pdf_embeds(out)
    card = Template((CARDS / "space_card.md").read_text()).substitute(stats(root, counts))
    (out / "README.md").write_text(card)


PDF_IFRAME_RE = re.compile(r'(<iframe class="pdf" src=")\.\./(pdf/[\w.-]+\.pdf)(?:#[^"]*)?"')
PDF_LINK_RE = re.compile(r'<a ([^>]*?)href="(\.\./pdf/[\w.-]+\.pdf)"')


def patch_pdf_embeds(out: Path) -> int:
    """Hugging Face shows a Space in a sandboxed iframe, and Chrome blocks its PDF viewer there.
    Point the PDF iframes at pdfview.html (PDF.js) and open PDF links in a new tab, which leaves the sandbox."""
    shutil.copy(CARDS / "pdfview.html", out / "pdfview.html")
    n = 0
    for page in out.glob("**/*.html"):
        text = page.read_text()
        new = PDF_IFRAME_RE.sub(r'\1../pdfview.html?f=\2"', text)
        new = PDF_LINK_RE.sub(r'<a \1href="\2" target="_blank" rel="noopener"', new)
        if new != text:
            page.write_text(new)
            n += 1
    return n


def size(path: Path) -> str:
    n = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    files = sum(1 for f in path.rglob("*") if f.is_file())
    return f"{n / 1e6:.1f} MB in {files} files"


# ---------- commands ----------


def cmd_check(_args) -> bool:
    w = api().whoami()
    member = any(o["name"] == ORG for o in w.get("orgs", []))
    at = w.get("auth", {}).get("accessToken", {})
    perms = [p for s in at.get("fineGrained", {}).get("scoped", []) if s["entity"]["name"] == ORG
             for p in s["permissions"]]
    write = at.get("role") == "write" or "repo.write" in perms
    print(f"user={w['name']} member_of_{ORG}={member} token_role={at.get('role')} org_perms={perms}")
    return member and write


def cmd_build(args):
    root = Path(args.root).resolve()
    out = REPO / "build" / "hf"
    counts = build_dataset(root, out / "dataset")
    build_space(root, out / "space", counts)
    print("dataset:", counts)
    print("dataset size:", size(out / "dataset"))
    print("space size:", size(out / "space"))
    return out


def cmd_screenshots(args):
    root = Path(args.root).resolve()
    img = CARDS / "img"
    img.mkdir(parents=True, exist_ok=True)
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765", "-d", str(root / "site")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.5)
        shots = {"index.png": ("index.html", "1440,1000"), "page.png": (args.page, "1440,1000"),
                 "explore.png": ("explore.html", "1440,1000"), "analysis.png": ("analysis.html", "1440,1000")}
        for name, (path, win) in shots.items():
            subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1",
                            f"--window-size={win}", "--virtual-time-budget=6000", f"--screenshot={img / name}",
                            f"http://127.0.0.1:8765/{path}"], check=True, capture_output=True)
            print("wrote", img / name)
    finally:
        srv.terminate()


def cmd_verify(_args) -> bool:
    a = api()
    ok = True
    for _ in range(30):
        rt = a.get_space_runtime(SPACE_ID)
        print("space runtime:", rt.stage)
        if rt.stage in ("RUNNING", "RUNTIME_ERROR", "BUILD_ERROR", "CONFIG_ERROR"):
            break
        time.sleep(10)
    ok &= rt.stage == "RUNNING"
    for path in ("", "index.html", "explore.html", "pages/13.html", "img_card/index.png"):
        try:
            with urllib.request.urlopen(f"{SPACE_APP_URL}/{path}", timeout=30) as r:
                print("GET", path or "/", r.status, len(r.read()), "bytes")
        except Exception as e:  # noqa: BLE001
            ok = False
            print("GET", path or "/", "failed:", e)
    hdr = {"Authorization": f"Bearer {token()}"}
    valid = {}
    for _ in range(30):
        req = urllib.request.Request(f"https://datasets-server.huggingface.co/is-valid?dataset={DATASET_ID}",
                                     headers=hdr)
        try:
            valid = json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as e:  # noqa: BLE001  the viewer returns 500 while it processes a new dataset
            print("is-valid not ready:", e)
        if valid.get("viewer"):
            break
        time.sleep(20)
    print("is-valid:", valid)
    req = urllib.request.Request(f"https://datasets-server.huggingface.co/splits?dataset={DATASET_ID}", headers=hdr)
    try:
        splits = json.load(urllib.request.urlopen(req, timeout=30))
        got = {s["config"] for s in splits.get("splits", [])}
        print("configs in viewer:", sorted(got), "missing:", sorted(set(CONFIGS) - got))
        ok &= set(CONFIGS) <= got
    except Exception as e:  # noqa: BLE001
        ok = False
        print("splits failed:", e)
    ok &= bool(valid.get("viewer"))
    print("VERIFY", "OK" if ok else "FAILED")
    return ok


def cmd_publish(args):
    if not cmd_check(args):
        sys.exit("token cannot write to the org; see runs/worker-hf.md")
    out = cmd_build(args)
    a = api()
    msg = args.message or f"Publish from {GITHUB} at {git_rev()}"
    a.create_repo(SPACE_ID, repo_type="space", space_sdk="static", exist_ok=True)
    a.upload_folder(repo_id=SPACE_ID, repo_type="space", folder_path=out / "space", commit_message=msg,
                    delete_patterns="*")
    print("space uploaded:", SPACE_URL)
    a.create_repo(DATASET_ID, repo_type="dataset", exist_ok=True)
    a.upload_folder(repo_id=DATASET_ID, repo_type="dataset", folder_path=out / "dataset", commit_message=msg,
                    delete_patterns="*")
    print("dataset uploaded:", DATASET_URL)
    if not args.no_verify:
        cmd_verify(args)


def git_rev() -> str:
    try:
        return subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "build", "screenshots", "publish", "verify"])
    ap.add_argument("--root", default=str(REPO), help="checkout with artifacts/, runs/, site/, docs/cases/")
    ap.add_argument("--page", default="pages/1910.html", help="page used for the page screenshot")
    ap.add_argument("--message", help="commit message on the Hub")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()
    fn = {"check": cmd_check, "build": cmd_build, "screenshots": cmd_screenshots, "publish": cmd_publish,
          "verify": cmd_verify}[args.command]
    res = fn(args)
    if args.command in ("check", "verify") and not res:
        sys.exit(1)


if __name__ == "__main__":
    main()
