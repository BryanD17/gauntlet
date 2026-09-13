"""Offline external-service behavior: fallbacks and non-default branch writes."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest

from gauntlet import fixer, github_pr, notify
from gauntlet.attacks import Result


@pytest.fixture(autouse=True)
def no_remote_credentials(monkeypatch):
    for name in ("GITHUB_TOKEN", "ANTHROPIC_API_KEY", "SLACK_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(httpx, "post", Mock(side_effect=AssertionError("unexpected HTTP")))


@pytest.fixture
def artifact_dir():
    directory = Path(__file__).resolve().parents[1] / "review" / "integration-artifacts" / uuid4().hex
    directory.mkdir(parents=True)
    return directory


@pytest.fixture
def fix():
    return fixer.FixProposal("injection", "agents/naive_agent.py", "safe = True\n", "Use trusted data.", "--- a/agent.py\n+++ b/agent.py\n")


@pytest.fixture
def failure():
    return Result("injection", "injection", "Prompt injection", "FAIL", 35,
                  "Only trusted payment", "Unauthorized transfer", inputs=[{"task_id": "qa-task"}])


def test_slack_no_configuration_makes_no_request():
    assert notify.post_to_slack("QA", "A", 100, "None") is False
    httpx.post.assert_not_called()


@pytest.mark.parametrize("status,expected", [(200, True), (400, False), (429, False), (500, False)])
def test_slack_status_and_payload(monkeypatch, status, expected):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://qa.invalid/slack")
    post = Mock(return_value=httpx.Response(status))
    monkeypatch.setattr(httpx, "post", post)
    assert notify.post_to_slack("QA", "F", 5, "Prompt injection", "report.html") is expected
    payload = post.call_args.kwargs["json"]
    assert payload["text"] == "Gauntlet: QA graded F (5)"
    assert "report.html" in str(payload["blocks"])
    assert post.call_args.kwargs["timeout"] <= 15


def test_slack_timeout_returns_false(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://qa.invalid/slack")
    monkeypatch.setattr(httpx, "post", Mock(side_effect=httpx.ReadTimeout("simulated")))
    assert notify.post_to_slack("QA", "F", 5, "Prompt injection") is False


def test_github_missing_token_saves_both_fallback_artifacts(artifact_dir, fix):
    assert github_pr.open_fix_pr("qa/repo", fix, artifact_dir) is None
    assert (artifact_dir / "patches/injection.diff").read_text() == fix.diff
    assert (artifact_dir / "patches/injection.naive_agent.py").read_text() == fix.fixed_source


@pytest.mark.parametrize("existing_branch", [False, True])
def test_github_updates_only_new_branch_and_opens_review_pr(monkeypatch, artifact_dir, fix, existing_branch):
    monkeypatch.setenv("GITHUB_TOKEN", "qa-placeholder")
    class FakeGithubError(Exception):
        pass
    repo = Mock()
    repo.default_branch = "main"
    repo.get_branch.return_value.commit.sha = "base-sha"
    repo.get_contents.return_value.sha = "file-sha"
    repo.create_pull.return_value.html_url = "https://github.com/qa/repo/pull/1"
    if existing_branch:
        repo.create_git_ref.side_effect = [FakeGithubError("exists"), None]
    gh = Mock()
    gh.get_repo.return_value = repo
    monkeypatch.setitem(sys.modules, "github", SimpleNamespace(Github=Mock(return_value=gh), GithubException=FakeGithubError))
    assert github_pr.open_fix_pr("qa/repo", fix, artifact_dir, "exact failure") == "https://github.com/qa/repo/pull/1"
    update = repo.update_file.call_args.kwargs
    branch = update["branch"]
    assert branch.startswith("gauntlet/fix-injection")
    assert branch != repo.default_branch
    assert update["content"] == fix.fixed_source
    assert update["sha"] == "file-sha"
    repo.get_contents.assert_called_once_with(fix.filename, ref=branch)
    pr = repo.create_pull.call_args.kwargs
    assert pr["base"] == "main" and pr["head"] == branch
    assert "exact failure" in pr["body"]
    assert repo.create_git_ref.call_args.kwargs == {"ref": f"refs/heads/{branch}", "sha": "base-sha"}


def test_github_api_failure_falls_back_without_file_update(monkeypatch, artifact_dir, fix):
    monkeypatch.setenv("GITHUB_TOKEN", "qa-placeholder")
    gh = Mock()
    gh.get_repo.side_effect = RuntimeError("simulated outage")
    monkeypatch.setitem(sys.modules, "github", SimpleNamespace(Github=Mock(return_value=gh), GithubException=RuntimeError))
    assert github_pr.open_fix_pr("qa/repo", fix, artifact_dir) is None
    assert (artifact_dir / "patches/injection.diff").exists()


def test_fixer_without_key_never_constructs_client(monkeypatch, failure):
    constructor = Mock(side_effect=AssertionError("unexpected client"))
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=constructor))
    assert fixer.generate_fix(failure, "unsafe = True\n", "agent.py") is None
    constructor.assert_not_called()


@pytest.mark.parametrize("reply", ["No code supplied.", "```python\nsafe = True\n```", None])
def test_fixer_response_and_api_failure_paths(monkeypatch, failure, reply):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "qa-placeholder")
    client = Mock()
    if reply is None:
        client.messages.create.side_effect = RuntimeError("simulated outage")
    else:
        client.messages.create.return_value.content = [SimpleNamespace(type="text", text=reply)]
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=Mock(return_value=client)))
    result = fixer.generate_fix(failure, "unsafe = True\n", "agent.py")
    if reply and "```" in reply:
        assert result.fixed_source == "safe = True\n"
        assert "-unsafe = True" in result.diff and "+safe = True" in result.diff
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "qa-task" in prompt and "Unauthorized transfer" in prompt
    else:
        assert result is None
