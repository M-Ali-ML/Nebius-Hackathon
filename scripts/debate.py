"""Run the time-travel debates (Hermes on Nemotron 3.5 Super VL) and build site/debate.html.

uv run python scripts/debate.py run [--slug lightning] [--redo]   # model calls, then verify
uv run python scripts/debate.py verify                          # verify saved debates again, no model calls
uv run python scripts/debate.py site                            # build site/debate.html
Paths default to the main checkout: --repo (Hermes profile and tools), --work-dir (artifacts).
"""
import argparse
import json
from pathlib import Path

from nemotron_challenge import debate

MAIN = Path("/Users/aly/repos/Nebius-Hackathon")

p = argparse.ArgumentParser()
p.add_argument("cmd", choices=["run", "verify", "site", "smoke"])
p.add_argument("--repo", type=Path, default=MAIN)
p.add_argument("--work-dir", type=Path, default=None)
p.add_argument("--site-dir", type=Path, default=None)
p.add_argument("--slug", action="append")
p.add_argument("--redo", action="store_true")
a = p.parse_args()
work = a.work_dir or a.repo / "artifacts"
if a.cmd == "run":
    print(json.dumps(debate.run(a.repo, work, a.slug, a.redo), indent=1))
elif a.cmd == "verify":
    print(json.dumps(debate.rescore(work), indent=1))
elif a.cmd == "smoke":
    t = debate.TOPICS[0]
    r = debate.hermes_turn(debate._prompt("scholar", t, "opening", {}), repo=a.repo)
    print(r["status"], r.get("model"), r.get("tokens"), r["seconds"], [c["name"] for c in r.get("tool_calls", [])])
    print(r.get("final_text")); print(r.get("stderr", "")[-1500:], r.get("error"))
else:
    from nemotron_challenge.debate_site import build
    print(json.dumps(build(work, a.site_dir or a.repo / "site"), indent=1))
