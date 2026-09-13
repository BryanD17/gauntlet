import threading
import time
from unittest.mock import patch

from gauntlet import report


def test_leaderboard_updates_are_serialized_across_threads():
    start = threading.Barrier(3)
    state_guard = threading.Lock()
    active = 0
    max_active = 0

    def controlled_update(*args):
        nonlocal active, max_active
        with state_guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with state_guard:
            active -= 1
        return "leaderboard.html"

    def call_update(team):
        start.wait()
        report.update_leaderboard(object(), team, "now")

    with patch.object(report, "_update_leaderboard", controlled_update):
        threads = [threading.Thread(target=call_update, args=(team,)) for team in ("A", "B")]
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert max_active == 1
