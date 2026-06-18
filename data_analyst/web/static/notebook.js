// data_analyst notebook UI

const API = "/api";

// Logged-in username (from the header) — used to label cell authors.
const CURRENT_USER = (document.querySelector("header .user span")?.textContent || "").trim();

const STARTER_QUESTIONS = [
  {
    label: "Top 5 test creatives",
    prompt: "Show the top 5 creatives from test campaigns over the last 7 days. Include spend, purchases, CPA, impressions, link clicks, CTR, and hook rate.",
  },
  {
    label: "Unique creatives by pipeline",
    prompt: "How many unique creatives were tested in test campaigns over the last 7 days? Break the count down by pipeline.",
  },
  {
    label: "Pipeline results (7d)",
    prompt: "How many creative pipelines are currently in test campaigns, and what are their results over the last 7 days?",
  },
  {
    label: "Zero-purchase spenders",
    prompt: "Which test creatives spent money over the last 7 days but produced zero purchases? Show the highest-spend rows first.",
  },
  {
    label: "Best pipeline by CPA",
    prompt: "Which pipelines have the best CPA at statistically meaningful volume? Use the documented significance rules.",
  },
  {
    label: "Last week summary",
    prompt: "Summarize last week's test performance: spend, purchases, CPA, impressions, link clicks, CTR, hook rate, tested creatives, and active pipelines.",
  },
];

const state = {
  notebooks: [],
  currentNotebookId: null,
  currentAccess: null,       // "owner", "editor", or "shared"
  currentOwnerUsername: null,
  cellsById: new Map(),  // cell_id -> {el, body, status}
  modelProfiles: [],     // [{profile, model, provider, role, available, ...}]
  defaultProfile: null,
  routingEnabled: false,
};

// --- Markdown renderer ----------------------------------------------------

marked.setOptions({
  gfm: true,
  breaks: false,
  highlight: (code, lang) => {
    try {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value;
      }
    } catch (e) {}
    return code;
  },
});

function renderMarkdown(text) {
  const html = marked.parse(text || "");
  return html;
}

// --- Tool-result summary helpers -----------------------------------------

function iconFor(kind) {
  switch (kind) {
    case "read_wiki": return "📖";
    case "sql": return "▤";
    case "chart": return "📈";
    case "chart_error":
    case "python_exec_error":
    case "csv_error": return "⚠️";
    case "python_exec": return "▶";
    case "csv": return "⬇";
    default: return "→";
  }
}

