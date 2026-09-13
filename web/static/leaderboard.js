(function (global) {
  "use strict";

  function gradeClass(letter) {
    if (letter === "A" || letter === "B") return "grade-positive";
    if (letter === "C") return "grade-warning";
    return "grade-negative";
  }

  function cell(tag, value, className) {
    var node = document.createElement(tag);
    node.textContent = String(value);
    if (className) node.className = className;
    return node;
  }

  function reportUrl(row) {
    if (row.report_url) return row.report_url;
    if (row.slug) return "/report/" + encodeURIComponent(row.slug);
    if (row.report && String(row.report).charAt(0) === "/") return row.report;
    return "#";
  }

  function renderRows(rows) {
    var body = document.getElementById("leaderboard-body");
    var empty = document.getElementById("board-empty");
    body.replaceChildren();
    empty.hidden = rows.length !== 0;
    rows.forEach(function (row, index) {
      var rank = row.rank || index + 1;
      var tr = document.createElement("tr");
      if (rank === 1) tr.className = "top-rank";
      tr.appendChild(cell("td", rank, "rank-cell"));
      var team = cell("th", row.team, "team-cell");
      team.scope = "row";
      tr.appendChild(team);
      var grade = cell("td", row.letter, "board-grade " + gradeClass(row.letter));
      grade.setAttribute("aria-label", "Grade " + row.letter);
      tr.appendChild(grade);
      tr.appendChild(cell("td", row.score, "numeric-cell"));
      tr.appendChild(cell("td", row.attacks_survived + " / " + row.attacks_total, "numeric-cell"));
      var evidence = document.createElement("td");
      var link = document.createElement("a");
      link.href = reportUrl(row);
      link.textContent = "View report";
      link.setAttribute("aria-label", "View report for " + row.team);
      evidence.appendChild(link);
      tr.appendChild(evidence);
      body.appendChild(tr);
    });
  }

  async function loadBoard() {
    var status = document.getElementById("board-status");
    try {
      var response = await fetch("/api/leaderboard", {headers: {"Accept": "application/json"}});
      var payload = await response.json();
      if (!response.ok) throw new Error("Leaderboard request failed");
      var rows = Array.isArray(payload) ? payload : payload.rows;
      if (!Array.isArray(rows)) throw new Error("Leaderboard response was invalid");
      renderRows(rows);
      status.textContent = rows.length + (rows.length === 1 ? " certified agent" : " certified agents");
    } catch (error) {
      status.textContent = "Could not load records. Refresh to try again.";
    }
  }

  global.GauntletBoard = {gradeClass: gradeClass, reportUrl: reportUrl, renderRows: renderRows};
  if (typeof document !== "undefined") loadBoard();
}(typeof window !== "undefined" ? window : globalThis));
