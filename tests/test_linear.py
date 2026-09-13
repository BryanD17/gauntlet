"""Offline Linear contract checks; no keys or network access required."""
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from gauntlet import linear


@pytest.fixture(autouse=True)
def isolate_linear(monkeypatch):
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_TEAM_ID", raising=False)
    monkeypatch.setattr(linear.httpx, "post", Mock(side_effect=AssertionError("unexpected HTTP")))


def response(body):
    return httpx.Response(200, json=body, request=httpx.Request("POST", linear.ENDPOINT))


def test_no_key_skips_all_http(capsys):
    assert linear._team_id() is None
    assert linear.file_issue("title", "description") is None
    assert linear.file_failures("QA", []) == []
    linear.httpx.post.assert_not_called()
    assert capsys.readouterr().out.count("LINEAR_API_KEY not set; skipping Linear") == 3


def test_configured_team_does_not_query(monkeypatch):
    monkeypatch.setenv("LINEAR_TEAM_ID", "configured-team")
    assert linear._team_id() == "configured-team"
    linear.httpx.post.assert_not_called()


def test_team_discovery_and_mutation_use_raw_auth_and_variables(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "qa-placeholder")
    post = Mock(side_effect=[
        response({"data": {"teams": {"nodes": [{"id": "team-id"}]}}}),
        response({"data": {"issueCreate": {"success": True, "issue": {"url": "https://linear.app/qa/QA-1"}}}}),
    ])
    monkeypatch.setattr(linear.httpx, "post", post)
    assert linear.file_issue("title", "description") == "https://linear.app/qa/QA-1"
    assert post.call_count == 2
    for call in post.call_args_list:
        assert call.args == ("https://api.linear.app/graphql",)
        assert call.kwargs["headers"]["Authorization"] == "qa-placeholder"
        assert call.kwargs["timeout"] <= 15
    assert post.call_args.kwargs["json"]["variables"]["input"] == {
        "teamId": "team-id", "title": "title", "description": "description",
    }


@pytest.mark.parametrize("body", [None, [], {"errors": [{"message": "bad"}]},
    {"data": None}, {"data": {"teams": None}}, {"data": {"teams": {"nodes": [None]}}},
    {"data": {"teams": {"nodes": [{"id": 42}]}}}])
def test_malformed_team_responses_do_not_raise(monkeypatch, body):
    monkeypatch.setenv("LINEAR_API_KEY", "qa-placeholder")
    monkeypatch.setattr(linear.httpx, "post", Mock(return_value=response(body)))
    assert linear._team_id() is None


@pytest.mark.parametrize("body", [{"data": {"issueCreate": None}},
    {"data": {"issueCreate": {"success": False}}},
    {"data": {"issueCreate": {"success": True, "issue": {"url": None}}}}])
def test_unsuccessful_mutation_returns_none(monkeypatch, body):
    monkeypatch.setenv("LINEAR_API_KEY", "qa-placeholder")
    monkeypatch.setenv("LINEAR_TEAM_ID", "configured-team")
    monkeypatch.setattr(linear.httpx, "post", Mock(return_value=response(body)))
    assert linear.file_issue("title", "description") is None


def test_timeout_warns_without_echoing_credentials(monkeypatch, capsys):
    monkeypatch.setenv("LINEAR_API_KEY", "qa-placeholder")
    monkeypatch.setattr(linear.httpx, "post", Mock(side_effect=httpx.ReadTimeout("qa-placeholder\nupstream body")))
    assert linear.file_issue("title", "description") is None
    output = capsys.readouterr().out
    assert "qa-placeholder" not in output
    assert output.startswith("  ! ")
    assert len(output.splitlines()) == 1


def test_batch_keeps_successes_after_failure_and_includes_evidence(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "qa-placeholder")
    issue = Mock(side_effect=[None, "https://linear.app/qa/QA-2"])
    monkeypatch.setattr(linear, "file_issue", issue)
    result = SimpleNamespace(title="Prompt injection", scenario="injection", detail="unsafe payment", required="trusted invoice only")
    assert linear.file_failures("QA", [result, result], "site/report.html") == ["https://linear.app/qa/QA-2"]
    title, description = issue.call_args.args
    assert title == "[Gauntlet] QA: Prompt injection failed"
    assert all(text in description for text in ["injection", "unsafe payment", "trusted invoice only", "site/report.html"])
