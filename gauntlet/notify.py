"""Post Gauntlet results to a Slack incoming webhook."""

import os

import httpx


def post_to_slack(team: str, letter: str, score: int, top_failure: str, report_path: str | None = None) -> bool:
    """Post a Gauntlet result using SLACK_WEBHOOK_URL; return False on failure."""
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        print("  ! SLACK_WEBHOOK_URL not set; skipping Slack post")
        return False

    payload = {
        "text": f"Gauntlet: {team} graded {letter} ({score})",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Gauntlet report: {team}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "plain_text", "text": f"Grade\n{letter} ({score})"},
                    {"type": "plain_text", "text": f"Top failure\n{top_failure or 'None'}"},
                ],
            },
        ],
    }
    if report_path:
        payload["blocks"].append(
            {
                "type": "context",
                "elements": [{"type": "plain_text", "text": report_path}],
            }
        )

    try:
        resp = httpx.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"  ! Slack post failed: HTTP {resp.status_code}")
        return resp.status_code == 200
    except Exception as exc:
        print(f"  ! Slack post failed ({type(exc).__name__})")
        return False


if __name__ == "__main__":
    print(post_to_slack("Test Team", "A", 100, "None"))
