"""Branch and PR creation via PyGithub. Never pushes to main.

For each FixProposal we create a fresh branch off the default branch, commit the
corrected file to that branch only, and open a pull request. Main is never written.
If anything GitHub-related fails, the patch is written to runs/<ts>/patches/ and the
run continues.

Least privilege — the ONLY write APIs this module calls are:
  * create_git_ref        (create a new branch)
  * update_file           (commit the fix to that branch only)
  * create_pull           (open a pull request against the default branch)
A fine-grained PAT scoped to the single target repo with **Contents: read/write** and
**Pull requests: read/write** is sufficient. No other write scope is needed, and the
default branch is never written, force-pushed, merged, or deleted.
"""

import os
from datetime import datetime, timezone
from pathlib import Path


def _write_patch_fallback(fix, run_dir: Path, reason: str) -> None:
    patches = run_dir / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    (patches / f"{fix.scenario}.diff").write_text(fix.diff, encoding="utf-8")
    (patches / f"{fix.scenario}.{Path(fix.filename).name}").write_text(
        fix.fixed_source, encoding="utf-8")
    print(f"  ! GitHub unavailable ({reason}); wrote patch to {patches}")


def open_fix_pr(repo_full_name: str, fix, run_dir: Path, evidence_detail: str = "") -> str | None:
    """Open one PR for a fix on its own branch, or write a fallback patch. Returns URL or None."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        _write_patch_fallback(fix, run_dir, "GITHUB_TOKEN not set")
        return None
    try:
        from github import Github, GithubException
    except ImportError:
        _write_patch_fallback(fix, run_dir, "PyGithub not installed")
        return None

    try:
        gh = Github(token)
        repo = gh.get_repo(repo_full_name)
        base = repo.default_branch
        if base == "":
            raise RuntimeError("no default branch")
        base_sha = repo.get_branch(base).commit.sha

        branch = f"gauntlet/fix-{fix.scenario}"
        ref = f"refs/heads/{branch}"
        try:
            repo.create_git_ref(ref=ref, sha=base_sha)
        except GithubException:
            # Branch already exists from a previous run: make it unique.
            stamp = datetime.now(timezone.utc).strftime("%H%M%S")
            branch = f"gauntlet/fix-{fix.scenario}-{stamp}"
            repo.create_git_ref(ref=f"refs/heads/{branch}", sha=base_sha)

        # Update the target file on the new branch only (never on base/main).
        existing = repo.get_contents(fix.filename, ref=branch)
        repo.update_file(
            path=fix.filename,
            message=f"Gauntlet fix: {fix.scenario}",
            content=fix.fixed_source,
            sha=existing.sha,
            branch=branch,
        )

        body = (
            f"## Gauntlet fix: {fix.scenario}\n\n"
            f"**Failing scenario:** {fix.scenario}\n\n"
            f"**Evidence:** {evidence_detail or fix.explanation}\n\n"
            f"**Change:** {fix.explanation}\n\n"
            f"```diff\n{fix.diff[:5000]}\n```\n\n"
            f"Gauntlet never pushes to `{base}`; review and merge this branch.\n\n"
            f"🤖 Generated with [Claude Code](https://claude.com/claude-code)\n\n"
            f"https://claude.ai/code/session_01PP6RyT932SJ3XyskmwuATa"
        )
        pr = repo.create_pull(
            title=f"Gauntlet fix: {fix.scenario}",
            body=body, head=branch, base=base,
        )
        print(f"  PR opened: {pr.html_url}")
        return pr.html_url
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        _write_patch_fallback(fix, run_dir, str(exc))
        return None
