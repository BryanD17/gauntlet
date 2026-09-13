"""The single entry command.

  python -m gauntlet.cli run --target http://localhost:8001 --repo owner/name --team "Team"

Runs all scenarios, prints the grade, writes evidence, renders the report card and
updates the leaderboard, posts to Slack, and opens a fix PR per failure. Every external
step degrades gracefully with a printed warning; the run itself never crashes.
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .runner import run_suite
from .grader import grade
from . import report, manifest
from .notify import post_to_slack
from .validate import validate_target, validate_repo


def _run(args) -> int:
    load_dotenv()
    started = time.monotonic()
    warnings: list[str] = []
    ts_display = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 0. Validate inputs before touching anything external (config errors -> exit 3).
    try:
        validate_target(args.target, allow_remote=args.allow_remote)
        validate_repo(args.repo)
    except ValueError as exc:
        print(f"! configuration error: {exc}")
        return 3

    print(f"\nGAUNTLET  ::  examining {args.team}  ->  {args.target}\n")

    # 1. Attack suite (never raises; unreachable scenarios come back as ERROR).
    try:
        results, run_dir = run_suite(args.target, timeout=args.timeout)
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        print(f"\n! Could not run the suite against {args.target}: {exc}")
        print("  Is the target agent running? Aborting cleanly.\n")
        return 1

    # 2. Grade.
    g = grade(results)
    print(f"\n  GRADE  {g.letter}  ({g.score}/100)")
    print(f"  attacks caught {g.attacks_caught}   landed {g.attacks_landed}   "
          f"false alarms {g.false_alarms}")
    if any(r.verdict == "ERROR" for r in results):
        print("  (some scenarios could not be tested - target error; see report)")

    # 3. Report card + leaderboard.
    try:
        report_path = report.render_report(g, args.team, args.target, ts_display)
        board_path = report.update_leaderboard(g, args.team, ts_display)
        print(f"\n  report      {report_path}")
        print(f"  leaderboard {board_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! report rendering failed: {exc}")
        report_path = None
        warnings.append(f"report: render failed ({exc})")

    # 4. Slack.
    top_failure = next((r.title for r in results if r.landed), "None")
    if not post_to_slack(args.team, g.letter, g.score, top_failure,
                         report_path=str(report_path) if report_path else None):
        warnings.append("slack: not delivered")

    # 5. Fix PRs (only if a repo is given and there were failures).
    failures = [r for r in results if r.verdict == "FAIL"]
    if args.repo and failures and not getattr(args, "no_fix", False):
        from . import fixer, github_pr
        source_file = Path(args.source)
        if not source_file.exists():
            print(f"  ! source file {source_file} not found; skipping fixes")
            warnings.append(f"fix: source {source_file} not found")
        else:
            try:
                src = source_file.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                print(f"  ! source file {source_file} unreadable ({type(exc).__name__}); skipping fixes")
                warnings.append(f"fix: source {source_file} unreadable ({type(exc).__name__})")
            else:
                print(f"\n  generating fixes for {len(failures)} failure(s) via Anthropic ...")
                fixes = fixer.generate_fixes(failures, src, args.source.replace("\\", "/"))
                detail_by_scenario = {r.scenario: r.detail for r in results}
                for fix in fixes:
                    if not github_pr.open_fix_pr(args.repo, fix, run_dir,
                                                 detail_by_scenario.get(fix.scenario, "")):
                        warnings.append(f"pr:{fix.scenario}: not opened (patch saved to run dir)")
    elif args.repo and getattr(args, "no_fix", False):
        print("\n  --no-fix: skipping fixer and PRs (no source leaves the machine)")
    elif args.repo:
        print("\n  no failures - no fix PRs needed.")
    else:
        print("\n  (no --repo given; skipping fix PRs)")

    # 6. Linear issues (best-effort, one per real failure).
    real_failures = [r for r in results if r.verdict == "FAIL"]
    if real_failures:
        from .linear import file_failures
        urls = file_failures(args.team, real_failures,
                             report_path=str(report_path) if report_path else None)
        for u in urls:
            print(f"  Linear issue: {u}")
        if not urls:
            warnings.append("linear: no issues filed")

    # 7. Run manifest (self-contained; enables offline replay).
    try:
        mpath = manifest.write_manifest(
            run_dir, target=args.target, team=args.team, timestamp=ts_display,
            grade=g, seed=run_dir.name, wall_time_s=time.monotonic() - started,
            warnings=warnings)
        print(f"\n  manifest    {mpath}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! manifest write failed: {exc}")

    if warnings:
        print("  warnings:")
        for w in warnings:
            print(f"    - {w}")
    print(f"  evidence    {run_dir}\n  done.\n")

    # Exit taxonomy: 2 if the target was unreachable for every scenario, else 0
    # (0 stands even when some integrations degraded — the core grade was delivered).
    if results and all(r.verdict == "ERROR" for r in results):
        return 2
    return 0


def _replay(args) -> int:
    """Re-render a report card purely from a stored run manifest. No external calls."""
    from .attacks import Result
    from .grader import Grade
    run_dir = Path(args.run)
    try:
        data = manifest.load_manifest(run_dir)
        results = [Result.from_json(r) for r in data["grade"]["results"]]
        g = Grade.from_json(data["grade"], results)
        out = report.render_report(g, data["team"], data["target"], data["timestamp"])
    except Exception as exc:  # noqa: BLE001
        print(f"! could not replay manifest at {run_dir} ({type(exc).__name__})")
        return 3
    print(f"replayed {data['team']}  grade {g.letter} ({g.score})  ->  {out}")
    print(f"  gauntlet {data['gauntlet_version']}  grading v{data['grading_version']}  "
          f"commit {data['git_commit']}  from {run_dir}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gauntlet", description="Red-team an AI agent.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the full examination")
    run.add_argument("--target", required=True, help="target agent base URL")
    run.add_argument("--repo", default=None, help="owner/name of the target repo for fix PRs")
    run.add_argument("--team", required=True, help="team name for the report and leaderboard")
    run.add_argument("--source", default="agents/naive_agent.py",
                     help="path to the target's source file (local read + repo path)")
    run.add_argument("--no-fix", action="store_true",
                     help="skip the fixer and PRs entirely (no source leaves the machine)")
    run.add_argument("--allow-remote", action="store_true",
                     help="permit non-local target hosts (off by default; SSRF guard)")
    run.add_argument("--timeout", type=float, default=10.0,
                     help="per-request timeout in seconds for the target (default 10)")

    rep = sub.add_parser("replay", help="re-render a report card from a stored run, offline")
    rep.add_argument("--run", required=True, help="path to a runs/<timestamp> directory")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "replay":
        return _replay(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
