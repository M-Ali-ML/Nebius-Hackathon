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
    from .match import run_match, run_page_match

    result = run_match(settings, work_dir)
    result["pages"] = run_page_match(settings, work_dir)
    result["index"] = build_index(settings, work_dir)
    return result


def compare(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Corpus word frequencies, pair comparisons with checked quotes, and the drift decomposition."""
    from .compare import run

    return run(settings, work_dir)


def agent(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Send the questions in runs/agent/questions.json (or the defaults) to Hermes and save each transcript."""
    from .agent_runner import RUNS, load_questions, run_questions

    del settings, work_dir  # Hermes reads its own config; the tools read the shared artifacts
    return run_questions(load_questions(RUNS / "questions.json"), repo=Path(__file__).resolve().parents[2])


def site(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Compile one LaTeX document per page record, then build the static site next to the work dir."""
    from .latex import build_all
    from .site import build_site

    if not (work_dir / "extract" / "pages").is_dir():
        raise ValueError(f"no page records in {work_dir / 'extract' / 'pages'}; run extract first")
    return {"latex": build_all(work_dir), "site": build_site(work_dir)}


def evaluate(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Collect run metadata and check that each case study in docs/cases links to a saved transcript."""
    from .evaluate import run

    del settings
    return run(work_dir)
