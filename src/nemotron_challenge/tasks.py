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
    """TODO: define your extraction and entry segmentation process."""
    _unfinished("extract")


def match(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: define how your team finds and verifies article matches."""
    _unfinished("match")


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
    """TODO: build your LaTeX documents and static website."""
    _unfinished("site")


def evaluate(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: review your results and document successes and failures."""
    _unfinished("evaluate")
