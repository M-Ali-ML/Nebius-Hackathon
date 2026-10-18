"""Teams implement these stages with their coding agents."""
from pathlib import Path
from typing import Any

from .config import Settings

STAGES = ("extract", "match", "compare", "agent", "site", "evaluate")


def _unfinished(stage: str) -> None:
    raise NotImplementedError(
        f"TODO: implement the {stage} milestone. Read docs/milestones.md#{stage}. "
        "The starter has no result for this stage."
    )


def extract(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Segment existing page records into entries. Parse output in extract/pages/ comes from extract.py."""
    from .segment import run_segment

    if not any((work_dir / "extract" / "pages").glob("*.json")):
        raise FileNotFoundError(f"no page records in {work_dir / 'extract' / 'pages'}; run Parse first")
    return run_segment(work_dir)


def match(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """BM25 -> embed -> rerank per entry, then index entries and matched articles in LanceDB."""
    from .index import build_index
    from .match import run_match

    result = run_match(settings, work_dir)
    result["index"] = build_index(settings, work_dir)
    return result


def compare(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: define your vocabulary, frequency, or topic comparison."""
    _unfinished("compare")


def agent(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: implement your Hermes tools and evidence checks."""
    _unfinished("agent")


def site(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: build your LaTeX documents and static website."""
    _unfinished("site")


def evaluate(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: review your results and document successes and failures."""
    _unfinished("evaluate")
