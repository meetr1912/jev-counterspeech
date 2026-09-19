"use strict";

// Local-only inspector for a jev-counterspeech run.
// Every value that carries post/candidate text is written via textContent,
// never innerHTML. The only network request made is to this same local server.

const STATE = { report: null, selectedId: null };

const GATE_ORDER = ["draft", "human_review", "report", "ignore"];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function num(value, digits) {
  const places = digits === undefined ? 3 : digits;
  return typeof value === "number" && isFinite(value) ? value.toFixed(places) : "–";
}

function pct(value) {
  return typeof value === "number" && isFinite(value) ? Math.round(value * 100) + "%" : "–";
}

function prettyKey(key) {
  return String(key).replace(/_/g, " ");
}

function describeError(payload, status) {
  if (payload && typeof payload.error === "string") return payload.error;
  return "request failed (HTTP " + status + ")";
}

// --------------------------------------------------------------------------
// Small building blocks
// --------------------------------------------------------------------------

function bars(dist, options) {
  const opts = options || {};
  const wrap = el("div", "bars");
  const entries = Object.entries(dist || {});
  if (entries.length === 0) {
    wrap.append(el("span", "muted", "no distribution"));
    return wrap;
  }
  entries.sort((a, b) => (Number(b[1]) || 0) - (Number(a[1]) || 0));
  const max = Math.max.apply(null, entries.map((pair) => Number(pair[1]) || 0).concat([0.0001]));
  const scale = opts.relative ? max : 1;
  for (const pair of entries) {
    const key = pair[0];
    const value = pair[1];
    const row = el("div", "bar-row");
    if (opts.highlight && key === opts.highlight) row.classList.add("chosen");
    if (opts.best && key === opts.best) row.classList.add("best");
    row.append(el("span", "label", prettyKey(key)));
    const track = el("span", "bar-track");
    const fill = el("span", "bar-fill");
    const width = Math.max(0, Math.min(1, (Number(value) || 0) / scale)) * 100;
    fill.style.width = width.toFixed(2) + "%";
    track.append(fill);
    row.append(track, el("span", "pct", pct(value)));
    wrap.append(row);
  }
  return wrap;
}

function scalarBars(values) {
  const dist = {};
  for (const key of Object.keys(values)) dist[key] = values[key];
  return bars(dist);
}

function gateBadge(action) {
  const known = GATE_ORDER.indexOf(action) >= 0 ? action : "unknown";
  return el("span", "gate-badge gate-" + known, action || "unknown");
}

function section(title) {
  const node = el("section", "block");
  node.append(el("h3", null, title));
  return node;
}

function reasonsList(reasons) {
  const list = el("ul", "reasons");
  const items = Array.isArray(reasons) ? reasons : [];
  if (items.length === 0) {
    list.append(el("li", "muted", "no reasons recorded"));
    return list;
  }
  for (const reason of items) list.append(el("li", null, reason));
  return list;
}

// --------------------------------------------------------------------------
// Header, calibration, gate counts
// --------------------------------------------------------------------------

function renderMeta(meta) {
  const host = document.getElementById("meta");
  host.replaceChildren();
  if (!meta) {
    host.append(el("span", "muted", "no meta"));
    return;
  }
  const fields = [
    ["mode", meta.mode],
    ["stub", meta.stub],
    ["seed", meta.seed],
    ["limit", meta.limit],
    ["threshold", meta.threshold],
    ["draft", meta.draft_mode],
  ];
  for (const pair of fields) {
    if (pair[1] === undefined || pair[1] === null) continue;
    const chip = el("span", "chip");
    chip.append(el("label", null, pair[0]), el("b", null, pair[1]));
    host.append(chip);
  }
}

function renderGateCounts(gate) {
  const host = document.getElementById("gatecounts");
  host.replaceChildren();
  const counts = gate || {};
  const keys = GATE_ORDER.concat(["refused", "drafted_items"]);
  for (const key of keys) {
    const chip = el("span", "count-chip count-" + key);
    chip.append(el("span", "count-label", key.replace(/_/g, " ")), el("b", null, counts[key] === undefined ? "–" : counts[key]));
    host.append(chip);
  }
}

function reliabilityColumns(rows) {
  const first = rows[0];
  return Object.keys(first).filter((key) => typeof first[key] !== "object" || first[key] === null);
}

