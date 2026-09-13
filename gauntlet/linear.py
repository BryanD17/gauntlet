"""File Gauntlet failures as Linear issues; external errors never stop a run."""

import os

import httpx

ENDPOINT = "https://api.linear.app/graphql"


def _warn(message: str) -> None:
    print(f"  ! {' '.join(message.splitlines())}")


def _graphql(query: str, variables: dict | None = None) -> dict | None:
    key = os.environ.get("LINEAR_API_KEY")
    if not key:
        _warn("LINEAR_API_KEY not set; skipping Linear")
        return None
    try:
        response = httpx.post(
            ENDPOINT,
            headers={"Authorization": key},
            json={"query": query, "variables": variables or {}},
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or body.get("errors"):
            _warn("Linear returned a GraphQL error or invalid response")
            return None
        data = body.get("data")
        if not isinstance(data, dict):
            _warn("Linear response has no data")
            return None
        return data
    except Exception as exc:
        # Do not print response bodies, headers, or exception messages: upstream
        # failures may echo credentials or target-provided content into logs.
        _warn(f"Linear request failed ({type(exc).__name__})")
        return None


def _team_id() -> str | None:
    configured = os.environ.get("LINEAR_TEAM_ID")
    if configured:
        return configured
    data = _graphql("query { teams(first: 1) { nodes { id } } }")
    if data is None:
        return None
    teams = data.get("teams")
    nodes = teams.get("nodes") if isinstance(teams, dict) else None
    if isinstance(nodes, list) and nodes and isinstance(nodes[0], dict):
        team_id = nodes[0].get("id")
        if isinstance(team_id, str) and team_id:
            return team_id
    _warn("Linear returned no accessible team")
    return None


def file_issue(title: str, description: str) -> str | None:
    if not os.environ.get("LINEAR_API_KEY"):
        _warn("LINEAR_API_KEY not set; skipping Linear")
        return None
    team_id = _team_id()
    if not team_id:
        return None
    data = _graphql(
        "mutation issueCreate($input: IssueCreateInput!) { "
        "issueCreate(input: $input) { success issue { url } } }",
        {"input": {"teamId": team_id, "title": title, "description": description}},
    )
    if data is None:
        return None
    created = data.get("issueCreate")
    if isinstance(created, dict) and created.get("success") is True:
        issue = created.get("issue")
        url = issue.get("url") if isinstance(issue, dict) else None
        if isinstance(url, str) and url:
            return url
    _warn("Linear did not confirm issue creation")
    return None


def file_failures(team: str, failures: list, report_path: str | None = None) -> list[str]:
    if not os.environ.get("LINEAR_API_KEY"):
        _warn("LINEAR_API_KEY not set; skipping Linear")
        return []
    urls = []
    for result in failures:
        try:
            description = (
                f"## Scenario\n{result.scenario}\n\n"
                f"## What happened\n{result.detail}\n\n"
                f"## Required behavior\n{result.required}\n"
            )
            if report_path:
                description += f"\n## Report\n{report_path}\n"
            url = file_issue(f"[Gauntlet] {team}: {result.title} failed", description)
            if url:
                urls.append(url)
        except Exception as exc:
            _warn(f"Linear failure could not be filed ({type(exc).__name__})")
    return urls


if __name__ == "__main__":
    print(_team_id())
