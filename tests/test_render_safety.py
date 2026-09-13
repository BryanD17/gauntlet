"""Render hostile display data through the real HTML templates."""
from pathlib import Path
from uuid import uuid4

from gauntlet import report
from gauntlet.attacks import Result
from gauntlet.grader import grade
from gauntlet.harness import Action


def test_report_escapes_script_and_hides_local_path(monkeypatch):
    output = Path(__file__).resolve().parents[1] / "review" / "render-safety" / uuid4().hex
    monkeypatch.setattr(report, "SITE", output)
    action = Action("flag", "", {}, "<script>alert('x')</script>")
    result = Result("injection", "injection", "Prompt injection", "PASS", 35,
                    "Untrusted text is data", "Blocked instruction", outputs=[[action]])
    path = report.render_report(
        grade([result]), '<b>QA</b> C:\\Users\\secret',
        'http://127.0.0.1:9001', 'QA timestamp',
    )
    html = path.read_text(encoding="utf-8")
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html
    assert "<b>QA</b>" not in html
    assert "C:\\Users" not in html, "local user path leaked into shareable report"