function reliabilityPlot(rows) {
  const xKey = ["confidence", "predicted", "mean_predicted", "bin_confidence", "bin"].find((key) => rows.some((row) => typeof row[key] === "number"));
  const yKey = ["accuracy", "observed", "fraction_positive", "empirical", "correct"].find((key) => rows.some((row) => typeof row[key] === "number"));
  if (!xKey || !yKey) return null;

  const W = 320;
  const H = 220;
  const PAD = 30;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.setAttribute("class", "reliability-svg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Reliability diagram: confidence versus accuracy");

  const x = (v) => PAD + Math.max(0, Math.min(1, Number(v) || 0)) * (W - 2 * PAD);
  const y = (v) => H - PAD - Math.max(0, Math.min(1, Number(v) || 0)) * (H - 2 * PAD);

  const axes = document.createElementNS(ns, "path");
  axes.setAttribute("d", "M " + x(0) + " " + y(0) + " L " + x(1) + " " + y(0) + " M " + x(0) + " " + y(0) + " L " + x(0) + " " + y(1));
  axes.setAttribute("class", "axis");
  svg.append(axes);

  const diagonal = document.createElementNS(ns, "line");
  diagonal.setAttribute("x1", x(0));
  diagonal.setAttribute("y1", y(0));
  diagonal.setAttribute("x2", x(1));
  diagonal.setAttribute("y2", y(1));
  diagonal.setAttribute("class", "diagonal");
  svg.append(diagonal);

  for (const row of rows) {
    if (typeof row[xKey] !== "number" || typeof row[yKey] !== "number") continue;
    const dot = document.createElementNS(ns, "circle");
    dot.setAttribute("cx", x(row[xKey]));
    dot.setAttribute("cy", y(row[yKey]));
    dot.setAttribute("r", "4");
    dot.setAttribute("class", "point");
    const title = document.createElementNS(ns, "title");
    title.textContent = xKey + " " + num(row[xKey]) + ", " + yKey + " " + num(row[yKey]);
    dot.append(title);
    svg.append(dot);
  }
  return svg;
}

function renderCalibration(cal) {
  const calibration = cal || {};
  setText("brier", num(calibration.brier));
  setText("ece", num(calibration.ece));

  const wrap = document.getElementById("reliability-wrap");
  wrap.replaceChildren();
  const rows = Array.isArray(calibration.reliability) ? calibration.reliability : [];
  if (rows.length === 0) {
    wrap.append(el("p", "muted", "No reliability bins present in this report."));
    return;
  }

  if (typeof rows[0] !== "object" || rows[0] === null) {
    const list = el("div", "bars");
    rows.forEach((value, index) => {
      const row = el("div", "bar-row");
      row.append(el("span", "label", "bin " + index));
      const track = el("span", "bar-track");
      const fill = el("span", "bar-fill");
      fill.style.width = (Math.max(0, Math.min(1, Number(value) || 0)) * 100).toFixed(1) + "%";
      track.append(fill);
      row.append(track, el("span", "pct", num(value)));
      list.append(row);
    });
    wrap.append(list);
    return;
  }

  const layout = el("div", "calib-layout");
  const table = el("table", "reliability-table");
  const head = el("thead");
  const headRow = el("tr");
  for (const column of reliabilityColumns(rows)) headRow.append(el("th", null, prettyKey(column)));
  head.append(headRow);
  table.append(head);
  const body = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    for (const column of reliabilityColumns(rows)) {
      const value = row[column];
      tr.append(el("td", null, typeof value === "number" ? num(value) : String(value === undefined || value === null ? "–" : value)));
    }
    body.append(tr);
  }
  table.append(body);
  layout.append(table);

  const plot = reliabilityPlot(rows);
  if (plot) layout.append(plot);
  wrap.append(layout);
}

// --------------------------------------------------------------------------
// Sidebar list
// --------------------------------------------------------------------------

