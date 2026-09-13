(function (global) {
  "use strict";

  var activeStream = null;
  var HARNESS_DOCS_URL = "https://github.com/BryanD17/gauntlet#the-harness-contract";

  function normalizeTarget(value) {
    return String(value || "").trim().replace(/\/task\/?$/, "").replace(/\/$/, "");
  }

  function buildRunPayload(form) {
    var repo = form.elements.repo.value.trim();
    return {
      target: normalizeTarget(form.elements.target.value),
      repo: repo || null,
      team: form.elements.team.value.trim(),
      no_fix: form.elements.no_fix.checked,
      allow_remote: form.elements.allow_remote.checked
    };
  }

  function verdictClass(verdict) {
    var normalized = String(verdict || "").toUpperCase();
    if (normalized === "PASS") return "verdict-pass";
    if (normalized === "ABSTAINED") return "verdict-abstain";
    if (normalized === "FAIL" || normalized === "ERROR") return "verdict-fail";
    return "verdict-pending";
  }

  function gradeClass(letter) {
    if (letter === "A" || letter === "B") return "grade-positive";
    if (letter === "C") return "grade-warning";
    return "grade-negative";
  }

  function text(id, value) {
    var node = document.getElementById(id);
    if (node) node.textContent = String(value);
  }

  function attackRow(scenario) {
    var rows = document.querySelectorAll("#attack-list [data-scenario]");
    for (var i = 0; i < rows.length; i += 1) {
      if (rows[i].dataset.scenario === scenario) return rows[i];
    }
    return null;
  }

  function renderAttack(data) {
    var row = attackRow(data.scenario);
    if (!row) return;
    row.className = "attack-plate " + verdictClass(data.verdict) + " is-resolved";
    row.querySelector("strong").textContent = data.title;
    row.querySelector("small").textContent = data.detail;
    row.querySelector("b").textContent = data.verdict;
  }

  function addResultLink(container, label, href) {
    if (!href) return;
    var link = document.createElement("a");
    link.href = href;
    link.textContent = label;
    container.appendChild(link);
  }

  function renderResult(data) {
    var panel = document.getElementById("grade-panel");
    panel.hidden = false;
    panel.className = "grade-panel grade-strike " + gradeClass(data.letter);
    text("grade-letter", data.letter);
    text("grade-score", data.score + " / 100");
    text("stat-caught", data.attacks_caught);
    text("stat-landed", data.attacks_landed);
    text("stat-false-alarms", data.false_alarms);
    text("stat-slack", data.slack);

    var stats = document.getElementById("result-stats");
    stats.hidden = false;
    var links = document.getElementById("result-links");
    links.replaceChildren();
    addResultLink(links, "Open report", data.report_url);
    (data.pr_urls || []).forEach(function (url, index) {
      addResultLink(links, "Fix PR " + (index + 1), url);
    });
    (data.linear_urls || []).forEach(function (url, index) {
      addResultLink(links, "Linear issue " + (index + 1), url);
    });
    addResultLink(links, "View leaderboard", "/leaderboard");
    links.hidden = false;
    text("run-label", "Examination complete for " + data.team);
  }

  function resetRecord() {
    var rows = document.querySelectorAll("#attack-list [data-scenario]");
    rows.forEach(function (row) {
      row.className = "attack-plate verdict-pending";
      row.querySelector("small").textContent = "Waiting for evidence";
      row.querySelector("b").textContent = "Pending";
    });
    document.getElementById("grade-panel").hidden = true;
    document.getElementById("result-stats").hidden = true;
    document.getElementById("result-links").hidden = true;
  }

  function parseEvent(event) {
    if (!event.data) return null;
    try {
      return JSON.parse(event.data);
    } catch (error) {
      return null;
    }
  }

  function setRunning(running, message) {
    var button = document.getElementById("run-button");
    button.disabled = running;
    button.textContent = running ? "Examination running" : "Run examination";
    document.getElementById("examination").setAttribute("aria-busy", String(running));
    text("form-status", message);
  }

  function showError(message) {
    setRunning(false, message || "The examination could not continue. Check the target and try again.");
    text("run-label", "Examination stopped");
    var links = document.getElementById("result-links");
    links.replaceChildren();
    addResultLink(links, "Check the harness contract", HARNESS_DOCS_URL);
    links.hidden = false;
  }

  function connectEvents(runId) {
    if (activeStream) activeStream.close();
    activeStream = new EventSource("/api/run/" + encodeURIComponent(runId) + "/events");
    activeStream.addEventListener("attack", function (event) {
      var data = parseEvent(event);
      if (data) renderAttack(data);
    });
    activeStream.addEventListener("result", function (event) {
      var data = parseEvent(event);
      if (data) {
        renderResult(data);
        setRunning(false, "Grade " + data.letter + " recorded for " + data.team + ".");
      }
    });
    activeStream.addEventListener("error", function (event) {
      var data = parseEvent(event);
      showError(data && data.message ? data.message : "Connection to the examination stream was lost. Try again.");
      activeStream.close();
    });
    activeStream.addEventListener("done", function () {
      activeStream.close();
      document.getElementById("examination").setAttribute("aria-busy", "false");
    });
  }

  async function submitRun(event) {
    event.preventDefault();
    var form = event.currentTarget;
    if (!form.reportValidity()) return;
    resetRecord();
    setRunning(true, "Submitting target for examination.");
    text("run-label", "Starting examination");
    try {
      var response = await fetch("/api/run", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(buildRunPayload(form))
      });
      var body = await response.json();
      if (!response.ok || !body.run_id) {
        throw new Error(body.detail || body.message || "The server rejected this examination.");
      }
      text("run-label", "Run " + body.run_id);
      text("form-status", "Target accepted. Evidence is streaming.");
      connectEvents(body.run_id);
    } catch (error) {
      showError(error.message);
    }
  }

  function fillReference() {
    document.getElementById("target").value = "http://localhost:8002";
    document.getElementById("team").value = "Hardened Reference";
    document.getElementById("repo").value = "";
    document.getElementById("no-fix").checked = true;
    text("form-status", "Hardened Reference is ready. Start its local agent, then run the examination.");
    document.getElementById("target").focus();
  }

  global.GauntletUI = {
    buildRunPayload: buildRunPayload,
    verdictClass: verdictClass,
    gradeClass: gradeClass,
    renderAttack: renderAttack,
    renderResult: renderResult,
    showError: showError
  };

  if (typeof document !== "undefined") {
    var form = document.getElementById("run-form");
    var reference = document.getElementById("reference-button");
    if (form) form.addEventListener("submit", submitRun);
    if (reference) reference.addEventListener("click", fillReference);
  }
}(typeof window !== "undefined" ? window : globalThis));
