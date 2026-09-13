"""Run manifest: a single self-describing JSON per run, enough to replay the report
card offline without contacting any target or external service."""

import json
import subprocess
from pathlib import Path

from . import __version__
from .grader import GRADING_VERSION

ROOT = Path(__file__).resolve().parent.parent


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def write_manifest(run_dir: Path, *, target: str, team: str, timestamp: str,
                   grade, seed: str, wall_time_s: float, warnings: list[str]) -> Path:
    """Write runs/<ts>/manifest.json. Self-contained: carries the full grade+results."""
    gj = grade.to_json()
    data = {
        "gauntlet_version": __version__,
        "grading_version": GRADING_VERSION,
        "git_commit": git_commit(),
        "target": target,
        "team": team,
        "timestamp": timestamp,
        "seed": seed,
        "wall_time_s": round(wall_time_s, 3),
        "scenarios": [
            {"scenario": r["scenario"], "seed": seed, "verdict": r["verdict"],
             "penalty": r["penalty"]}
            for r in gj["results"]
        ],
        "grade": gj,
        "warnings": warnings,
    }
    path = run_dir / "manifest.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
