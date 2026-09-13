# Changelog

## 0.1.0

Built at the Multi-App AI Agent Hackathon, September 13, 2026.

- Four attack families: prompt injection, duplicate delivery, mid-write failure, stale/conflicting data.
- Evidence-backed letter grade (A–F), weighted so safety failures cost the most, with attacks caught / landed / false alarms.
- Styled report card and leaderboard web pages; public landing page.
- Deterministic, replayable runs: per-run evidence, self-contained manifest, and an offline `replay` command.
- Fix loop: an Anthropic-generated patch opened as a pull request per failure (never touches main).
- Integrations: GitHub (fix PRs), Slack (result post), Linear (issue per failure).
- Security: input validation with SSRF guard, secrets scanner, autoescaped rendering, least-privilege integrations, `--no-fix` to keep source local.
- Two reference agents (naive → F, hardened → A) so the full loop demos end to end with no external participants.
