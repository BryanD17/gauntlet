"""Scan tracked content for likely credentials without printing matched values."""

import argparse
from collections import Counter
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".venv", "runs", "site", "review", "collab"}
EXCLUDED_FILES = {".env", ".env.example"}
PATTERNS = (
    ("Anthropic credential prefix", re.compile(r"sk-ant[-_][A-Za-z0-9_-]{3,}")),
    ("GitHub credential prefix", re.compile(r"(?:github_pat_|gho_)[A-Za-z0-9_]{3,}")),
    ("Linear credential prefix", re.compile(r"lin_api_[A-Za-z0-9_-]{3,}")),
    ("Slack credential prefix", re.compile(r"xoxb-[A-Za-z0-9-]{3,}")),
    ("Slack webhook URL", re.compile(re.escape("hooks.slack.com/" + "services"))),
)
TOKEN = re.compile(r"[A-Za-z0-9_+/-]{40,}")
URL = re.compile(r"https?://[^\s\"\'<>]+")


def excluded(filename: str) -> bool:
    parts = PurePosixPath(filename).parts
    return any(part in EXCLUDED_DIRS for part in parts) or any(part in EXCLUDED_FILES for part in parts)


def high_entropy(token: str) -> bool:
    # Three character classes plus Shannon entropy avoid flagging ordinary long
    # identifiers, prose, and public hex commit hashes as secret-shaped tokens.
    if not (any(c.islower() for c in token) and any(c.isupper() for c in token)
            and any(c.isdigit() for c in token)):
        return False
    length = len(token)
    entropy = -sum((count / length) * math.log2(count / length)
                   for count in Counter(token).values())
    return entropy >= 4.5


def scan_text(filename: str, text: str) -> list[tuple[int, str]]:
    if excluded(filename):
        return []
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        reasons = [reason for reason, pattern in PATTERNS if pattern.search(line)]
        # URL separators must not join a short public path identifier to its
        # hostname and manufacture a 40-character token. Scan each URL component.
        candidates = URL.sub(lambda match: re.sub(r"[:/.?&=]", " ", match.group()), line)
        if not reasons and any(high_entropy(match.group()) for match in TOKEN.finditer(candidates)):
            reasons.append("high-entropy token (40+ characters)")
        hits.extend((number, reason) for reason in reasons)
    return hits


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.PIPE)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="scan changed index blobs, not working copies")
    args = parser.parse_args(argv)
    try:
        inventory = (git_bytes("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
                     if args.staged else git_bytes("ls-files", "-z"))
    except (OSError, subprocess.CalledProcessError):
        print("git:0: cannot read tracked file inventory")
        return 1
    found = False
    for raw_name in inventory.split(b"\0"):
        if not raw_name:
            continue
        filename = raw_name.decode("utf-8", errors="surrogateescape")
        if excluded(filename):
            continue
        try:
            if args.staged:
                content = git_bytes("show", f":{filename}")
            else:
                path = ROOT / filename
                if path.is_symlink():
                    print(f"{filename}:0: symbolic link cannot be safely scanned")
                    found = True
                    continue
                if not path.exists():  # tracked file deleted in the working tree
                    continue
                content = path.read_bytes()
        except (OSError, subprocess.CalledProcessError):
            print(f"{filename}:0: cannot read file for scanning")
            found = True
            continue
        # Decode rather than skipping binary files: printable embedded keys count.
        for number, reason in scan_text(filename, content.decode("utf-8", errors="replace")):
            print(f"{filename}:{number}: {reason}")
            found = True
    return int(found)


if __name__ == "__main__":
    sys.exit(main())
