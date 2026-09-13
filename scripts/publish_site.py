"""Build the public static site into public/ for hosting (Vercel).

The public site is a static showcase: the console-era landing page, the two reference
report cards as live examples, and the leaderboard. The run console itself needs the
local backend (it drives real integrations with your tokens), so the landing's console
links point at the GitHub quickstart. This script rewrites the backend template's
absolute paths for static hosting; it does not change any application code.

  python scripts/publish_site.py
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"
STATIC = ROOT / "web" / "static"
SITE = ROOT / "site"
PUBLIC = ROOT / "public"
REPO = "https://github.com/BryanD17/gauntlet"

NAIVE = "report-naive-reference.html"
HARDENED = "report-hardened-reference.html"

# Absolute backend paths -> static equivalents for the hosted landing page.
LANDING_REWRITES = {
    'href="/static/': 'href="',
    'src="/static/': 'src="',
    'href="/console"': f'href="{REPO}#quickstart"',
    'href="/leaderboard"': 'href="leaderboard.html"',
    'href="/report/naive-reference"': f'href="{NAIVE}"',
    'href="/report/hardened-reference"': f'href="{HARDENED}"',
    'href="/"': 'href="index.html"',
}


def build_landing() -> str:
    html = (TEMPLATES / "landing.html.j2").read_text(encoding="utf-8")
    for old, new in LANDING_REWRITES.items():
        html = html.replace(old, new)
    return html


def main() -> int:
    PUBLIC.mkdir(exist_ok=True)
    (PUBLIC / "index.html").write_text(build_landing(), encoding="utf-8")

    copied = ["index.html"]
    # New landing assets (console-era design).
    for name in ("console.css", "hero-bg.mp4", "seal.png"):
        src = STATIC / name
        if src.exists():
            shutil.copyfile(src, PUBLIC / name)
            copied.append(name)
    # Report cards + their stylesheet + the leaderboard, from the rendered site/.
    for name in ("style.css", "leaderboard.html", NAIVE, HARDENED):
        src = SITE / name
        if src.exists():
            shutil.copyfile(src, PUBLIC / name)
            copied.append(name)
    print("published to public/:", ", ".join(copied))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