function renderPostList(items) {
  const list = document.getElementById("post-list");
  list.replaceChildren();
  setText("post-count", String(items.length));
  for (const item of items) {
    const card = el("button", "post-card");
    card.type = "button";
    card.dataset.postId = item.post_id;
    if (item.post_id === STATE.selectedId) card.classList.add("active");

    const head = el("div", "post-card-head");
    head.append(el("span", "post-id", item.post_id));
    const gate = item.gate || {};
    head.append(gateBadge(gate.action));
    card.append(head);

    card.append(el("p", "post-snippet", item.text));

    const foot = el("div", "post-card-foot");
    const triage = item.triage || {};
    foot.append(el("span", "mini", "cat " + (triage.category || "–")));
    foot.append(el("span", "mini", "sev " + num(triage.severity, 1)));
    foot.append(el("span", "mini", "conf " + pct(triage.confidence)));
    card.append(foot);

    card.addEventListener("click", () => selectPost(item.post_id));
    list.append(card);
  }
}

// --------------------------------------------------------------------------
// Detail pane
// --------------------------------------------------------------------------

function renderTriage(item) {
  const triage = item.triage || {};
  const block = section("Triage");
  block.append(
    scalarBars({
      hateful: triage.hateful,
      targets_protected_group: triage.targets_protected_group,
      has_slur: triage.has_slur,
    })
  );

  const grid = el("div", "triage-grid");
  grid.append(el("span", "stat-label", "predicted category"), el("b", null, triage.category || "–"));
  grid.append(el("span", "stat-label", "severity"), el("b", null, num(triage.severity, 2)));
  grid.append(el("span", "stat-label", "confidence"), el("b", null, pct(triage.confidence)));
  block.append(grid);

  const cat = el("div", "sub-block");
  cat.append(el("h4", null, "Category distribution"));
  cat.append(bars(triage.category_probs, {}));
  block.append(cat);

  const handling = el("div", "sub-block");
  handling.append(el("h4", null, "Handling distribution"));
  handling.append(bars(triage.handling_probs, { highlight: triage.handling }));
  block.append(handling);

  const severity = el("div", "sub-block");
  severity.append(el("h4", null, "Severity distribution"));
  severity.append(bars(triage.severity_dist, {}));
  block.append(severity);

  return block;
}

function candidateCard(candidate, ranking, isBest) {
  const card = el("article", "candidate" + (isBest ? " best" : ""));
  const rank = ranking || {};
  const quality = rank.quality || {};

  const head = el("div", "candidate-head");
  const left = el("div", "candidate-tags");
  left.append(el("span", "candidate-id", candidate.id));
  left.append(el("span", "tag", candidate.strategy || "–"));
  left.append(el("span", "tag origin", candidate.origin || "–"));
  if (isBest) left.append(el("span", "tag best-tag", "Jev best"));
  head.append(left);
  head.append(el("span", "quality-badge", "quality " + num(quality[candidate.id])));
  card.append(head);

  card.append(el("blockquote", "candidate-text", candidate.text));

  const qblock = el("div", "sub-block");
  qblock.append(el("h4", null, "Quality distribution"));
  qblock.append(bars(rank.quality_dists && rank.quality_dists[candidate.id], { highlight: undefined }));
  card.append(qblock);

  const dims = rank.dimensions || {};
  const dimBlock = el("div", "sub-block");
  dimBlock.append(el("h4", null, "Per-dimension distributions"));
  const dimNames = Object.keys(dims);
  if (dimNames.length === 0) {
    dimBlock.append(el("span", "muted", "no dimensions recorded"));
  }
  for (const dim of dimNames) {
    const row = el("div", "dim-row");
    row.append(el("span", "dim-label", prettyKey(dim)));
    row.append(bars(dims[dim], { highlight: candidate.id, best: isBest ? candidate.id : undefined, relative: true }));
    dimBlock.append(row);
  }
  card.append(dimBlock);

  return card;
}

function renderEditor(item) {
  const ranking = item.ranking || {};
  const bestId = ranking.best;
  const bestCandidate = (item.candidates || []).find((c) => c.id === bestId) || (item.candidates || [])[0];

  const editor = section("Reply draft (editable)");
  editor.append(el("p", "muted", "This draft is prefilled with Jev’s highest-ranked candidate. Edit it before sending; nothing leaves this machine."));

  const textarea = el("textarea", "draft-text");
  textarea.id = "draft-text";
  textarea.rows = 6;
  textarea.spellcheck = true;
  textarea.value = bestCandidate ? bestCandidate.text : "";
  editor.append(textarea);

  const actions = el("div", "editor-actions");
  const button = el("button", "send-button", "Send to local outbox");
  button.id = "send-btn";
  button.type = "button";
  const status = el("span", "send-status muted", "");
  status.id = "send-status";
  actions.append(button, status);
  editor.append(actions);

  button.addEventListener("click", () => sendDraft(item, textarea, button, status));
  return editor;
}

