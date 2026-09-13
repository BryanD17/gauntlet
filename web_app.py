"""Gauntlet web console — a thin FastAPI layer over the existing engine (port 8080).

It adds NO grading logic. Every examination goes through the same functions the CLI
calls: gauntlet.runner.run_suite, gauntlet.grader.grade, gauntlet.report, the same
validators, and the same Slack/Linear/GitHub integrations. The only engine hook it
uses is run_suite's optional on_result callback, which streams each attack verdict to
the browser as it resolves and changes nothing about the grade or the evidence.

Run:  python web_app.py         (or: uvicorn web_app:app --port 8080)
"""

import json
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import (HTMLResponse, JSONResponse, RedirectResponse,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from gauntlet import report, manifest
from gauntlet.runner import run_suite
from gauntlet.grader import grade, GRADING_VERSION
from gauntlet.validate import validate_target, validate_repo, safe_slug
from gauntlet.notify import post_to_slack

load_dotenv()

ROOT = Path(__file__).resolve().parent
WEB_TEMPLATES = ROOT / "web" / "templates"
WEB_STATIC = ROOT / "web" / "static"
SITE = ROOT / "site"
DEFAULT_SOURCE = ROOT / "agents" / "naive_agent.py"

app = FastAPI(title="Gauntlet")
SITE.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(WEB_STATIC)), name="static")
app.mount("/site", StaticFiles(directory=str(SITE), html=True), name="site")

_env = Environment(
    loader=FileSystemLoader(str(WEB_TEMPLATES)),
    autoescape=select_autoescape(["html", "j2"]),
)

# One examination at a time (queue of one); the leaderboard write is already atomic.
_RUN_LOCK = threading.Lock()
_RUNS: dict[str, queue.Queue] = {}


def _render(template_name: str, **ctx) -> HTMLResponse:
    """Render a Codex-owned template if present; otherwise a minimal inline fallback so
    the backend is usable before the frontend lands (and after, it uses the real page)."""
    try:
        html = _env.get_template(template_name).render(**ctx)
        return HTMLResponse(html)
    except Exception:  # noqa: BLE001 - template not built yet
        return HTMLResponse(_fallback(template_name), status_code=200)


def _fallback(name: str) -> str:
    links = ('<p><a href="/console">Run console</a> · '
             '<a href="/leaderboard">Leaderboard</a> · '
             '<a href="/site/report-naive-reference.html">Naive F</a> · '
             '<a href="/site/report-hardened-reference.html">Hardened A</a></p>')
    return (f"<!doctype html><meta charset=utf-8><title>Gauntlet</title>"
            f"<body style='background:#0E0F12;color:#EDEAE3;font:15px/1.6 system-ui;"
            f"max-width:960px;margin:40px auto;padding:0 16px'>"
            f"<h1 style='font-weight:700'>GAUNTLET</h1>"
            f"<p>Web console backend is live on :8080. The <code>{name}</code> page is "
            f"being built by the frontend task.</p>{links}</body>")


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return _render("landing.html.j2",
                   naive_report="/site/report-naive-reference.html",
                   hardened_report="/site/report-hardened-reference.html",
                   grading_version=GRADING_VERSION)


@app.get("/console", response_class=HTMLResponse)
def console(request: Request):
    return _render("console.html.j2")


@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_page(request: Request):
    try:
        return HTMLResponse(_env.get_template("leaderboard_page.html.j2").render())
    except Exception:  # noqa: BLE001
        board = SITE / "leaderboard.html"
        if board.exists():
            return RedirectResponse("/site/leaderboard.html")
        return _render("leaderboard_page.html.j2")


@app.get("/report/{team}", response_class=HTMLResponse)
def report_by_team(team: str):
    path = SITE / f"report-{safe_slug(team)}.html"
    if path.exists():
        return RedirectResponse(f"/site/report-{safe_slug(team)}.html")
    return HTMLResponse(_fallback(f"report-{safe_slug(team)}"), status_code=404)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/leaderboard")
