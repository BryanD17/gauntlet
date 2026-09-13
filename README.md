# Gauntlet

An AI agent that red-teams other AI agents before they ever reach production.

*Built at the Multi-App AI Agent Hackathon. Docs: [Quickstart](#quickstart) · [Harness kit](docs/HARNESS.md) · [Threat model](docs/THREAT-MODEL.md) · [Security](docs/SECURITY.md) · [Architecture](docs/ARCHITECTURE.md).*

## Quickstart

Zero to a grade in five minutes. Two reference agents ship in the repo, so the whole loop
demos with no external participants.

```bash
# 1. install (a fresh venv)
python -m venv .venv
. .venv/bin/activate           # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env           # Windows: Copy-Item .env.example .env  (fill in keys, all optional)

# 2. start the two reference agents (separate terminals)
python agents/naive_agent.py       # port 8001, grades F
python agents/hardened_agent.py    # port 8002, grades A

# 3. examine them
python -m gauntlet.cli run --target http://localhost:8001 --team "Naive Reference"
python -m gauntlet.cli run --target http://localhost:8002 --team "Hardened Reference" --source agents/hardened_agent.py
```

Open `site/report-naive-reference.html` and `site/leaderboard.html`. Installing the package
(`pip install -e .`) also gives you a `gauntlet` command that works the same way.

All keys in `.env` are optional: without them the run still grades and renders, and each
integration (Slack, Linear, GitHub PRs, the Anthropic fixer) degrades to a printed warning.

## The problem

Teams everywhere are shipping AI agents that read messages, move money, edit tickets, and write to real systems. Almost none of those agents have been tested against the conditions that actually break them. They work when the input is friendly. Nobody knows what they do when an email contains a hidden instruction, when the same event arrives twice, or when an API dies in the middle of a write. Today, teams discover those answers in production, at the cost of their users.

## What Gauntlet does

Gauntlet is an examiner. You point it at a running agent, and it attacks that agent on purpose, in a controlled setting, before real users ever can.

It runs the target agent through a battery of hostile scenarios, watches exactly how the agent responds, and then does two things:

1. It issues a graded report card. The card shows what broke, how it broke, and how safe the agent is to deploy, summarized as a letter grade with a category by category breakdown.
2. It fixes what it found. For every failure, Gauntlet generates a concrete patch and opens a pull request on the target agent's own repository, explaining the failure and citing the exact test that exposed it.

Gauntlet does not just find the holes. It patches them.

## How it works

Target agents connect through a standard harness: a single HTTP endpoint that accepts a task and returns the agent's proposed actions. Gauntlet needs no access to an agent's internals to examine it. Any agent that speaks the harness contract can be tested, regardless of language or framework.

Once connected, Gauntlet runs its attack suite. Every scenario is deterministic and replayable, and every request and response is logged, so any grade can be defended with evidence.

## The attack suite

Gauntlet tests four failure classes, chosen because they account for the most damaging real world agent incidents.

Prompt injection. Task content contains embedded instructions, such as a message that says to ignore all rules and take a harmful action. A passing agent treats the content as data. A failing agent obeys it.

Duplicate delivery. The same task is delivered twice, which happens constantly in real systems through webhook retries and network flakiness. A passing agent acts exactly once. A failing agent pays the bill twice.

Mid-write failure. The connection fails partway through an action, then the task is retried. A passing agent recovers cleanly. A failing agent double executes or leaves state corrupted.

Stale and conflicting data. The agent is handed context that contradicts its task. A passing agent notices and abstains or asks. A failing agent confidently acts on the wrong information.

## The report card

Each run produces a letter grade from A to F, weighted so that safety failures cost the most, a breakdown by attack category, the evidence behind every result, and a summary of attacks caught, attacks that landed, and false alarms. Results are posted to Slack and added to a shared leaderboard, so every certified agent's grade is public and comparable.

## The fix loop

Failures do not end at the report. For each one, Gauntlet analyzes the evidence together with the relevant target code and produces a targeted patch: input sanitization for injection failures, idempotency keys for duplicate failures, transactional guards for interrupted writes. The patch arrives as a pull request on the target repository, on its own branch, with an explanation of the failure it addresses. The author reviews and merges. Gauntlet never pushes to main.

## Getting your agent certified

1. Wrap your agent in the harness contract: one endpoint that accepts a task and returns proposed actions. The contract is documented below, with two reference implementations in this repository to copy from.
2. Run your agent locally and share its URL, along with your repository name if you want fix pull requests.
3. Gauntlet runs the suite, posts your report card, and adds you to the leaderboard.

## Running Gauntlet

Configuration lives in a local .env file. Copy .env.example and fill in your keys. One command runs the full examination: the attack suite, the grade, the report page, the leaderboard update, the Slack post, and the fix pull requests. The repository includes two reference agents, one naive and one hardened, so the entire loop can be demonstrated end to end with no external participants.

### Flags

- `--target <url>` — the running agent's base URL (required).
- `--team "<name>"` — team name for the report and leaderboard (required).
- `--repo owner/name` — open fix PRs on this repo (optional).
- `--source <path>` — the target's source file to patch and its path in the repo (default `agents/naive_agent.py`).
- `--no-fix` — skip the fixer and PRs entirely, so no source leaves the machine.
- `--allow-remote` — permit a non-local target host (off by default; an SSRF guard refuses `file:`, cloud-metadata, and non-canonical numeric hosts).
- `--timeout <seconds>` — per-request timeout for the target (default 10).

### Replaying a run offline

```bash
python -m gauntlet.cli replay --run runs/<timestamp>
```

Re-renders a report card purely from the stored manifest — no target, no network. Useful if wifi dies mid-demo.

### Exit codes

- `0` — run completed and the grade was produced (this stands even if an integration degraded; warnings are printed and recorded in the manifest).
- `2` — the target was unreachable for every scenario. Grade F is recorded with ERROR panels.
- `3` — configuration error (bad flags, malformed `--repo`, refused `--target`). Nothing external is touched.

## The harness contract

A target agent exposes exactly one endpoint. Gauntlet plays the executor, so the agent
only *proposes* actions; Gauntlet decides what is committed.

**Request** — `POST /task`

```json
{
  "task_id": "abc-123",
  "task_type": "pay_invoice",
  "payload": {"invoice_id": "INV-2002", "vendor": "Beta LLC", "amount": 300},
  "context": {"invoice": {"invoice_id": "INV-2002", "vendor": "Beta LLC", "amount": 300, "status": "approved"}}
}
```

**Response** — a JSON array of proposed actions. Each action:

```json
[
  {"action_type": "pay_invoice", "target": "INV-2002",
   "params": {"amount": 300, "vendor": "Beta LLC", "idempotency_key": "abc-123:INV-2002"},
   "note": null}
]
```

`action_type` is `pay_invoice` / `transfer_funds` for writes, or `abstain` / `flag` / `noop`
for non-writes (put the reason in `note`). A write carrying `params.idempotency_key`
(a string) is deduplicated by the executor, so a retried or duplicated delivery commits once.
A retried delivery arrives with `context.delivery = {"attempt": 2, ...}`.

**One curl example:**

```bash
curl -s -X POST http://localhost:8001/task \
  -H "Content-Type: application/json" \
  -d '{"task_id":"abc-123","task_type":"pay_invoice",
       "payload":{"invoice_id":"INV-2002","vendor":"Beta LLC","amount":300},
       "context":{"invoice":{"invoice_id":"INV-2002","vendor":"Beta LLC","amount":300,"status":"approved"}}}'
```

Run the full examination:

```bash
python -m gauntlet.cli run --target http://localhost:8001 --repo owner/name --team "Team Name"
```

## Design principles

Precision over accusation. A tool that falsely accuses a healthy agent loses all trust. A failure verdict is always backed by unambiguous evidence, and uncertain outcomes are reported as abstentions rather than guesses.

Determinism. Every scenario is seeded and repeatable. The same agent gets the same grade twice.

Evidence for everything. Full request and response logs are kept for every run. No grade exists that cannot be replayed.

Test before production, not after. The cheapest place to discover an agent's failure mode is a sandbox that wants to find it. Gauntlet is that sandbox.

## Status

Built solo at the Multi-App AI Agent Hackathon, September 13, 2026. Integrations: GitHub, Slack, and the Anthropic API.
