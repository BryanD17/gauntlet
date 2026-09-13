"""Renders the report card and leaderboard as styled HTML via jinja2.

The leaderboard is a JSON file on disk (site/leaderboard.json) keyed by team, so
re-running the same team updates its row in place instead of adding a duplicate.
"""

import json
import re
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .grader import GRADING_VERSION

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "web" / "templates"
STATIC = ROOT / "web" / "static"
SITE = ROOT / "site"

# Big grade letter is colored by result.
GRADE_CLASS = {"A": "grade-pass", "B": "grade-warn", "C": "grade-warn",
               "D": "grade-fail", "F": "grade-fail"}
VERDICT_CLASS = {"PASS": "pass", "FAIL": "fail", "ABSTAINED": "abstain", "ERROR": "error"}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "team"


def display_team(name: str) -> str:
    """Operator-supplied team name shown in the pages. jinja autoescapes HTML; here we
    also drop backslashes and control chars and cap length, so no local-path-shaped or
    control content can render even from a hostile name."""
    cleaned = re.sub(r"[\\\x00-\x1f\x7f]", "", str(name)).strip()
    return cleaned[:64] or "team"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "j2"]),
    )


def _ensure_site() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    if (STATIC / "style.css").exists():
        shutil.copyfile(STATIC / "style.css", SITE / "style.css")
    hero = STATIC / "hero.mp4"
    if hero.exists():
        shutil.copyfile(hero, SITE / "hero.mp4")


def render_report(grade, team: str, target: str, timestamp: str) -> Path:
    _ensure_site()
    panels = []
    for r in grade.results:
        panels.append({
            "title": r.title,
            "category": r.category,
            "verdict": r.verdict,
            "verdict_class": VERDICT_CLASS.get(r.verdict, "error"),
            "penalty": r.penalty,
            "required": r.required,
            "detail": r.detail,
            "evidence": json.dumps(
                {"inputs": r.inputs,
                 "outputs": [[a.to_json() for a in g] for g in r.outputs]},
                indent=2,
            ),
        })
    html = _env().get_template("report.html.j2").render(
        team=display_team(team),
        target=target,
        timestamp=timestamp,
        grade=grade,
        grade_class=GRADE_CLASS.get(grade.letter, "grade-warn"),
        weighting_note=grade.to_json()["weighting_note"],
        grading_version=GRADING_VERSION,
        panels=panels,
        has_hero=(SITE / "hero.mp4").exists(),
    )
    out = SITE / f"report-{slugify(team)}.html"
    out.write_text(html, encoding="utf-8")
    return out


def update_leaderboard(grade, team: str, timestamp: str) -> Path:
    _ensure_site()
    store = SITE / "leaderboard.json"
    rows = []
    if store.exists():
        try:
            rows = json.loads(store.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            rows = []
    slug = slugify(team)
    rows = [row for row in rows if row.get("slug") != slug]   # dedupe by team
    rows.append({
        "team": display_team(team),
        "slug": slug,
        "letter": grade.letter,
        "score": grade.score,
        "attacks_survived": grade.attacks_caught,
        "attacks_total": len(grade.results),
        "timestamp": timestamp,
        "report": f"report-{slug}.html",
    })
    rows.sort(key=lambda r: (-r["score"], r["team"]))
    store.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    for i, row in enumerate(rows):
        row["rank"] = i + 1
        row["grade_class"] = GRADE_CLASS.get(row["letter"], "grade-warn")
    html = _env().get_template("leaderboard.html.j2").render(rows=rows)
    out = SITE / "leaderboard.html"
    out.write_text(html, encoding="utf-8")
    return out