async function sendDraft(item, textarea, button, status) {
  const ranking = item.ranking || {};
  button.disabled = true;
  status.className = "send-status";
  status.textContent = "Writing locally…";
  try {
    const response = await fetch("/api/outbox", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        post_id: item.post_id,
        candidate_id: ranking.best === undefined ? null : ranking.best,
        text: textarea.value,
        approved: true,
      }),
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (error) {
      payload = {};
    }
    if (response.ok && payload.ok) {
      status.className = "send-status ok";
      status.textContent =
        "Written locally to " + payload.path + " (" + payload.count + " in outbox). Nothing was posted.";
    } else {
      status.className = "send-status err";
      status.textContent = "Rejected: " + describeError(payload, response.status);
    }
  } catch (error) {
    status.className = "send-status err";
    status.textContent = "Could not reach the local server: " + error;
  } finally {
    button.disabled = false;
  }
}

function renderDetail(item) {
  const detail = document.getElementById("detail");
  detail.replaceChildren();
  if (!item) {
    detail.append(el("p", "empty", "Select a post to inspect Jev’s triage, gate decision, and drafts."));
    return;
  }

  const head = el("div", "detail-head");
  head.append(el("span", "post-id", item.post_id));
  head.append(gateBadge((item.gate || {}).action));
  const drafted = el("span", "tag", item.drafted ? "drafted" : "not drafted");
  head.append(drafted);
  detail.append(head);

  detail.append(el("blockquote", "post-text", item.text));

  const gate = item.gate || {};
  const gateBlock = section("Gate decision");
  const gateLine = el("div", "gate-line");
  gateLine.append(el("span", "muted", "action"), gateBadge(gate.action), el("span", "muted", "threshold " + num(gate.threshold, 2)));
  gateBlock.append(gateLine);
  gateBlock.append(el("h4", null, "Reasons"));
  gateBlock.append(reasonsList(gate.reasons));
  detail.append(gateBlock);

  detail.append(renderTriage(item));

  if (item.drafted && item.ranking) {
    const drafts = section("Candidate replies");
    drafts.append(el("p", "muted", "Ranked by Jev. The best-ranked candidate is highlighted and prefilled below."));
    for (const candidate of item.candidates || []) {
      drafts.append(candidateCard(candidate, item.ranking, candidate.id === item.ranking.best));
    }
    detail.append(drafts);
    detail.append(renderEditor(item));
  } else {
    const noReply = section("No reply offered");
    noReply.append(
      el(
        "p",
        "no-reply",
        "No public reply is offered for this item. The gate decided this post is " +
          (gate.action || "not draftable") +
          ", so it is ignore/report only and the UI will not send a reply."
      )
    );
    noReply.append(el("h4", null, "Why"));
    noReply.append(reasonsList(gate.reasons));
    detail.append(noReply);
  }
}

function selectPost(postId) {
  STATE.selectedId = postId;
  const item = (STATE.report && STATE.report.items ? STATE.report.items : []).find((entry) => entry.post_id === postId);
  renderPostList(STATE.report && STATE.report.items ? STATE.report.items : []);
  renderDetail(item || null);
}

// --------------------------------------------------------------------------
// Boot
// --------------------------------------------------------------------------

async function load() {
  const detail = document.getElementById("detail");
  try {
    const response = await fetch("/api/data", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || payload.error) {
      detail.replaceChildren(el("p", "empty error", "Could not load report: " + describeError(payload, response.status)));
      return;
    }
    STATE.report = payload;
    renderMeta(payload.meta);
    renderGateCounts(payload.gate);
    renderCalibration(payload.calibration);
    const items = Array.isArray(payload.items) ? payload.items : [];
    if (items.length > 0) {
      STATE.selectedId = items[0].post_id;
      renderPostList(items);
      renderDetail(items[0]);
    } else {
      renderPostList([]);
      detail.replaceChildren(el("p", "empty", "The report contains no items."));
    }
  } catch (error) {
    detail.replaceChildren(el("p", "empty error", "Could not reach the local server: " + error));
  }
}

load();
