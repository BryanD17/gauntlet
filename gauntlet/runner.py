"""Runs a target agent through all four attack scenarios and writes evidence."""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .attacks import ALL_ATTACKS
from .harness import parse_actions

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


class Target:
    """A running target agent, addressed only through the harness contract."""

    def __init__(self, base_url: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def deliver(self, task: dict):
        resp = self._client.post(f"{self.base_url}/task", json=task)
        resp.raise_for_status()
        return parse_actions(resp.json())

    def close(self):
        self._client.close()


def run_suite(target_url: str) -> tuple[list, Path]:
    """Run every attack against target_url, write evidence, return (results, run_dir)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    target = Target(target_url)
    results = []
    try:
        for attack in ALL_ATTACKS:
            result = attack(target, run_id=ts)
            results.append(result)
            print(f"  [{result.verdict:>9}] {result.title}: {result.detail}")
    finally:
        target.close()

    evidence = {
        "target": target_url,
        "timestamp_utc": ts,
        "results": [r.to_json() for r in results],
    }
    (run_dir / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return results, run_dir
