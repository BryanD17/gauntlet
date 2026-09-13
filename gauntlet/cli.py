"""The single entry command.

  python -m gauntlet.cli run --target http://localhost:8001 --repo owner/name --team "Team"

Runs all scenarios, prints the grade, writes evidence, renders the report card and
updates the leaderboard, posts to Slack, and opens a fix PR per failure. Every external
step degrades gracefully with a printed warning; the run itself never crashes.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .runner import run_suite
from .grader import grade
from . import report
from .notify import post_to_slack


def _run(args) -> int:
    load_dotenv()
    ts_display = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print(f"\nGAUNTLET  ::  examining {args.team}  ->  {args.target}\n")

    # 1. Attack suite (never raises; unreachable scenarios come back as ERROR).
    try:
        results, run_dir = run_suite(args.target)
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

    # 4. Slack.
    top_failure = next((r.title for r in results if r.landed), "None")
    post_to_slack(args.team, g.letter, g.score, top_failure,
                  report_path=str(report_path) if report_path else None)

    # 5. Fix PRs (only if a repo is given and there were failures).
    failures = [r for r in results if r.verdict in ("FAIL", "ERROR")]
    if args.repo and failures:
        from . import fixer, github_pr
        source_file = Path(args.source)
        if not source_file.exists():
            print(f"  ! source file {source_file} not found; skipping fixes")
        else:
            src = source_file.read_text(encoding="utf-8")
            print(f"\n  generating fixes for {len(failures)} failure(s) via Anthropic ...")
            fixes = fixer.generate_fixes(failures, src, args.source.replace("\\", "/"))
            detail_by_scenario = {r.scenario: r.detail for r in results}
            for fix in fixes:
                github_pr.open_fix_pr(args.repo, fix, run_dir,
                                      detail_by_scenario.get(fix.scenario, ""))
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

    print(f"\n  evidence    {run_dir}\n  done.\n")
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
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
