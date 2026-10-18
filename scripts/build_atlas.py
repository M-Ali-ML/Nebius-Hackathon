"""Rebuild the multimodal atlas: uv run python scripts/build_atlas.py [--work-dir artifacts] [--site-dir site] [--offline]"""
import argparse
import json
from pathlib import Path

from nemotron_challenge.atlas import run
from nemotron_challenge.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--work-dir", type=Path, default=Path("artifacts"))
parser.add_argument("--site-dir", type=Path, default=None)
parser.add_argument("--offline", action="store_true", help="use cached vectors only; no service calls")
args = parser.parse_args()
work = args.work_dir.resolve()
print(json.dumps(run(Settings.from_env(".env"), work, args.site_dir or work.parent / "site", offline=args.offline), indent=1))
