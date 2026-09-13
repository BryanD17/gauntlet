"""CLI-to-evidence/report verification with every remote side effect mocked."""
import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from agents import hardened_agent, naive_agent
from gauntlet import cli, fixer, github_pr, linear, manifest, report, runner


@pytest.fixture
def isolated_cli(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "review" / "cli-artifacts" / uuid4().hex
    root.mkdir(parents=True)
    monkeypatch.setattr(cli, "load_dotenv", Mock())  # never read the actual .env
    monkeypatch.setattr(cli, "post_to_slack", Mock(return_value=True))
    monkeypatch.setattr(linear, "file_failures", Mock(return_value=[]))
    monkeypatch.setattr(fixer, "generate_fixes", Mock(return_value=[]))
    monkeypatch.setattr(github_pr, "open_fix_pr", Mock())
    monkeypatch.setattr(manifest, "git_commit", lambda: "qa-read-only")
    monkeypatch.setattr(runner, "RUNS_DIR", root / "runs")
    monkeypatch.setattr(report, "SITE", root / "site")
    return root


def install_target(monkeypatch, app_client):
    target_class = runner.Target
    class LocalTarget(target_class):
        def __init__(self, url, timeout=10.0):
            super().__init__(url, timeout=timeout)
            self._client.close()
            def handle(request):
                response = app_client.post("/task", json=json.loads(request.content))
                return httpx.Response(response.status_code, content=response.content)
            self._client = httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(runner, "Target", LocalTarget)


@pytest.mark.parametrize("agent,expected", [(naive_agent, "F"), (hardened_agent, "A")])
def test_cli_runs_twice_preserves_manifests_and_replays_offline(monkeypatch, isolated_cli, agent, expected):
    if agent is hardened_agent:
        monkeypatch.setattr(agent, "seen_task_ids", set())
    with TestClient(agent.app) as client:
        install_target(monkeypatch, client)
        for _ in range(2):
            assert cli.main(["run", "--target", "http://127.0.0.1:9001", "--team", "QA Team"]) == 0
    runs = list((isolated_cli / "runs").iterdir())
    assert len(runs) == 2
    for directory in runs:
        data = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        assert data["grade"]["letter"] == expected
        assert all(r["verdict"] != "ERROR" for r in data["grade"]["results"])
        assert (directory / "evidence.json").exists()
    leaderboard = json.loads((report.SITE / "leaderboard.json").read_text(encoding="utf-8"))
    assert len(leaderboard) == 1
    assert leaderboard[0]["letter"] == expected
    fixer.generate_fixes.assert_not_called()
    github_pr.open_fix_pr.assert_not_called()
    cli.post_to_slack.reset_mock()
    linear.file_failures.reset_mock()
    monkeypatch.setattr(runner, "Target", Mock(side_effect=AssertionError("replay must be offline")))
    assert cli.main(["replay", "--run", str(runs[0])]) == 0
    cli.post_to_slack.assert_not_called()
    linear.file_failures.assert_not_called()


def test_invalid_target_configuration_has_no_external_effects(monkeypatch, isolated_cli):
    suite = Mock(side_effect=AssertionError("invalid config must not run"))
    monkeypatch.setattr(cli, "run_suite", suite)
    assert cli.main(["run", "--target", "file:///etc/passwd", "--team", "QA"]) == 3
    suite.assert_not_called()
    cli.post_to_slack.assert_not_called()
    linear.file_failures.assert_not_called()


def test_no_fix_does_not_read_source_or_generate_patch(monkeypatch, isolated_cli):
    with TestClient(naive_agent.app) as client:
        install_target(monkeypatch, client)
        assert cli.main(["run", "--target", "http://127.0.0.1:9001", "--team", "QA",
                         "--repo", "qa/repo", "--source", "nonexistent-source.py", "--no-fix"]) == 0
    fixer.generate_fixes.assert_not_called()
    github_pr.open_fix_pr.assert_not_called()
