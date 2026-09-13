"""Render the landing page and mirror the static site into public/ for hosting.

Run after generating report cards (site/report-*.html + leaderboard.html exist).
Renders site/index.html, then copies the static site into public/ (a committed,
non-gitignored directory) so a static host such as Vercel can serve it.

  python scripts/publish_site.py
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gauntlet import report  # noqa: E402

SITE = ROOT / "site"
PUBLIC = ROOT / "public"

NAIVE = "report-naive-reference.html"
HARDENED = "report-hardened-reference.html"


def main() -> int:
    report.render_index(NAIVE, HARDENED)
    PUBLIC.mkdir(exist_ok=True)
    copied = []
    for name in ("index.html", "leaderboard.html", "style.css", NAIVE, HARDENED):
        src = SITE / name
        if src.exists():
            shutil.copyfile(src, PUBLIC / name)
            copied.append(name)
    hero = SITE / "hero.mp4"
    if hero.exists():
        shutil.copyfile(hero, PUBLIC / "hero.mp4")
        copied.append("hero.mp4")
    print("published to public/:", ", ".join(copied))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
