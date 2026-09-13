"""Static publishing stays complete, repeatable, and free of local paths."""

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
    site, public = root / "site", root / "public"
    site.mkdir(parents=True)
    publisher = load_publisher()
    monkeypatch.setattr(publisher, "SITE", site)
    monkeypatch.setattr(publisher, "PUBLIC", public)
    monkeypatch.setattr(publisher.report, "SITE", site)
    return publisher, site, public


def seed_site(site: Path) -> None:
    for name in (
        "leaderboard.html",
        "style.css",
        "report-naive-reference.html",
        "report-hardened-reference.html",
    ):
        (site / name).write_text(
            f"<!doctype html><html><body>first {name}</body></html>",
            encoding="utf-8",
        )
    (site / "leaderboard.json").write_text("private runtime data", encoding="utf-8")
    (site / "unrelated.txt").write_text("must not publish", encoding="utf-8")


def local_links(html: str) -> list[str]:
    return [
        link for link in re.findall(r'href="([^"]+)"', html)
        if not link.startswith(("http://", "https://", "#"))
    ]


def test_publish_is_allowlisted_link_complete_and_repeatable(publish_roots):
    publisher, site, public = publish_roots
    seed_site(site)
    assert publisher.main() == 0
    expected = {
        "index.html", "leaderboard.html", "style.css",
        "report-naive-reference.html", "report-hardened-reference.html",
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
    (site / "leaderboard.html").write_text("second leaderboard", encoding="utf-8")
    assert publisher.main() == 0
    assert (public / "leaderboard.html").read_text(encoding="utf-8") == "second leaderboard"


def test_optional_hero_is_copied_when_present(publish_roots):
    publisher, site, public = publish_roots
    seed_site(site)
    (site / "hero.mp4").write_bytes(b"qa-video")
    assert publisher.main() == 0
    assert (public / "hero.mp4").read_bytes() == b"qa-video"
