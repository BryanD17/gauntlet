"""Offline tests for the web console backend: validation, leaderboard, and the SSE
event sequence — the engine is stubbed so no network or real integration runs."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import web_app
from gauntlet.attacks import Result

client = TestClient(web_app.app)


@pytest.fixture
def web_artifacts():
    directory = Path(__file__).resolve().parents[1] / "review" / "web-backend-artifacts" / uuid4().hex
    directory.mkdir(parents=True)
    return directory


def _fake_results():
    return [
        Result("injection", "injection", "Prompt injection", "FAIL", 35, "req", "obeyed"),
        Result("duplicate", "duplicate", "Duplicate delivery", "FAIL", 20, "req", "twice"),
        Result("midwrite", "midwrite", "Mid-write failure", "FAIL", 25, "req", "double"),
        Result("stale", "stale", "Stale or conflicting data", "FAIL", 15, "req", "acted"),
    ]


@pytest.fixture(autouse=True)
def stub_engine(monkeypatch, web_artifacts):
    """Replace every external/engine call with an offline stub."""
    def fake_run_suite(target, timeout=10.0, on_result=None):
        results = _fake_results()
        for r in results:
            if on_result:
                on_result(r)
        run_dir = web_artifacts / "run"
        run_dir.mkdir(exist_ok=True)
        return results, run_dir

    monkeypatch.setattr(web_app, "run_suite", fake_run_suite)
    monkeypatch.setattr(web_app.report, "render_report", lambda *a, **k: web_artifacts / "r.html")
    monkeypatch.setattr(web_app.report, "update_leaderboard", lambda *a, **k: web_artifacts / "l.html")
    monkeypatch.setattr(web_app, "post_to_slack", lambda *a, **k: True)
    monkeypatch.setattr(web_app.manifest, "write_manifest", lambda *a, **k: web_artifacts / "m.json")
    # No repo passed in these tests, so fixer/github_pr/linear are never reached.


def test_validation_rejects_file_scheme():
    resp = client.post("/api/run", json={"target": "file:///etc/passwd", "team": "x"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_validation_rejects_bad_repo():
    resp = client.post("/api/run", json={"target": "http://127.0.0.1:8001",
                                        "team": "x", "repo": "bad repo"})
    assert resp.status_code == 400


@pytest.mark.parametrize("body", [
    [],
    {"target": "http://127.0.0.1:8001", "team": "QA", "repo": ["owner/repo"]},
    {"target": "http://127.0.0.1:8001", "team": {"name": "QA"}},
    {"target": "https://example.com", "team": "QA", "allow_remote": "false"},
    {"target": "http://127.0.0.1:8001", "team": "QA", "no_fix": "false"},
])
def test_request_shape_rejects_wrong_json_types(body):
    resp = client.post("/api/run", json=body)

    assert resp.status_code == 400
    assert resp.json()["message"]


def test_malformed_json_is_a_client_error():
    resp = client.post("/api/run", content=b"{", headers={"content-type": "application/json"})

    assert resp.status_code == 400
    assert resp.json()["error"] == "Request body must be valid JSON"


def test_run_streams_four_attacks_then_grade():
    started = client.post("/api/run", json={"target": "http://127.0.0.1:8001",
                                           "team": "QA Web", "no_fix": True})
    assert started.status_code == 200
    run_id = started.json()["run_id"]

    events = []
    with client.stream("GET", f"/api/run/{run_id}/events") as s:
        current = None
        for line in s.iter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((current, json.loads(line.split(":", 1)[1].strip())))
            if current == "done":
                break

    kinds = [e[0] for e in events]
    assert kinds.count("attack") == 4
    assert "result" in kinds
    result = next(d for k, d in events if k == "result")
    assert result["letter"] == "F"
    assert result["score"] == 5
    assert result["attacks_landed"] == 4
    assert result["slack"] == "delivered"


def test_worker_error_does_not_reflect_exception_content(monkeypatch):
    monkeypatch.setattr(web_app, "run_suite", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("QA_REFLECTED_MARKER")
    ))
    started = client.post("/api/run", json={
        "target": "http://127.0.0.1:8001", "team": "QA", "no_fix": True,
    })
    run_id = started.json()["run_id"]

    error = None
    with client.stream("GET", f"/api/run/{run_id}/events") as stream:
        current = None
        for line in stream.iter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and current == "error":
                error = json.loads(line.split(":", 1)[1].strip())
            if current == "done":
                break

    assert "RuntimeError" in error["message"]
    assert "QA_REFLECTED_MARKER" not in error["message"]


def test_leaderboard_endpoint_returns_json():
    resp = client.get("/api/leaderboard")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
