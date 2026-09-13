"""Offline checks for the browser console's request and SSE rendering contract."""

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_JS = ROOT / "web" / "static" / "console.js"
CONSOLE_TEMPLATE = ROOT / "web" / "templates" / "console.html.j2"


def run_node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_console_builds_exact_api_payload():
    result = run_node(r"""
require('./web/static/console.js');
const form = {elements: {
  target: {value: ' http://localhost:9002/task/ '},
  repo: {value: ' owner/repository '},
  team: {value: ' Hardened Reference '},
  no_fix: {checked: true},
  allow_remote: {checked: false}
}};
console.log(JSON.stringify(globalThis.GauntletUI.buildRunPayload(form)));
""")

    assert result == {
        "target": "http://localhost:9002",
        "repo": "owner/repository",
        "team": "Hardened Reference",
        "no_fix": True,
        "allow_remote": False,
    }


def test_mocked_sse_sequence_maps_verdicts_and_renders_final_grade():
    result = run_node(r"""
require('./web/static/console.js');

class Node {
  constructor(id) {
    this.id = id;
    this.textContent = '';
    this.hidden = true;
    this.className = '';
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.parts = {};
  }
  querySelector(name) { return this.parts[name]; }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren() { this.children = []; }
  setAttribute(name, value) { this.attributes[name] = value; }
}

const scenarios = ['injection', 'duplicate', 'midwrite', 'stale'];
const rows = scenarios.map((scenario) => {
  const row = new Node(scenario);
  row.dataset.scenario = scenario;
  row.parts.strong = new Node('title');
  row.parts.small = new Node('detail');
  row.parts.b = new Node('verdict');
  return row;
});
const ids = {};
['grade-panel', 'grade-letter', 'grade-score', 'result-stats', 'result-links',
 'stat-caught', 'stat-landed', 'stat-false-alarms', 'stat-slack', 'run-label']
  .forEach((id) => { ids[id] = new Node(id); });
global.document = {
  getElementById: (id) => ids[id],
  querySelectorAll: (selector) => rows,
  createElement: (tag) => new Node(tag)
};

const sequence = [
  {type: 'attack', data: {scenario: 'injection', title: 'Prompt injection', verdict: 'PASS', detail: '<script>evidence</script>', penalty: 35}},
  {type: 'attack', data: {scenario: 'duplicate', title: 'Duplicate delivery', verdict: 'FAIL', detail: 'two payments', penalty: 20}},
  {type: 'attack', data: {scenario: 'midwrite', title: 'Mid-write failure', verdict: 'ERROR', detail: 'timeout', penalty: 25}},
  {type: 'attack', data: {scenario: 'stale', title: 'Stale data', verdict: 'ABSTAINED', detail: 'conflict flagged', penalty: 15}},
  {type: 'result', data: {
    letter: 'A', score: 100, attacks_caught: 4, attacks_landed: 0,
    false_alarms: 0, report_url: '/report/hardened-reference',
    pr_urls: ['/pull/1', '/pull/2'], linear_urls: ['/linear/1'],
    slack: 'delivered', team: 'Hardened Reference'
  }}
];
sequence.forEach((event) => {
  if (event.type === 'attack') globalThis.GauntletUI.renderAttack(event.data);
  if (event.type === 'result') globalThis.GauntletUI.renderResult(event.data);
});

console.log(JSON.stringify({
  verdictClasses: rows.map((row) => row.className),
  hostileDetail: rows[0].parts.small.textContent,
  letter: ids['grade-letter'].textContent,
  score: ids['grade-score'].textContent,
  panelHidden: ids['grade-panel'].hidden,
  panelClass: ids['grade-panel'].className,
  stats: [ids['stat-caught'].textContent, ids['stat-landed'].textContent,
          ids['stat-false-alarms'].textContent, ids['stat-slack'].textContent],
  links: ids['result-links'].children.map((link) => [link.textContent, link.href]),
  runLabel: ids['run-label'].textContent
}));
""")

    assert result["verdictClasses"] == [
        "attack-plate verdict-pass is-resolved",
        "attack-plate verdict-fail is-resolved",
        "attack-plate verdict-fail is-resolved",
        "attack-plate verdict-abstain is-resolved",
    ]
    assert result["hostileDetail"] == "<script>evidence</script>"
    assert (result["letter"], result["score"]) == ("A", "100 / 100")
    assert result["panelHidden"] is False
    assert "grade-positive" in result["panelClass"]
    assert result["stats"] == ["4", "0", "0", "delivered"]
    assert result["links"] == [
        ["Open report", "/report/hardened-reference"],
        ["Fix PR 1", "/pull/1"],
        ["Fix PR 2", "/pull/2"],
        ["Linear issue 1", "/linear/1"],
        ["View leaderboard", "/leaderboard"],
    ]
    assert result["runLabel"] == "Examination complete for Hardened Reference"


def test_console_template_wires_post_and_all_named_sse_events():
    template = CONSOLE_TEMPLATE.read_text(encoding="utf-8")
    source = CONSOLE_JS.read_text(encoding="utf-8")

    for field in ("target", "repo", "team", "allow_remote", "no_fix"):
        assert f'name="{field}"' in template
    assert 'fetch("/api/run"' in source
    assert 'method: "POST"' in source
    for event in ("attack", "result", "error", "done"):
        assert f'addEventListener("{event}"' in source
    assert 'new EventSource("/api/run/"' in source
    assert "innerHTML" not in source
    assert "insertAdjacentHTML" not in source
