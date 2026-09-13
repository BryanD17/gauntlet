# Gauntlet security

Gauntlet examines untrusted agents, so it is built to be safe both for the person running
it and against the hostile agent it grades. One page, no filler.

## What Gauntlet touches

- **The target agent** — HTTP `POST /task` only, to the URL you pass. By default the target
  host must be local or private (`localhost`, `127.0.0.1`, `::1`, RFC-1918, `*.local`); pass
  `--allow-remote` to permit a public host. `file:` and cloud-metadata addresses
  (`169.254.169.254`, non-canonical numeric hosts) are always refused (SSRF guard, `gauntlet/validate.py`).
- **The local disk** — `runs/` (evidence, manifest, logs) and `site/` (rendered HTML). Both gitignored.
- **GitHub** (only with `--repo`, only on failures) — creates a branch, creates/updates the target
  file **on that branch only**, opens a pull request. It never writes to the default branch. See the
  permission block in `gauntlet/github_pr.py`.
- **Slack** (only with `SLACK_WEBHOOK_URL`) — posts a short summarized result. No raw evidence.
- **Linear** (only with `LINEAR_API_KEY`) — creates one issue per failure. Issue creation only.
- **The Anthropic API** (only when generating fixes) — see "What leaves the machine" below.

## What Gauntlet never touches

- The default/main branch of any repo. It never force-pushes, deletes, or merges.
- Any GitHub write beyond branch + file-on-branch + pull request.
- Your `.env` — it is loaded into the process only; never printed, logged, or committed.
- Reads of existing Slack or Linear workspace data beyond what filing requires.

## What leaves the machine

- **To the target:** the seeded attack payloads (no secrets).
- **To GitHub/Slack/Linear:** summaries and, for a fix PR, the proposed patch.
- **To the Anthropic API (fixer only):** the failing scenario's evidence **and the relevant target
  source file**, so a minimal patch can be generated. If you cannot share source externally, run with
  **`--no-fix`** — the full examination completes (grade, report, leaderboard, Slack, Linear) with no
  Anthropic call and no source leaving the machine.

## Handling the hostile agent's output

The target is untrusted, so everything it returns is treated as attacker-controlled:

- Responses are parsed defensively (`gauntlet/harness.py`): non-object actions, non-string
  `idempotency_key`, and parse failures become recorded evidence, never a crash.
- All agent-derived text is HTML-autoescaped in the report (jinja2), so an agent cannot XSS the
  examiner. The operator-supplied team name is additionally stripped of backslashes/control chars and
  capped, and no absolute local path is ever rendered into the pages.
- Every external call degrades to a printed warning and a note in the run manifest — Slack, Linear,
  GitHub, or Anthropic being down never produces a traceback.

## Token scoping

- **GitHub:** a fine-grained PAT scoped to the single target repo with **Contents: read/write** and
  **Pull requests: read/write** is sufficient. Nothing else is needed.
- **Slack:** an incoming-webhook URL (single channel).
- **Linear:** a personal API key (issue create).
- **Anthropic:** a standard API key; used only by the fixer.

## Secrets discipline

`scripts/check_secrets.py` scans tracked files for credential-shaped strings (never printing the
value) and is wired into CI. `.env` is gitignored; `.env.example` carries keys only.

## Dependency hygiene

Dependencies are pinned in `requirements.txt`. Run `pip-audit -r requirements.txt` if network permits.
*(pip-audit not run in the build environment; no advisories recorded at 0.1.0.)*

## Reporting a vulnerability

Open a private security advisory on the GitHub repository, or email the maintainer listed in
`pyproject.toml`. Please do not file a public issue with exploit details.