def api_leaderboard():
    store = SITE / "leaderboard.json"
    rows = []
    if store.exists():
        try:
            rows = json.loads(store.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            rows = []
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return JSONResponse(rows)


@app.post("/api/run")
async def api_run(request: Request):
    body = await request.json()
    target = str(body.get("target", "")).strip()
    repo = (body.get("repo") or "").strip() or None
    team = str(body.get("team", "")).strip() or "Anonymous agent"
    no_fix = bool(body.get("no_fix", False))
    allow_remote = bool(body.get("allow_remote", False))

    # Validate before anything external (same validators as the CLI).
    try:
        validate_target(target, allow_remote=allow_remote)
        validate_repo(repo)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    run_id = uuid.uuid4().hex[:12]
    q: queue.Queue = queue.Queue()
    _RUNS[run_id] = q
    threading.Thread(
        target=_do_run,
        args=(run_id, target, repo, team, no_fix),
        daemon=True,
    ).start()
    return JSONResponse({"run_id": run_id})


def _emit(q: queue.Queue, event: str, data: dict) -> None:
    q.put((event, data))


def _do_run(run_id: str, target: str, repo, team: str, no_fix: bool) -> None:
    q = _RUNS[run_id]
    ts_display = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    warnings: list[str] = []
    started = time.monotonic()
    with _RUN_LOCK:
        try:
            def on_result(r):
                _emit(q, "attack", {"scenario": r.scenario, "title": r.title,
                                    "verdict": r.verdict, "detail": r.detail,
                                    "penalty": r.penalty})
            results, run_dir = run_suite(target, timeout=10.0, on_result=on_result)
            g = grade(results)

            report_path = report.render_report(g, team, target, ts_display)
            report.update_leaderboard(g, team, ts_display)
            slug = safe_slug(team)
            report_url = f"/site/report-{slug}.html"

            # Fix PRs (best-effort; only real failures, only with a repo, honoring no-fix).
            pr_urls, linear_urls = [], []
            failures = [r for r in results if r.verdict == "FAIL"]
            if repo and failures and not no_fix and DEFAULT_SOURCE.exists():
                from gauntlet import fixer, github_pr
                src = DEFAULT_SOURCE.read_text(encoding="utf-8")
                fixes = fixer.generate_fixes(failures, src, "agents/naive_agent.py")
                detail_by = {r.scenario: r.detail for r in results}
                for fix in fixes:
                    url = github_pr.open_fix_pr(repo, fix, run_dir, detail_by.get(fix.scenario, ""))
                    if url:
                        pr_urls.append(url)

            # Linear issues (best-effort).
            if failures:
                from gauntlet.linear import file_failures
                linear_urls = file_failures(team, failures, report_path=report_url)

            slack_ok = post_to_slack(team, g.letter, g.score,
                                     next((r.title for r in results if r.landed), "None"),
                                     report_path=report_url)

            try:
                manifest.write_manifest(run_dir, target=target, team=team,
                                        timestamp=ts_display, grade=g, seed=run_dir.name,
                                        wall_time_s=time.monotonic() - started,
                                        warnings=warnings)
            except Exception:  # noqa: BLE001
                pass

            _emit(q, "result", {
                "letter": g.letter, "score": g.score,
                "attacks_caught": g.attacks_caught, "attacks_landed": g.attacks_landed,
                "false_alarms": g.false_alarms,
                "report_url": report_url, "pr_urls": pr_urls, "linear_urls": linear_urls,
                "slack": "delivered" if slack_ok else "not delivered",
                "team": team, "grading_version": GRADING_VERSION,
            })
        except Exception as exc:  # noqa: BLE001 - never crash the server
            _emit(q, "error", {"message": f"{type(exc).__name__}: {exc}"})
        finally:
            _emit(q, "done", {})


@app.get("/api/run/{run_id}/events")
def api_events(run_id: str):
    q = _RUNS.get(run_id)
    if q is None:
        return JSONResponse({"error": "unknown run id"}, status_code=404)

    def stream():
        yield "retry: 3000\n\n"
        while True:
            try:
                event, data = q.get(timeout=30)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
            if event == "done":
                break
        _RUNS.pop(run_id, None)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