function buildSummaryLine(toolName, kind, result, args) {
  if (toolName === "read_wiki") {
    const page = (args && (args.page || args.name || args.slug || args.path)) || "";
    return page ? `Read wiki: ${page}` : "Read wiki";
  }
  if (toolName === "sql") {
    const text = typeof result === "string" ? result : "";
    const firstLine = (text.split("\n").find(l => l.trim()) || "").replace(/[*_`]/g, "").trim();
    const preview = firstLine.length > 60 ? firstLine.slice(0, 60) + "…" : firstLine;
    return preview ? `SQL — ${preview}` : "SQL";
  }
  if (kind === "chart") {
    return `Chart — ${result.summary || ""}`.trim();
  }
  if (kind === "chart_error") {
    return `Chart error — ${result.error || result.summary || ""}`.trim();
  }
  if (kind === "python_exec") {
    return `Python — ${result.summary || ""}`.trim();
  }
  if (kind === "python_exec_error") {
    return `Python error — ${result.error || result.summary || ""}`.trim();
  }
  if (kind === "csv") {
    return `CSV export — ${result.filename || result.summary || ""}`.trim();
  }
  if (kind === "csv_error") {
    return `CSV error — ${result.error || result.summary || ""}`.trim();
  }
  return `${toolName || "tool"} result`;
}

// --- python_exec result renderer -----------------------------------------

function renderPythonExec(body, result) {
  body.classList.add("py-result");
  if (result.summary) {
    const head = document.createElement("div");
    head.className = "py-summary";
    head.textContent = result.summary;
    body.appendChild(head);
  }
  if (result.stdout && result.stdout.trim()) {
    const pre = document.createElement("pre");
    pre.className = "py-stdout";
    pre.textContent = result.stdout;
    body.appendChild(pre);
  }
  if (result.stderr && result.stderr.trim()) {
    const pre = document.createElement("pre");
    pre.className = "py-stderr";
    if (result.exit_status === "error" || result.exit_status === "timeout") {
      pre.classList.add("py-stderr-error");
    }
    pre.textContent = result.stderr;
    body.appendChild(pre);
  }
  for (const t of (result.tables || [])) {
    const tbl = document.createElement("table");
    tbl.className = "py-table";
    if (t.title) {
      const cap = document.createElement("caption");
      cap.textContent = t.title;
      tbl.appendChild(cap);
    }
    const thead = document.createElement("thead");
    const trh = document.createElement("tr");
    for (const col of (t.columns || [])) {
      const th = document.createElement("th");
      th.textContent = col;
      trh.appendChild(th);
    }
    thead.appendChild(trh);
    tbl.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const row of (t.rows || []).slice(0, 200)) {
      const tr = document.createElement("tr");
      for (const col of (t.columns || [])) {
        const td = document.createElement("td");
        let v = row[col];
        if (v === null || v === undefined) v = "";
        let s = typeof v === "string" ? v : JSON.stringify(v);
        if (s.length > 200) {
          td.title = s;
          s = s.slice(0, 199) + "…";
        }
        td.textContent = s;
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    body.appendChild(tbl);
  }
  for (const spec of (result.vega_specs || [])) {
    const chartDiv = document.createElement("div");
    chartDiv.className = "vl-chart";
    body.appendChild(chartDiv);
    requestAnimationFrame(() => {
      try {
        vegaEmbed(chartDiv, spec, { actions: false, theme: "ggplot2" })
          .catch(err => {
            chartDiv.textContent = "chart render error: " + (err && err.message || err);
            chartDiv.classList.add("tool-error");
          });
      } catch (err) {
        chartDiv.textContent = "chart render error: " + (err && err.message || err);
        chartDiv.classList.add("tool-error");
      }
    });
  }
  for (const plot of (result.plots || [])) {
    const img = document.createElement("img");
    img.className = "py-plot";
    img.loading = "lazy";
    img.alt = plot.filename || "plot";
    img.src = plot.url;
    body.appendChild(img);
  }
}

// --- CSV export result renderer ------------------------------------------

function renderCsvResult(body, result) {
  body.classList.add("csv-result");

  if (result.url) {
    const dl = document.createElement("a");
    dl.className = "csv-download-btn";
    dl.href = result.url;
    dl.download = result.filename || "export.csv";
    dl.textContent = "⬇ Download " + (result.filename || "CSV");
    body.appendChild(dl);
  }

  const meta = document.createElement("div");
  meta.className = "csv-meta";
  const parts = [];
  if (typeof result.row_count === "number") {
    parts.push(result.row_count.toLocaleString() + " rows");
  }
  if (Array.isArray(result.columns) && result.columns.length) {
    parts.push(result.columns.length + " columns: " + result.columns.join(", "));
  }
  meta.textContent = parts.join(" · ");
  body.appendChild(meta);

  if (result.truncated) {
    const trunc = document.createElement("div");
    trunc.className = "csv-trunc";
    trunc.textContent =
      "⚠ Truncated to " +
      (typeof result.row_count === "number" ? result.row_count.toLocaleString() : result.row_count) +
      " rows — query returned more. Aggregate or add a LIMIT to export full results.";
    body.appendChild(trunc);
  }
}

// --- API helpers ----------------------------------------------------------

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(API + path, opts);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${method} ${path} → ${resp.status}: ${text}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

// --- Sidebar --------------------------------------------------------------

async function loadNotebooks() {
  state.notebooks = await api("GET", "/notebooks");

  const ownList = document.getElementById("notebook-list-own");
  const sharedList = document.getElementById("notebook-list-shared");
  const sharedSection = document.getElementById("sidebar-shared-section");

  ownList.innerHTML = "";
  sharedList.innerHTML = "";

  const owned = state.notebooks.filter(nb => nb.access === "owner");
  // "Shared with me" holds every notebook shared to this user — both read-only
  // viewers (access === "shared") and editors (access === "editor"). Editors
  // were previously dropped from both lists, making editor notebooks invisible.
  const shared = state.notebooks.filter(
    nb => nb.access === "shared" || nb.access === "editor"
  );

  for (const nb of owned) {
    const li = _makeNotebookItem(nb);
    ownList.appendChild(li);
  }

  for (const nb of shared) {
    const li = _makeNotebookItem(nb);
    sharedList.appendChild(li);
  }

  sharedSection.hidden = shared.length === 0;
}

function _makeNotebookItem(nb) {
  const li = document.createElement("li");
  li.dataset.id = nb.id;
  li.classList.toggle("active", nb.id === state.currentNotebookId);
  if (nb.access === "shared" || nb.access === "editor") {
    const isEditor = nb.access === "editor";
    const roleText = isEditor ? "editor" : "read-only";
    li.title = `Shared by ${nb.owner_username} (${roleText})`;
    const label = document.createElement("span");
    label.className = "nb-shared-tag" + (isEditor ? " nb-editor-tag" : "");
    // Distinguish editor vs read-only at a glance: editors get a role suffix
    // and a distinct style; read-only viewers keep the plain owner tag.
    label.textContent = isEditor ? `${nb.owner_username} · editor` : nb.owner_username;
    const title = document.createElement("span");
    title.textContent = nb.title || "Untitled";
    li.appendChild(title);
    li.appendChild(label);
  } else {
    li.textContent = nb.title || "Untitled";
  }
  li.addEventListener("click", () => openNotebook(nb.id));
  return li;
}

document.getElementById("new-notebook-btn").addEventListener("click", async () => {
  const title = prompt("Notebook title:", "Untitled");
  if (title === null) return;
  const nb = await api("POST", "/notebooks", { title });
  await loadNotebooks();
  openNotebook(nb.id);
});

// --- Notebook view --------------------------------------------------------

function _applyAccessUI(access) {
  const isOwner = access === "owner";
  const canEdit = access === "owner" || access === "editor";
  const archiveBtn = document.getElementById("delete-notebook-btn");
  const shareBtn = document.getElementById("share-notebook-btn");
  const forkBtn = document.getElementById("fork-notebook-btn");
  const exportBtn = document.getElementById("export-notebook-btn");
  const cellForm = document.getElementById("new-cell-form");
  const ownerLabel = document.getElementById("notebook-owner-label");

  // Owner-only controls: archive + share.
  archiveBtn.hidden = !isOwner;
  shareBtn.hidden = !isOwner;
  // Fork + Export available to everyone with access.
  forkBtn.hidden = isOwner;
  exportBtn.hidden = false;
  // Cell form: owners and editors can add/run cells; read-only viewers cannot.
  cellForm.hidden = !canEdit;

  if (!isOwner && state.currentOwnerUsername) {
    const role = access === "editor" ? "editor" : "read-only";
    ownerLabel.textContent = `shared by ${state.currentOwnerUsername} · ${role}`;
    ownerLabel.hidden = false;
  } else {
    ownerLabel.hidden = true;
  }

  // Cell-level delete buttons — update any already rendered
  document.querySelectorAll(".cell-delete").forEach(btn => {
    btn.hidden = !isOwner;
  });
}

async function openNotebook(id) {
  state.currentNotebookId = id;
  state.currentAccess = null;
  state.currentOwnerUsername = null;
  state.cellsById.clear();
  document.getElementById("notebook-empty").hidden = true;
  document.getElementById("notebook").hidden = false;

  // Update sidebar selection in both lists
  document.querySelectorAll("#notebook-list-own li, #notebook-list-shared li").forEach(li => {
    li.classList.toggle("active", Number(li.dataset.id) === id);
  });

  const data = await api("GET", `/notebooks/${id}`);
  state.currentAccess = data.access;
  state.currentOwnerUsername = data.owner_username;

  document.getElementById("notebook-title").textContent = data.title;
  _applyAccessUI(data.access);

  const cells = document.getElementById("cells");
  cells.innerHTML = "";
  for (const cell of data.cells) {
    const el = createCellElement(cell);
    cells.appendChild(el);
    for (const ev of cell.events) {
      applyEvent(cell.id, ev.type, ev.payload);
    }
  }
}

// --- Share dialog (owner only) -------------------------------------------

document.getElementById("share-notebook-btn").addEventListener("click", async () => {
  if (!state.currentNotebookId || state.currentAccess !== "owner") return;

  // Show current shares first
  let shares = [];
  try {
    shares = await api("GET", `/notebooks/${state.currentNotebookId}/shares`);
  } catch (e) {
    // ignore
  }

  let msg = "Share this notebook\n\n";
  if (shares.length > 0) {
    msg += "Currently shared with:\n";
    for (const s of shares) {
      msg += `  • ${s.username} (${s.permission === "edit" ? "editor" : "view"})\n`;
    }
    msg += "\n";
  } else {
    msg += "Not shared with anyone yet.\n\n";
  }
  msg += "Enter username to share with (leave blank to only see current shares):";

  const username = prompt(msg);
  if (username === null) return;
  const u = username.trim();
  if (!u) return;

  const permInput = prompt(
    `Permission for ${u}:\n\n` +
    "  • view — read-only (can view, export, fork)\n" +
    "  • edit — editor (can also add/run new cells)\n\n" +
    "Type 'view' or 'edit':",
    "view",
  );
  if (permInput === null) return;
  const permission = permInput.trim().toLowerCase() || "view";
  if (permission !== "view" && permission !== "edit") {
    alert("Invalid permission — must be 'view' or 'edit'.");
    return;
  }

  try {
    await api("POST", `/notebooks/${state.currentNotebookId}/shares`, { username: u, permission });
    alert(`Shared with ${u} as ${permission === "edit" ? "editor" : "viewer"}.`);
  } catch (err) {
    alert("Could not share: " + err.message);
  }
});

// --- Export button (owner / editor / viewer) -----------------------------

document.getElementById("export-notebook-btn").addEventListener("click", () => {
  if (!state.currentNotebookId) return;
  const a = document.createElement("a");
  a.href = `${API}/notebooks/${state.currentNotebookId}/export?format=markdown`;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// --- Fork button (viewer) ------------------------------------------------

document.getElementById("fork-notebook-btn").addEventListener("click", async () => {
  if (!state.currentNotebookId) return;
  if (!confirm("Copy this notebook to your own notebooks?")) return;

  try {
    const result = await api("POST", `/notebooks/${state.currentNotebookId}/fork`);
    await loadNotebooks();
    openNotebook(result.id);
  } catch (err) {
    alert("Fork failed: " + err.message);
  }
});

// --- Archive button -------------------------------------------------------

document.getElementById("delete-notebook-btn").addEventListener("click", async () => {
  if (!state.currentNotebookId) return;
  if (!confirm("Archive this notebook?")) return;
  await api("DELETE", `/notebooks/${state.currentNotebookId}`);
  state.currentNotebookId = null;
  state.currentAccess = null;
  state.currentOwnerUsername = null;
  document.getElementById("notebook").hidden = true;
  document.getElementById("notebook-empty").hidden = false;
  await loadNotebooks();
});

// --- Cell rendering -------------------------------------------------------

function _modelBadgeText(cell) {
  const ap = cell.actual_model_profile || cell.model_profile;
  if (!ap) return null;
  if (cell.escalated && cell.model_profile && cell.model_profile !== ap) {
    return `${cell.model_profile} → ${ap}`;
  }
  return ap;
}

function _cellAuthorHtml(cell) {
  const author = cell.created_by_username;
  if (!author) return "";
  // Show the author when it's not the current user, or whenever the notebook
  // is shared (editor/viewer access) so provenance is always visible there.
  if (author !== CURRENT_USER || state.currentAccess !== "owner") {
    const safe = String(author).replace(/[<>&"]/g, "");
    return `<span class="cell-author" title="Created by ${safe}">@${safe}</span>`;
  }
  return "";
}

function createCellElement(cell) {
  const isOwner = state.currentAccess === "owner";
  const badgeText = _modelBadgeText(cell);
  const badgeHtml = badgeText
    ? `<span class="cell-model-badge${cell.escalated ? " escalated" : ""}" title="${badgeText}">${badgeText}</span>`
    : "";
  const div = document.createElement("div");
  div.className = "cell";
  div.dataset.cellId = cell.id;
  div.innerHTML = `
    <div class="cell-head">
      <span class="cell-pos">[${cell.position + 1}]</span>
      <span class="cell-status ${cell.status}">${cell.status}</span>
      ${badgeHtml}
      ${_cellAuthorHtml(cell)}
      <span class="spacer"></span>
      <button class="cell-delete" title="Delete this cell and all below">✕</button>
    </div>
    <div class="cell-prompt"></div>
    <div class="cell-output"></div>
  `;
  div.querySelector(".cell-prompt").textContent = cell.prompt;
  const delBtn = div.querySelector(".cell-delete");
  delBtn.hidden = !isOwner;
  delBtn.addEventListener("click", async () => {
    if (!confirm("Delete this cell and all subsequent cells?")) return;
    await api("DELETE", `/notebooks/${state.currentNotebookId}/cells/${cell.id}`);
    await openNotebook(state.currentNotebookId);
  });
  state.cellsById.set(cell.id, {
    el: div,
    body: div.querySelector(".cell-output"),
    pendingTools: new Map(),     // tool_call_id -> element
    pendingToolNames: new Map(), // tool_call_id -> tool name
    pendingToolArgs: new Map(),  // tool_call_id -> parsed args (for read_wiki summary line)
  });
  return div;
}

function setCellStatus(cellId, status) {
  const c = state.cellsById.get(cellId);
  if (!c) return;
  const badge = c.el.querySelector(".cell-status");
  badge.className = "cell-status " + status;
  badge.textContent = status;
}

function applyEvent(cellId, type, payload) {
  const c = state.cellsById.get(cellId);
  if (!c) return;

  if (type === "assistant_message") {
    if (payload.text && payload.text.trim()) {
      const div = document.createElement("div");
      div.className = "assistant-text";
      div.innerHTML = renderMarkdown(payload.text);
      c.body.appendChild(div);
    }
  } else if (type === "tool_call") {
    const div = document.createElement("div");
    div.className = "tool-call pending";
    const argStr = payload.args ? JSON.stringify(payload.args) : (payload.args_raw || "");
    div.textContent = `→ ${payload.name}(${argStr.length > 120 ? argStr.slice(0, 120) + "…" : argStr})`;
    c.body.appendChild(div);
    c.pendingTools.set(payload.id, div);
    c.pendingToolNames.set(payload.id, payload.name);
    c.pendingToolArgs.set(payload.id, payload.args || null);
  } else if (type === "tool_result") {
    const pending = c.pendingTools.get(payload.id);
    if (pending) pending.classList.remove("pending");
    const result = payload.result;
    const toolName = c.pendingToolNames.get(payload.id) || null;
    const toolArgs = c.pendingToolArgs.get(payload.id) || null;
    const isStructured = result && typeof result === "object" && result.kind;
    const kind = isStructured ? result.kind : toolName;

    // Defaults: structured rich output (chart/python_exec/csv) and errors stay open;
    // reference text (read_wiki, sql markdown tables) collapses.
    const expandedByDefault = (
      kind === "chart" || kind === "chart_error" ||
      kind === "python_exec" || kind === "python_exec_error" ||
      kind === "csv" || kind === "csv_error" ||
      (!isStructured && toolName !== "read_wiki" && toolName !== "sql")
    );

    const details = document.createElement("details");
    details.className = "tool-result-wrap";
    if (expandedByDefault) details.open = true;

    const summary = document.createElement("summary");
    summary.className = "tool-result-summary";
    summary.innerHTML =
      '<span class="tool-result-icon"></span>' +
      '<span class="tool-result-label"></span>' +
      '<span class="tool-result-hint">(click to expand)</span>';
    summary.querySelector(".tool-result-icon").textContent = iconFor(kind);
    summary.querySelector(".tool-result-label").textContent =
      buildSummaryLine(toolName, kind, result, toolArgs);
    details.appendChild(summary);

    const body = document.createElement("div");
    body.className = "tool-result";
    if (result && typeof result === "object" && result.kind === "chart") {
      const cs = document.createElement("div");
      cs.innerHTML = renderMarkdown(result.summary || "");
      body.appendChild(cs);
      const chartDiv = document.createElement("div");
      chartDiv.className = "vl-chart";
      body.appendChild(chartDiv);
      requestAnimationFrame(() => {
        try {
          vegaEmbed(chartDiv, result.vega_lite_spec, { actions: false, theme: "ggplot2" })
            .catch(err => {
              chartDiv.textContent = "chart render error: " + (err && err.message || err);
              chartDiv.classList.add("tool-error");
            });
        } catch (err) {
          chartDiv.textContent = "chart render error: " + (err && err.message || err);
          chartDiv.classList.add("tool-error");
        }
      });
      if (result.truncated) {
        const trunc = document.createElement("div");
        trunc.className = "vl-chart-trunc";
        trunc.textContent = `(truncated to ${result.row_count} rows)`;
        body.appendChild(trunc);
      }
    } else if (result && typeof result === "object" && result.kind === "chart_error") {
      body.classList.add("tool-error");
      body.textContent = result.error || result.summary || "chart error";
    } else if (result && typeof result === "object" && result.kind === "python_exec") {
      renderPythonExec(body, result);
    } else if (result && typeof result === "object" && result.kind === "python_exec_error") {
      body.classList.add("tool-error");
      const err = document.createElement("div");
      err.className = "py-error";
      err.textContent = result.error || result.summary || "python_exec error";
      body.appendChild(err);
    } else if (result && typeof result === "object" && result.kind === "csv") {
      renderCsvResult(body, result);
    } else if (result && typeof result === "object" && result.kind === "csv_error") {
      body.classList.add("tool-error");
      const err = document.createElement("div");
      err.className = "py-error";
      err.textContent = result.error || result.summary || "export_csv error";
      body.appendChild(err);
    } else {
      body.innerHTML = renderMarkdown(typeof result === "string" ? result : (result ? JSON.stringify(result) : ""));
    }
    details.appendChild(body);
    c.body.appendChild(details);
  } else if (type === "routing_info") {
    const isEsc = payload.escalated;
    const div = document.createElement("div");
    div.className = "routing-info" + (isEsc ? " escalated" : "");
    if (isEsc) {
      const from = payload.requested_profile || "primary";
      const to = payload.actual_profile || "escalation";
      const reason = payload.escalation_reason || "";
      div.textContent = `⬆ Escalated: ${from} → ${to}` + (reason ? ` (${reason})` : "");
      // Update the cell's model badge
      const badge = c.el.querySelector(".cell-model-badge");
      if (badge) {
        badge.textContent = `${from} → ${to}`;
        badge.title = `${from} → ${to}`;
        badge.classList.add("escalated");
      }
    } else {
      div.textContent = `Model: ${payload.actual_profile || payload.requested_profile || ""}`;
    }
    c.body.appendChild(div);
  } else if (type === "error") {
    const div = document.createElement("div");
    div.className = "tool-error";
    div.textContent = payload.error || String(payload);
    c.body.appendChild(div);
    setCellStatus(cellId, "error");
  } else if (type === "done") {
    setCellStatus(cellId, "done");
    // Update cell badge with final actual_profile if provided
    if (payload.actual_profile) {
      const badge = c.el.querySelector(".cell-model-badge");
      const isEsc = payload.escalated;
      const from = state.cellModelProfiles && state.cellModelProfiles.get(cellId);
      if (badge && isEsc && from && from !== payload.actual_profile) {
        badge.textContent = `${from} → ${payload.actual_profile}`;
        badge.title = `${from} → ${payload.actual_profile}`;
        badge.classList.add("escalated");
      } else if (!badge && payload.actual_profile) {
        const head = c.el.querySelector(".cell-head");
        const spacer = head.querySelector(".spacer");
        const nb = document.createElement("span");
        nb.className = "cell-model-badge" + (isEsc ? " escalated" : "");
        nb.textContent = payload.actual_profile;
        nb.title = payload.actual_profile;
        head.insertBefore(nb, spacer);
      }
    }
  }
  c.body.scrollIntoView({ behavior: "smooth", block: "end" });
}

// --- Model profile selector ----------------------------------------------

async function loadModelProfiles() {
  try {
    const data = await api("GET", "/model-profiles");
    state.modelProfiles = data.profiles || [];
    state.defaultProfile = data.default_profile || null;
    state.routingEnabled = data.routing_enabled || false;
    _populateModelSelect();
  } catch (e) {
    // Silently degrade: selector stays with fallback option
    console.warn("Could not load model profiles:", e.message);
  }
}

function _populateModelSelect() {
  const sel = document.getElementById("model-select");
  if (!sel) return;
  sel.innerHTML = "";

  const visible = state.modelProfiles.filter((p) => !p.hidden);
  const _label = (p) => p.label || p.profile;
  const defProfile = visible.find((p) => p.profile === state.defaultProfile);

  // Default option (server default)
  const defOpt = document.createElement("option");
  defOpt.value = "";
  defOpt.textContent = defProfile
    ? `default (${_label(defProfile)})`
    : "default";
  sel.appendChild(defOpt);

  for (const p of visible) {
    const opt = document.createElement("option");
    opt.value = p.profile;
    opt.textContent = _label(p);
    if (!p.available) {
      opt.disabled = true;
      if (p.disabled && p.status_reason) {
        opt.textContent += ` (${p.status_reason})`;
        opt.title = p.status_reason;
      } else if (!p.key_configured) {
        opt.textContent += " (key missing)";
      } else {
        opt.textContent += " (unavailable)";
      }
    }
    sel.appendChild(opt);
  }

  // Show routing badge if enabled
  const wrap = document.getElementById("model-select-wrap");
  if (wrap) {
    const existing = wrap.querySelector(".routing-badge");
    if (state.routingEnabled && !existing) {
      const badge = document.createElement("span");
      badge.className = "routing-badge";
      badge.title = "Routing enabled — primary may escalate on failure";
      badge.textContent = "routing on";
      wrap.appendChild(badge);
    } else if (!state.routingEnabled && existing) {
      existing.remove();
    }
  }
}

// --- Submit cell + SSE stream --------------------------------------------

document.getElementById("new-cell-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.currentNotebookId) return;
  const ta = document.getElementById("prompt-input");
  const prompt = ta.value.trim();
  if (!prompt) return;

  const selEl = document.getElementById("model-select");
  const selectedProfile = selEl && selEl.value ? selEl.value : null;
  const highStakes = document.getElementById("high-stakes-cb")?.checked || false;

  const submitBtn = document.getElementById("submit-btn");
  submitBtn.disabled = true;
  ta.disabled = true;
  document.getElementById("status-line").textContent = "running…";

  const cellBody = { prompt };
  if (selectedProfile) cellBody.model_profile = selectedProfile;
  if (highStakes) cellBody.high_stakes = true;

  try {
    const resp = await fetch(API + `/notebooks/${state.currentNotebookId}/cells`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cellBody),
    });
    if (!resp.ok) {
      const t = await resp.text();
      if (resp.status === 409) {
        alert("Another cell is already running in this notebook. Wait for it to finish, then try again.");
      } else if (resp.status === 403) {
        alert("You have read-only access to this notebook and cannot run cells.");
      } else {
        alert("error: " + t);
      }
      return;
    }
    await consumeSSE(resp.body, prompt, selectedProfile || state.defaultProfile);
    ta.value = "";
    if (document.getElementById("high-stakes-cb")) {
      document.getElementById("high-stakes-cb").checked = false;
    }
  } catch (err) {
    alert("error: " + err.message);
  } finally {
    submitBtn.disabled = false;
    ta.disabled = false;
    ta.focus();
    document.getElementById("status-line").textContent = "";
  }
});

async function consumeSSE(body, prompt, modelProfile) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let activeCellId = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const ev = parseSSEBlock(block);
      if (!ev) continue;
      if (ev.type === "cell_created") {
        const cell = {
          id: ev.payload.cell_id,
          position: ev.payload.position,
          prompt,
          status: "running",
          model_profile: ev.payload.model_profile || modelProfile || null,
          // Stamp the author on the optimistic cell so an editor (or owner)
          // sees the @author label immediately on their freshly submitted
          // cell — without waiting for a reload to fetch created_by_username
          // from the server. _cellAuthorHtml renders it whenever the notebook
          // is shared (access !== "owner"), which is always true for editors.
          created_by_username: CURRENT_USER || null,
        };
        const el = createCellElement(cell);
        document.getElementById("cells").appendChild(el);
        activeCellId = cell.id;
        // Store the requested profile for badge updates
        if (!state.cellModelProfiles) state.cellModelProfiles = new Map();
        state.cellModelProfiles.set(cell.id, cell.model_profile);
      } else if (activeCellId !== null) {
        applyEvent(activeCellId, ev.type, ev.payload);
      }
    }
  }
}

function parseSSEBlock(block) {
  let type = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).trim();
    else if (line.startsWith("data:")) data += (data ? "\n" : "") + line.slice(5).trimStart();
  }
  if (!data) return null;
  try {
    return { type, payload: JSON.parse(data) };
  } catch (e) {
    return { type, payload: { raw: data } };
  }
}

// --- Starter questions ---------------------------------------------------

function renderStarterQuestions() {
  const container = document.getElementById("starter-questions");
  container.innerHTML = "";
  for (const q of STARTER_QUESTIONS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "starter-question-btn";
    btn.textContent = q.label;
    btn.addEventListener("click", () => {
      const ta = document.getElementById("prompt-input");
      ta.value = q.prompt;
      ta.focus();
    });
    container.appendChild(btn);
  }
}

// --- Boot -----------------------------------------------------------------

renderStarterQuestions();
loadNotebooks();
loadModelProfiles();
