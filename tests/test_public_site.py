"""The static publisher stays complete, repeatable, and free of backend paths.

publish_site.py builds public/ from the console-era landing template plus the rendered
report cards and leaderboard. It must publish exactly the intended files, never leak
private runtime data (leaderboard.json) or unrelated files, rewrite every backend path
(/static, /console, ...) to a static-safe one, and leave no raw template syntax or local
machine paths in the output.
"""

import importlib.util
import re
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_publisher():
    spec = importlib.util.spec_from_file_location(
        "gauntlet_publish_site", ROOT / "scripts" / "publish_site.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def publish_roots(monkeypatch):
    root = ROOT / "review" / "public-test" / uuid4().hex
    site, public, static = root / "site", root / "public", root / "static"
    site.mkdir(parents=True)
    static.mkdir(parents=True)
    for name in ("console.css", "hero-bg.mp4", "seal.png"):
        (static / name).write_bytes(b"asset")
    publisher = load_publisher()
    monkeypatch.setattr(publisher, "SITE", site)
    monkeypatch.setattr(publisher, "PUBLIC", public)
    monkeypatch.setattr(publisher, "STATIC", static)
    return publisher, site, public


def seed_site(site: Path) -> None:
    for name in ("leaderboard.html", "style.css",
                 "report-naive-reference.html", "report-hardened-reference.html"):
        (site / name).write_text(
            f"<!doctype html><html><body>first {name}</body></html>", encoding="utf-8")
    (site / "leaderboard.json").write_text("private runtime data", encoding="utf-8")
    (site / "unrelated.txt").write_text("must not publish", encoding="utf-8")


def local_links(html: str) -> list[str]:
    return [link for link in re.findall(r'href="([^"]+)"', html)
            if not link.startswith(("http://", "https://", "#"))]


def test_publish_is_allowlisted_link_complete_and_repeatable(publish_roots):
    publisher, site, public = publish_roots
    seed_site(site)
    assert publisher.main() == 0
    expected = {
        "index.html", "console.css", "hero-bg.mp4", "seal.png", "style.css",
        "leaderboard.html", "report-naive-reference.html", "report-hardened-reference.html",
    }
    assert {path.name for path in public.iterdir()} == expected
    assert not (public / "leaderboard.json").exists()
    assert not (public / "unrelated.txt").exists()
    for page in public.glob("*.html"):
        html = page.read_text(encoding="utf-8")
        assert not re.search(r"{{|{%", html)
        assert "C:\\Users\\" not in html
        for link in local_links(html):
            assert (public / link).is_file(), f"{page.name} has missing link {link}"
    # Repeatable: a second publish overwrites in place.
    (site / "leaderboard.html").write_text("second leaderboard", encoding="utf-8")
    assert publisher.main() == 0
    assert (public / "leaderboard.html").read_text(encoding="utf-8") == "second leaderboard"


def test_landing_has_no_backend_paths_and_ships_assets(publish_roots):
    publisher, site, public = publish_roots
    seed_site(site)
    assert publisher.main() == 0
    html = (public / "index.html").read_text(encoding="utf-8")
    # No absolute backend paths may leak into the static landing.
    assert "/static/" not in html
    assert 'href="/console"' not in html and 'href="/leaderboard"' not in html
    # The console-era assets are shipped.
    for name in ("console.css", "hero-bg.mp4", "seal.png"):
        assert (public / name).exists()
