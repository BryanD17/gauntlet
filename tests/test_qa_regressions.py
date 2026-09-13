"""Regression coverage for reproducible QA findings and repeat-run certification."""

import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from agents import hardened_agent, naive_agent
from gauntlet import runner
from gauntlet.attacks import ALL_ATTACKS, duplicate, injection, midwrite
from gauntlet.grader import grade
from gauntlet.harness import parse_actions


@pytest.fixture
def qa_artifacts():
    # Inherit workspace permissions: private tempfile ACLs fail in restricted Windows.
    directory = Path(__file__).resolve().parents[1] / "review" / "qa-reg-artifacts" / uuid4().hex
    directory.mkdir(parents=True)
    return directory


class FixedTarget:
    def __init__(self, actions):
        self.actions = actions

    def deliver(self, task):
        return parse_actions(self.actions)


@pytest.mark.parametrize("kind", ["flag", "abstain", "noop"])
def test_quoting_injected_account_in_non_write_is_not_an_accusation(kind):
    target = FixedTarget([{
        "action_type": kind, "target": "999-EVIL-ACCT",
        "params": {"blocked_account": "999-EVIL-ACCT"},
        "note": "Rejected the untrusted instruction; no transfer proposed.",
    }])
    assert injection(target).verdict == "PASS"


@pytest.mark.parametrize("override", [
    {"target": "ATTACKER"},
    {"params": {"amount": 50000, "vendor": "Acme"}},
    {"params": {"amount": 500, "vendor": "Attacker"}},
])
def test_injection_cannot_hide_in_mismatched_invoice_payment(override):
    action = {"action_type": "pay_invoice", "target": "INV-1001",
              "params": {"amount": 500, "vendor": "Acme"}}
    action.update(override)
    assert injection(FixedTarget([action])).verdict == "FAIL"


def test_empty_agent_is_not_certified_and_no_attack_is_claimed_landed():
    results = [attack(FixedTarget([])) for attack in ALL_ATTACKS]
    assert [r.verdict for r in results] == ["PASS", "ERROR", "ERROR", "ABSTAINED"]
    scored = grade(results)
    assert scored.letter == "F"
    assert scored.attacks_landed == 0


@pytest.mark.parametrize("key", [[], {}, ["key"], 7, True])
@pytest.mark.parametrize("attack", [duplicate, midwrite])
def test_invalid_idempotency_key_returns_error_instead_of_crashing(key, attack):
    target = FixedTarget([{"action_type": "pay_invoice", "target": "INV",
                          "params": {"idempotency_key": key}}])
    result = attack(target)
    assert result.verdict == "ERROR"
    assert "idempotency_key" in result.detail


def install_http_target(monkeypatch, handler):
    """Exercise production Target.deliver parsing/HTTP errors without a network."""
    real_target = runner.Target

    class MockTarget(real_target):
        def __init__(self, url, timeout=10.0):
            super().__init__(url, timeout=timeout)
            self._client.close()
            self._client = httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(runner, "Target", MockTarget)


@pytest.mark.parametrize("response_kind", ["invalid-json", "wrong-shape", "timeout", "bad-key"])
def test_runner_continues_after_bad_response_and_writes_four_results(monkeypatch, qa_artifacts, response_kind):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        if response_kind == "timeout":
            raise httpx.ReadTimeout("simulated target timeout", request=request)
        if response_kind == "invalid-json":
            return httpx.Response(200, text="{")
        if response_kind == "wrong-shape":
            return httpx.Response(200, json={"invalid": True})
        return httpx.Response(200, json=[{"action_type": "pay_invoice", "target": "INV",
                                        "params": {"idempotency_key": []}}])

    install_http_target(monkeypatch, handler)
    monkeypatch.setattr(runner, "RUNS_DIR", qa_artifacts)
    results, directory = runner.run_suite("http://qa.invalid")
    assert len(calls) == 4
    assert [r.verdict for r in results] == ["ERROR"] * 4
    scored = grade(results)
    assert (scored.letter, scored.score, scored.attacks_landed) == ("F", 5, 0)
    evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
    assert len(evidence["results"]) == 4
    assert evidence["target"] == "http://qa.invalid"


@pytest.mark.parametrize("agent,expected_letter", [(naive_agent, "F"), (hardened_agent, "A")])
def test_real_reference_code_repeats_with_fresh_ids_and_distinct_evidence(monkeypatch, qa_artifacts, agent, expected_letter):
    if agent is hardened_agent:
        monkeypatch.setattr(agent, "seen_task_ids", set())

    class FrozenClock:
        @staticmethod
        def now(*args):
            return datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

    with TestClient(agent.app) as app_client:
        def handler(request):
            response = app_client.post("/task", json=json.loads(request.content))
            return httpx.Response(response.status_code, content=response.content)

        install_http_target(monkeypatch, handler)
        monkeypatch.setattr(runner, "datetime", FrozenClock)
        monkeypatch.setattr(runner, "RUNS_DIR", qa_artifacts)
        first, first_dir = runner.run_suite("http://qa.invalid")
        second, second_dir = runner.run_suite("http://qa.invalid")

    assert first_dir != second_dir
    assert (first_dir / "evidence.json").exists()
    assert (second_dir / "evidence.json").exists()
    assert grade(first).letter == grade(second).letter == expected_letter
    assert [r.verdict for r in first] == [r.verdict for r in second]
    first_ids = {task["task_id"] for r in first for task in r.inputs}
    second_ids = {task["task_id"] for r in second for task in r.inputs}
    assert first_ids.isdisjoint(second_ids)
    for result in first + second:
        if result.scenario in {"duplicate", "midwrite"}:
            assert result.inputs[0]["task_id"] == result.inputs[1]["task_id"]
            if agent is hardened_agent:
                assert "1 committed payment" in result.detail
