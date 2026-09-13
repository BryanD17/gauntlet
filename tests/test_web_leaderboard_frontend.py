"""Offline DOM checks for the live leaderboard renderer."""

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_b_grade_renders_as_warning_with_working_report_link():
    script = r"""
require('./web/static/leaderboard.js');

class Node {
  constructor(tag) {
    this.tag = tag;
    this.textContent = '';
    this.hidden = false;
    this.className = '';
    this.children = [];
    this.attributes = {};
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren() { this.children = []; }
  setAttribute(name, value) { this.attributes[name] = value; }
}

const body = new Node('tbody');
const empty = new Node('p');
global.document = {
  getElementById: (id) => id === 'leaderboard-body' ? body : empty,
  createElement: (tag) => new Node(tag)
};

globalThis.GauntletBoard.renderRows([{
  rank: 1,
  team: 'Careful Agent',
  letter: 'B',
  score: 80,
  attacks_survived: 3,
  attacks_total: 4,
  slug: 'careful-agent'
}]);

const row = body.children[0];
console.log(JSON.stringify({
  emptyHidden: empty.hidden,
  rowClass: row.className,
  gradeClass: row.children[2].className,
  gradeLabel: row.children[2].attributes['aria-label'],
  reportHref: row.children[5].children[0].href
}));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "emptyHidden": True,
        "rowClass": "top-rank",
        "gradeClass": "board-grade grade-warning",
        "gradeLabel": "Grade B",
        "reportHref": "/report/careful-agent",
    }
