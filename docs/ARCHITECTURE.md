# Architecture

One sentence per module — what it owns and what it refuses to know about.

- **`gauntlet/harness.py`** owns the contract (Task/Action dataclasses, defensive `parse_actions`) and refuses to know how any attack or agent works.
- **`gauntlet/attacks.py`** owns the four attack scenarios and their deterministic check functions plus the idempotency-modeling executor, and refuses to make HTTP calls itself.
- **`gauntlet/runner.py`** owns talking to the target over HTTP and writing per-run evidence, and refuses to grade or render anything.
- **`gauntlet/grader.py`** owns scoring, the letter grade, and the category breakdown, and refuses to know how a verdict was reached.
- **`gauntlet/report.py`** owns rendering the report card, leaderboard, and landing page from data, and refuses to run attacks or contact a target.
- **`gauntlet/fixer.py`** owns turning a failure plus target source into a patch via the Anthropic API, and refuses to touch git or GitHub.
- **`gauntlet/github_pr.py`** owns branch and pull-request creation, and refuses to write the default branch.
- **`gauntlet/notify.py`** owns the Slack summary post, and **`gauntlet/linear.py`** owns filing one issue per failure — both refuse to raise.
- **`gauntlet/manifest.py`** owns the self-contained run manifest that makes offline replay possible, and refuses to contact anything external.
- **`gauntlet/validate.py`** owns input validation (safe slug, repo shape, SSRF-guarded target), and **`gauntlet/cli.py`** owns wiring every step into one command and the exit-code taxonomy — the CLI refuses to embed any step's internal logic.
