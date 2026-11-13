(() => {
"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  page: "overview",
  requestPage: 1,
  registerPage: 1,
  historyPage: 1,
  activityPage: 1,
  lpPage: 1,
  contractPage: 1,
  perPage: 25,
  requestQuery: "",
  searchTimer: null,
  filters: null,
  requests: [],
  executors: [],
  detail: null,
  editing: null,
  importBatch: null,
  importCanRun: false,
  importWarnings: false,
  workflowStageFilter: null,
  workflowRoleFilter: null,
  attentionOnly: false
};

const dateFields = [
  "dispatch_date", "contract_start_date", "contract_end_date",
  "boq_confirmation_date", "negotiation_date", "final_negotiation_date",
  "mi_head_approval_date", "mi_sm_approval_date", "mi_gm_approval_date",
  "legal_submission_date", "lp_circulation_start_date",
  "lp_contract_team_completion_date", "lp_junior_manager_approval_date",
  "lp_senior_manager_approval_date", "lp_gm_scm_approval_date", "lp_completion_date",
  "khs_inject_start_date", "khs_inject_completion_date", "last_updated_date"
];

const itemFields = [
  ["request_id", "Parent request", "request"],
  ["vendor_name", "Vendor name", "text"],
  ["executor_code", "Executor", "executor"],
  ["subtype", "Contract type", "subtype"],
  ["dispatch_date", "Dispatch date", "date"],
  ["contract_start_date", "Contract start date", "date"],
  ["contract_end_date", "Contract end date", "date"],
  ["boq_confirmation_date", "BOQ confirmation date", "date"],
  ["negotiation_date", "Negotiation date", "date"],
  ["final_negotiation_date", "Final negotiation date", "date"],
  ["mi_head_approval_date", "MI Head approval", "date"],
  ["mi_sm_approval_date", "MI SM approval", "date"],
  ["mi_gm_approval_date", "MI GM approval", "date"],
  ["legal_submission_date", "Legal submission date", "date"],
  ["lp_circulation_start_date", "LP circulation start / User submitted", "date"],
  ["lp_contract_team_completion_date", "LP Contract Team completion", "date"],
  ["lp_junior_manager_approval_date", "LP Junior Manager approval", "date"],
  ["lp_senior_manager_approval_date", "LP Senior Manager approval", "date"],
  ["lp_gm_scm_approval_date", "LP GM SCM approval", "date"],
  ["lp_completion_date", "LP Director sign-off / LP completion", "date"],
  ["khs_inject_start_date", "KHS injection start", "date"],
  ["khs_inject_completion_date", "KHS fully injected date", "date"],
  ["waiting_for", "Currently waiting for", "text"],
  ["waiting_reason", "Waiting reason / next action", "textarea"],
  ["remarks", "Remarks", "textarea"]
];

const requestFields = [
  ["request_date", "Request date", "date"],
  ["request_subject", "Request subject", "text"],
  ["requester_owner", "Requester / owner", "text"]
];

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmt(value) {
  if (!value) return "—";
  const s = String(value);
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
    const p = s.slice(0, 10).split("-");
    return p[2] + "/" + p[1] + "/" + p[0];
  }
  return s;
}

function pct(value) {
  return Math.max(0, Math.min(100, Number(value) || 0));
}

function set(id, value) {
  const el = $(id);
  if (el) el.textContent = value == null ? "—" : String(value);
}

function emptyRow(id, colspan, message) {
  const el = $(id);
  if (el) el.innerHTML = '<tr><td colspan="' + colspan + '" class="table-message">' + esc(message) + "</td></tr>";
}

function toast(message, ok) {
  const el = $("toast");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("toast-success", !!ok);
  el.classList.add("visible");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.classList.remove("visible"), 3200);
}

async function api(url, options) {
  const response = await fetch(url, options || {});
  let body = {};
  try { body = await response.json(); } catch (_) {}
  if (!response.ok || body.success === false) {
    throw new Error(body.message || ("Request failed (" + response.status + ")"));
  }
  return body;
}

function jsonOptions(method, payload) {
  return {
    method: method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  };
}

function showSystem(online, message) {
  const root = $("systemStatus");
  if (root) root.classList.toggle("status-offline", !online);
  set("systemStatusText", message || (online ? "Connected" : "Unavailable"));
}

function go(page) {
  const allowed = ["overview", "requests", "register", "lp", "contracts", "workflow", "imports", "activity"];
  if (allowed.indexOf(page) < 0) return;
  state.page = page;
  document.querySelectorAll(".page-view").forEach((el) => {
    el.classList.toggle("active", el.id === "page-" + page);
  });
  document.querySelectorAll(".nav-link[data-page]").forEach((el) => {
    el.classList.toggle("active", el.dataset.page === page);
    if (el.dataset.page === page) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  const active = $("page-" + page);
  set("breadcrumbCurrent", active ? active.dataset.title : page);
  if (window.location.hash !== "#" + page) history.replaceState(null, "", "#" + page);
  loadPage(page).catch((err) => toast(err.message));
}

async function loadPage(page) {
  if (page === "overview") return loadOverview();
  if (page === "requests") return loadRequests();
  if (page === "register") {
    await ensureFilters();
    return loadRegister();
  }
  if (page === "lp") return loadLPCirculation();
  if (page === "contracts") return loadContractLifecycle();
  if (page === "workflow") return loadWorkflow();
  if (page === "imports") return Promise.all([loadImportHistory(), Promise.resolve()]);
  if (page === "activity") return loadActivity();
}

function setWidth(id, value) {
  const el = $(id);
  if (el) el.style.width = pct(value) + "%";
}

async function loadOverview() {
  showSystem(true, "Refreshing");
  try {
    const results = await Promise.all([
      api("/api/dashboard/summary"),
      api("/api/dashboard/khs?attention=true&per_page=8"),
      api("/api/dashboard/workflow/overview").catch(() => null),
      api("/api/dashboard/contracts/lifecycle?per_page=1").catch(() => null)
    ]);
    const d = results[0].data;
    const p = d.lp;
    set("totalRequests", d.total_requests);
    set("totalKhs", d.total_khs);
    set("sidebarTotal", d.total_khs);
    const inject = d.khs_inject || { completed: 0, in_progress: 0, pending: 0, completion_rate_percent: 0 };
    set("injectCompleted", inject.completed);
    set("completionRate", inject.completion_rate_percent + "%");
    set("progressPrimary", p.completed + " / " + d.total_khs);
    set("progressRate", p.completion_rate_percent + "%");
    set("lpTotalTag", d.total_khs + " KHS");
    set("legendCompleted", p.completed);
    set("legendInProgress", p.in_progress);
    set("legendNotStarted", p.not_started);
    set("miGmCount", d.workflow.mi_gm_approved + " / " + d.total_khs);
    set("legalCount", d.workflow.legal_submitted + " / " + d.total_khs);
    set("lpStartedCount", p.in_progress + p.completed + " / " + d.total_khs);
    setWidth("barCompleted", d.total_khs ? p.completed / d.total_khs * 100 : 0);
    setWidth("barInProgress", d.total_khs ? p.in_progress / d.total_khs * 100 : 0);
    setWidth("barNotStarted", d.total_khs ? p.not_started / d.total_khs * 100 : 0);
    setWidth("miGmBar", d.total_khs ? d.workflow.mi_gm_approved / d.total_khs * 100 : 0);
    setWidth("legalBar", d.total_khs ? d.workflow.legal_submitted / d.total_khs * 100 : 0);
    setWidth("lpStartedBar", d.total_khs ? (p.in_progress + p.completed) / d.total_khs * 100 : 0);
    set("attentionCount", results[1].pagination.total_records);
    renderApprovalPipeline(results[2] && results[2].data ? results[2].data : null);
    const contractSummary = results[3] && results[3].summary ? results[3].summary : null;
    set("overviewExpiring6m", contractSummary ? contractSummary.expiring_within_6_months : "—");
    set("overviewExpiring3m", contractSummary ? contractSummary.expiring_within_3_months : "—");
    set("overviewExpiring1m", contractSummary ? contractSummary.expiring_within_1_month : "—");
    set("overviewExpiredContracts", contractSummary ? contractSummary.expired : "—");
    set("overviewMissingContractDates", contractSummary ? contractSummary.missing_contract_dates : "—");
    set("lastUpdated", new Date().toLocaleString());
    const exceptions = d.data_quality.lp_started_without_mi_gm_approval;
    const alert = $("qualityAlert");
    if (alert) alert.hidden = !exceptions;
    set("qualityCount", exceptions);
    renderAttention(results[1].data || []);
    showSystem(true, "Connected");
  } catch (err) {
    showSystem(false, "Connection issue");
    throw err;
  }
}

function renderApprovalPipeline(data) {
  if (!data) {
    [
      "miQueueTotal", "miJuniorCount", "miSeniorCount", "miGeneralCount",
      "lpQueueTotal", "lpJuniorCount", "lpSeniorCount", "lpGeneralCount",
      "lpDirectorCount", "lpOtherCount"
    ].forEach((id) => set(id, "—"));
    set("lpQueueNote", "Approval queue data is temporarily unavailable.");
    return;
  }

  const mi = data.memo_internal || [];
  const lp = data.lp || [];
  const countFor = (items, key) => {
    const item = items.find((entry) => entry.key === key);
    return item ? Number(item.count) || 0 : 0;
  };

  const miJunior = countFor(mi, "junior_manager");
  const miSenior = countFor(mi, "senior_manager");
  const miGeneral = countFor(mi, "general_manager");
  set("miJuniorCount", miJunior);
  set("miSeniorCount", miSenior);
  set("miGeneralCount", miGeneral);
  set("miQueueTotal", miJunior + miSenior + miGeneral);

  set("lpJuniorCount", countFor(lp, "junior_manager"));
  set("lpSeniorCount", countFor(lp, "senior_manager"));
  set("lpGeneralCount", countFor(lp, "general_manager"));
  set("lpDirectorCount", countFor(lp, "director"));
  set("lpQueueTotal", data.lp_active_total);
  set("lpOtherCount", data.lp_unassigned_or_other);
  set(
    "lpQueueNote",
    "Active LP records not mapped to the four roles are retained in this bucket."
  );
}

function renderAttention(rows) {
  const body = $("attentionBody");
  if (!body) return;
  if (!rows.length) {
    emptyRow("attentionBody", 6, "No records currently require attention.");
    return;
  }
  body.innerHTML = rows.map((r) =>
    "<tr><td><span class=\"cell-primary\">" + esc(r.request_subject || "Untitled request") +
    "</span><span class=\"cell-secondary\">" + esc(r.khs_id) + " · " + esc(r.request_id) + "</span></td>" +
    "<td>" + esc(r.vendor_name) + "</td><td>" + esc(r.current_stage_name || r.current_stage_code) +
    (r.lp_started_without_mi_gm_approval ? '<span class="exception-label">MI GM prerequisite exception</span>' : "") +
    "</td><td><span class=\"cell-primary\">" +
    esc(r.waiting_for || (r.lp_started_without_mi_gm_approval ? "Review prerequisite" : "Review next action")) +
    "</span>" +
    (r.waiting_reason ? '<span class="cell-secondary">' + esc(r.waiting_reason) + "</span>" : "") +
    "</td><td>" + esc(fmt(r.last_updated_date || r.updated_at)) +
    "</td><td><button class=\"view-button\" data-view-khs=\"" + esc(r.khs_id) + "\">Open</button></td></tr>"
  ).join("");
}

async function loadFilters() {
  const result = await api("/api/dashboard/filters");
  state.filters = result.data;
  state.executors = result.data.executors || [];
  fillSelect("executorFilter", state.executors, "executor_code", "display_name", "All executors");
  fillSelect("subtypeFilter", (result.data.subtypes || []).map((x) => ({ value: x, label: x })), "value", "label", "All subtypes");
  fillSelect("waitingFilter", (result.data.waiting_for || []).map((x) => ({ value: x, label: x })), "value", "label", "All waiting parties");
  fillSelect("stageFilter", result.data.stages || [], "stage_code", "stage_name", "All workflow stages");
}

function fillSelect(id, rows, valueKey, labelKey, first) {
  const el = $(id);
  if (!el) return;
  const old = el.value;
  el.innerHTML = '<option value="">' + esc(first) + "</option>" + rows.map((r) =>
    '<option value="' + esc(r[valueKey]) + '">' + esc(r[labelKey]) + "</option>"
  ).join("");
  if (Array.from(el.options).some((o) => o.value === old)) el.value = old;
}

async function ensureFilters() {
  if (!state.filters) await loadFilters();
}

function renderVendorPortfolio(record) {
  const vendors = Array.isArray(record.vendors)
    ? record.vendors.filter((name) => typeof name === "string" && name.trim())
    : [];
  if (!vendors.length) {
    return '<span class="vendor-empty">No vendors yet</span>';
  }

  const count = vendors.length;
  const label = count + (count === 1 ? " vendor" : " vendors");
  const names = vendors.map((name) =>
    '<span class="vendor-name-chip">' + esc(name) + '</span>'
  ).join("");

  return '<div class="vendor-summary">' +
    '<span class="vendor-count-badge">' + label + '</span>' +
    '<details class="vendor-details">' +
    '<summary aria-label="View ' + count + ' vendors">View list</summary>' +
    '<div class="vendor-detail-list" aria-label="Vendor list for ' + esc(record.request_id) + '">' +
    names +
    '</div></details></div>';
}

async function loadRequests() {
  const q = state.requestQuery ? "&q=" + encodeURIComponent(state.requestQuery) : "";
  const result = await api("/api/dashboard/requests?page=" + state.requestPage + "&per_page=25" + q);
  state.requests = result.data || [];
  const body = $("requestBody");
  if (!body) return;
  if (!state.requests.length) emptyRow("requestBody", 7, "No request records found.");
  else body.innerHTML = state.requests.map((r) =>
    "<tr><td><span class=\"cell-primary\">" + esc(r.request_subject) + "</span>" +
    "<span class=\"cell-secondary\">" + esc(r.request_id) + "</span></td>" +
    "<td>" + renderVendorPortfolio(r) + "</td>" +
    "<td>" + esc(fmt(r.request_date)) + "</td><td>" + esc(r.requester_owner || "—") +
    "</td><td>" + esc(r.total_khs) + "</td><td>" + esc(r.completed_khs) +
    "</td><td><button class=\"view-button\" data-edit-request=\"" + esc(r.request_id) + "\">Edit</button> " +
    "<button class=\"view-button\" data-add-child=\"" + esc(r.request_id) + "\">+ KHS</button></td></tr>"
  ).join("");
  const pg = result.pagination || {};
  set("requestPagination", "Page " + (pg.page || 1) + " · " + (pg.total_records || 0) + " requests");
  $("requestPrevious").disabled = state.requestPage <= 1;
  $("requestNext").disabled = state.requestPage >= (pg.total_pages || 0);
}

function clearRegisterFilters() {
  ["searchInput", "statusFilter", "executorFilter", "subtypeFilter", "waitingFilter", "stageFilter"]
    .forEach((id) => {
      const control = $(id);
      if (control) control.value = "";
    });
}

function registerQuery() {
  const p = new URLSearchParams();
  p.set("page", String(state.registerPage));
  p.set("per_page", String(state.perPage));
  [["q","searchInput"],["lp_status","statusFilter"],["executor_code","executorFilter"],
   ["subtype","subtypeFilter"],["waiting_for","waitingFilter"]].forEach((pair) => {
    const el = $(pair[1]);
    if (el && el.value) p.set(pair[0], el.value);
  });
  if (state.workflowStageFilter) p.set("stage", state.workflowStageFilter);
  else if ($("stageFilter") && $("stageFilter").value) p.set("stage", $("stageFilter").value);
  if (state.workflowRoleFilter) p.set("waiting_role", state.workflowRoleFilter);
  if (state.attentionOnly) p.set("attention", "true");
  return p.toString();
}

async function loadRegister() {
  const result = await api("/api/dashboard/khs?" + registerQuery());
  const body = $("registerBody");
  if (!body) return;
  if (!result.data.length) emptyRow("registerBody", 9, "No KHS records match the current filters.");
  else body.innerHTML = result.data.map((r) =>
    "<tr><td><span class=\"cell-primary\">" + esc(r.request_subject || "Untitled request") + "</span>" +
    "<span class=\"cell-secondary\">" + esc(r.vendor_name) + " · " + esc(r.khs_id) + "</span></td>" +
    "<td>" + esc(r.executor_name || r.executor_code || "Unassigned") + "</td>" +
    "<td>" + esc(r.current_stage_name || r.current_stage_code) +
    (r.lp_started_without_mi_gm_approval ? '<span class="exception-label">Prerequisite exception</span>' : "") +
    "</td><td><span class=\"status-badge status-" + esc(r.workflow_status || "not_started") + "\">" +
    esc((r.workflow_status || "not_started").replace("_", " ")) + "</span></td>" +
    "<td><span class=\"status-badge status-" + esc(r.lp_status) + "\">" +
    esc(r.lp_status.replace("_", " ")) + "</span></td>" +
    "<td>" + esc(fmt(r.khs_inject_start_date)) + "</td><td>" + esc(fmt(r.khs_inject_completion_date)) + "</td>" +
    "<td>" + esc(r.waiting_for || "—") + "</td>" +
    "<td><button class=\"view-button\" data-view-khs=\"" + esc(r.khs_id) + "\">Details</button></td></tr>"
  ).join("");
  set("sidebarTotal", result.pagination.total_records);
  set("recordCount", result.pagination.total_records + " records");
  set("paginationText", "Page " + (result.pagination.page || 1) + " of " + (result.pagination.total_pages || 0));
  $("previousPage").disabled = !result.pagination.has_previous;
  $("nextPage").disabled = !result.pagination.has_next;
}

async function loadWorkflow() {
  const result = await api("/api/dashboard/workflow");
  const wrap = $("workflowCards");
  if (!wrap) return;
  wrap.innerHTML = (result.data || []).map((r) =>
    '<article class="workflow-stage"><h3>' + esc(r.stage_name) + '</h3><strong>' + esc(r.total) +
    '</strong><p>Records currently at this checkpoint</p></article>'
  ).join("");
  if (!result.data || !result.data.length) wrap.textContent = "No workflow stage data.";
}

async function loadActivity() {
  const result = await api("/api/dashboard/activity?page=" + state.activityPage + "&per_page=25");
  const body = $("activityBody");
  if (!body) return;
  if (!result.data.length) emptyRow("activityBody", 6, "No activity has been recorded.");
  else body.innerHTML = result.data.map((r) => {
    const changes = typeof r.changes === "string" ? r.changes : JSON.stringify(r.changes || {});
    return "<tr><td>" + esc(fmt(r.occurred_at)) + "</td><td>" + esc(r.entity_type) + "</td><td>" +
      esc(r.entity_id) + "</td><td>" + esc(r.action) + "</td><td>" + esc(r.actor) +
      '<td title="' + esc(changes) + '">' + esc(changes.length > 90 ? changes.slice(0, 90) + "…" : changes) + "</td></tr>";
  }).join("");
  const p = result.pagination || {};
  set("activityPagination", "Page " + p.page + " · " + p.total_records + " activities");
  $("activityPrevious").disabled = state.activityPage <= 1;
  $("activityNext").disabled = state.activityPage >= p.total_pages;
}

async function loadImportHistory() {
  const result = await api("/api/imports/history?page=" + state.historyPage + "&per_page=10");
  const body = $("importHistoryBody");
  if (!body) return;
  if (!result.data.length) emptyRow("importHistoryBody", 8, "No import batches yet.");
  else body.innerHTML = result.data.map((r) => {
    const inserted = Number(r.inserted_requests || 0) + Number(r.inserted_items || 0);
    const updated = Number(r.updated_requests || 0) + Number(r.updated_items || 0);
    const unchanged = Number(r.unchanged_requests || 0) + Number(r.unchanged_items || 0);
    return "<tr><td>" + esc(r.id) + "</td><td>" + esc(r.original_file_name) + "</td><td>" +
      esc(r.status) + "</td><td>" + esc(r.total_rows) + "</td><td>" + inserted +
      "</td><td>" + updated + "</td><td>" + unchanged + "</td><td>" + esc(fmt(r.uploaded_at)) + "</td></tr>";
  }).join("");
  const p = result.pagination || {};
  set("historyPagination", "Page " + p.page + " · " + p.total_records + " batches");
  $("historyPrevious").disabled = state.historyPage <= 1;
  $("historyNext").disabled = state.historyPage >= p.total_pages;
}

function fillDialogField(def, record, mode) {
  const name = def[0], label = def[1], type = def[2];
  const value = record && record[name] != null ? String(record[name]).slice(0, 10) : "";
  let control = "";
  if (type === "date") {
    control = '<input type="date" name="' + name + '" value="' + esc(value) + '">';
  } else if (type === "textarea") {
    control = '<textarea name="' + name + '" rows="3">' + esc(record && record[name] || "") + "</textarea>";
  } else if (type === "request") {
    const opts = state.requests.map((r) => '<option value="' + esc(r.request_id) + '">' +
      esc(r.request_subject + (r.vendor_summary ? " · " + r.vendor_summary : "")) + "</option>").join("");
    control = '<select name="request_id" required><option value="">Select request</option>' + opts + "</select>";
  } else if (type === "executor") {
    const opts = state.executors.map((r) => '<option value="' + esc(r.executor_code) + '">' +
      esc(r.executor_code + " · " + r.display_name) + "</option>").join("");
    const legacy = record && record.executor_code && !state.executors.some((r) => r.executor_code === record.executor_code)
      ? '<option value="' + esc(record.executor_code) + '">' + esc(record.executor_code + " · current / inactive") + "</option>" : "";
    control = '<select name="executor_code" required><option value="">Select executor</option>' + legacy + opts + "</select>";
  } else if (type === "subtype") {
    const current = record && record.subtype && !["Renewal", "Kontrak Baru"].includes(record.subtype)
      ? '<option value="' + esc(record.subtype) + '">' + esc(record.subtype) + "</option>" : "";
    control = '<select name="subtype"><option value="">Select type</option>' + current + '<option>Renewal</option><option>Kontrak Baru</option></select>';
  } else {
    const required = ["request_subject", "vendor_name"].includes(name) ? " required" : "";
    control = '<input type="text" name="' + name + '" value="' + esc(record && record[name] || "") + '"' + required + '>';
  }
  const full = type === "textarea";
  return '<div class="form-field' + (full ? " full" : "") + '"><label>' + esc(label) + '</label>' + control + "</div>";
}

async function openForm(kind, record, parentRequestId) {
  if (kind === "khs") {
    await ensureFilters();
    const rq = await api("/api/dashboard/requests?per_page=100");
    state.requests = rq.data || [];
  }
  const editing = !!record;
  const defs = kind === "request" ? requestFields : itemFields.filter((f) =>
    !(editing && (f[0] === "request_id"))
  );
  state.editing = { kind: kind, record: record || null, original: record || {} };
  $("dialogEyebrow").textContent = editing ? "EDIT RECORD" : "NEW RECORD";
  $("dialogTitle").textContent = (editing ? "Edit " : "Create ") + (kind === "request" ? "Request" : "KHS item");
  $("dialogHint").textContent = kind === "khs"
    ? "LP circulation requires MI GM approval. KHS Injection starts only after LP completion; the KHS is Completed only when fully injected."
    : "Request ID is generated automatically when the record is saved.";
  $("dialogFields").innerHTML = defs.map((def) => fillDialogField(def, record, kind)).join("");
  if (kind === "khs" && !editing && parentRequestId) {
    const select = $("dialogFields").querySelector('[name="request_id"]');
    if (select) select.value = parentRequestId;
  }
  if (record) Object.keys(record).forEach((key) => {
    const el = $("dialogFields").querySelector('[name="' + key + '"]');
    if (el && el.tagName === "SELECT") el.value = record[key] || "";
  });
  $("recordDialog").showModal();
}

async function saveRecord(event) {
  event.preventDefault();
  const edit = state.editing;
  if (!edit) return;
  const form = $("recordForm");
  const data = {};
  new FormData(form).forEach((value, key) => { data[key] = value === "" ? null : value; });
  const fields = edit.kind === "request" ? requestFields : itemFields;
  if (edit.record) {
    const changed = {};
    fields.forEach((f) => {
      const key = f[0];
      if (key in data && String(data[key] == null ? "" : data[key]) !== String(edit.original[key] == null ? "" : edit.original[key])) {
        changed[key] = data[key];
      }
    });
    Object.keys(changed).forEach((key) => { data[key] = changed[key]; });
    Object.keys(data).forEach((key) => { if (!(key in changed)) delete data[key]; });
    if (!Object.keys(data).length) {
      toast("No changes to save.", true);
      $("recordDialog").close();
      return;
    }
  }
  const base = "/api/dashboard/" + (edit.kind === "request" ? "requests" : "khs");
  const url = edit.record ? base + "/" + encodeURIComponent(edit.record[edit.kind === "request" ? "request_id" : "khs_id"]) : base;
  const method = edit.record ? "PATCH" : "POST";
  try {
    await api(url, jsonOptions(method, data));
    $("recordDialog").close();
    toast(edit.record ? "Record updated." : "Record created.", true);
    if (edit.kind === "request") {
      state.requestPage = 1;
      await loadRequests();
      await loadOverview();
    } else {
      state.registerPage = 1;
      await Promise.all([loadRegisterIfReady(), loadOverview()]);
      if (state.page === "requests") await loadRequests();
    }
    state.editing = null;
  } catch (err) {
    toast(err.message);
  }
}

async function loadRegisterIfReady() {
  if (state.page === "register" && state.filters) await loadRegister();
}

async function openDetails(id) {
  try {
    const result = await api("/api/dashboard/khs/" + encodeURIComponent(id));
    state.detail = result.data;
    const r = result.data;
    set("detailTitle", r.vendor_name || r.khs_id);
    set("detailSubtitle", (r.request_subject || "No request subject") + " · " + r.khs_id);
    $("detailStatus").innerHTML =
      '<span class="status-badge status-' + esc(r.workflow_status || "not_started") + '">' +
      "Workflow: " + esc((r.workflow_status || "not_started").replace("_", " ")) + "</span>" +
      '<span class="status-badge status-' + esc(r.lp_status) + '">' +
      "LP: " + esc(r.lp_status.replace("_", " ")) + "</span>" +
      (r.lp_started_without_mi_gm_approval ? '<span class="exception-label">LP start without MI GM approval</span>' : "");
    const fields = [
      ["Request subject", r.request_subject], ["Request ID", r.request_id], ["Vendor", r.vendor_name],
      ["Executor", r.executor_name || r.executor_code], ["Type", r.subtype],
      ["Workflow stage", r.current_stage_name || r.current_stage_code],
      ["Workflow status", r.workflow_status], ["LP status", r.lp_status],
      ["Dispatch", r.dispatch_date], ["Contract start", r.contract_start_date], ["Contract end", r.contract_end_date],
      ["BOQ confirmation", r.boq_confirmation_date], ["Negotiation", r.negotiation_date],
      ["Final negotiation", r.final_negotiation_date], ["MI Head approval", r.mi_head_approval_date],
      ["MI SM approval", r.mi_sm_approval_date], ["MI GM approval", r.mi_gm_approval_date],
      ["Legal submission", r.legal_submission_date], ["LP circulation start", r.lp_circulation_start_date],
      ["LP completion", r.lp_completion_date], ["KHS injection start", r.khs_inject_start_date],
      ["KHS fully injected", r.khs_inject_completion_date],
      ["Waiting for", r.waiting_for], ["Waiting reason", r.waiting_reason],
      ["Remarks", r.remarks], ["Last updated", r.last_updated_date || r.updated_at]
    ];
    const history = result.history || [];
    $("detailGrid").innerHTML = fields.map((f) =>
      '<div class="detail-item"><span class="detail-label">' + esc(f[0]) +
      '</span><span class="detail-value">' + esc(fmt(f[1])) + "</span></div>"
    ).join("") + (history.length ? '<div class="detail-item full"><span class="detail-label">Recent activity</span><span class="detail-value">' +
      history.slice(0, 5).map((h) => esc(fmt(h.occurred_at) + " · " + h.action + " · " + h.actor)).join("<br>") + "</span></div>" : "");

    const documents = result.documents || [];
    const documentList = $("documentList");
    if (documentList) {
      documentList.innerHTML = documents.length ? documents.map((doc) =>
        '<div class="document-row"><div class="document-meta"><strong>' + esc(doc.original_file_name) +
        '</strong><small>' + esc(doc.document_type) + " · " + esc(fmt(doc.uploaded_at)) +
        '</small></div><a class="view-button" href="' + esc(doc.download_url) + '">Download</a></div>'
      ).join("") : '<p class="muted">No evidence documents uploaded yet.</p>';
    }
    if (!$("detailDialog").open) $("detailDialog").showModal();
  } catch (err) {
    toast(err.message);
  }
}

function renderPreview(result) {
  const s = result.summary || {};
  state.importBatch = result.batch_id;
  state.importCanRun = !!s.can_import;
  state.importWarnings = Number(s.warning_rows || 0) > 0;
  $("importPreview").hidden = false;
  set("previewTitle", result.file_name || "Workbook preview");
  const detectedVersion = result.template_version || "unknown";
  set(
    "previewDescription",
    (result.message || "Validation finished. No database records have been changed.") +
      " Detected workbook: " + detectedVersion +
      ". Blank cells preserve existing values."
  );
  set("previewBadge", "PREVIEWED");
  set("previewTotal", s.total_rows || 0);
  set("previewValid", s.valid_rows || 0);
  set("previewWarnings", s.warning_rows || 0);
  set("previewErrors", s.error_rows || 0);
  const allowed = state.importCanRun;
  $("previewEligibility").className = "preview-eligibility " + (allowed ? "eligible" : "ineligible");
  $("previewEligibility").textContent = allowed ? "Ready to confirm. Review and acknowledge warnings where present." : "Import blocked: correct the validation errors and upload the corrected workbook.";
  const issues = result.issues || [];
  $("issuesSection").hidden = !issues.length;
  set("issuesCount", issues.length + " issue(s)");
  $("issuesBody").innerHTML = issues.map((x) =>
    "<tr><td><span class=\"severity-tag severity-" + esc(String(x.severity || "").toLowerCase()) + "\">" +
    esc(x.severity) + "</span></td><td>" + esc(x.entity || "—") + "</td><td>" +
    esc((x.sheet || "") + (x.row ? " / row " + x.row : "")) + "</td><td>" +
    esc(x.message || x.detail || x.code || "Validation issue") + "</td></tr>"
  ).join("");
  $("issuesTruncated").hidden = !result.issues_truncated;
  $("warningAckWrap").hidden = !state.importWarnings;
  $("acceptWarnings").checked = false;
  $("confirmImportButton").disabled = !allowed || (state.importWarnings && !$("acceptWarnings").checked);
  set("confirmationHint", allowed ? (state.importWarnings ? "Acknowledge warnings before confirmation." : "Validation passed.") : "Resolve errors before import.");
}

async function previewWorkbook() {
  const file = $("importFile").files[0];
  if (!file) return;
  const data = new FormData();
  data.append("file", file);
  $("previewImportButton").disabled = true;
  try {
    const response = await fetch("/api/imports/preview", { method: "POST", body: data });
    const result = await response.json();
    if (!response.ok || result.success === false) throw new Error(result.message || "Workbook validation failed.");
    renderPreview(result);
    toast("Workbook validation completed.", true);
  } catch (err) {
    $("importFeedback").hidden = false;
    $("importFeedback").textContent = err.message;
    $("importFeedback").className = "import-feedback feedback-error";
    $("importPreview").hidden = true;
  } finally {
    $("previewImportButton").disabled = false;
  }
}

async function confirmImport() {
  if (!state.importBatch || !state.importCanRun) return;
  const accepted = $("acceptWarnings").checked;
  if (state.importWarnings && !accepted) return;
  $("confirmImportButton").disabled = true;
  try {
    const result = await api("/api/imports/" + state.importBatch + "/confirm", jsonOptions("POST", { accept_warnings: accepted }));
    const r = result.result || {};
    $("importFeedback").hidden = false;
    $("importFeedback").className = "import-feedback feedback-success";
    $("importFeedback").textContent = result.message || "Import completed.";
    $("importPreview").hidden = true;
    state.importBatch = null;
    await Promise.all([loadImportHistory(), loadOverview()]);
    toast("Import completed. Existing records were preserved where source cells were blank.", true);
  } catch (err) {
    toast(err.message);
    $("confirmImportButton").disabled = false;
  }
}

async function uploadEvidence(event) {
  event.preventDefault();
  const r = state.detail;
  const file = $("documentFile").files[0];
  if (!r || !file) {
    toast("Choose a document first.");
    return;
  }
  const form = new FormData($("documentUploadForm"));
  const button = $("uploadDocumentButton");
  button.disabled = true;
  try {
    await api("/api/dashboard/khs/" + encodeURIComponent(r.khs_id) + "/documents", {
      method: "POST",
      body: form
    });
    toast("Evidence document uploaded.", true);
    $("documentUploadForm").reset();
    await openDetails(r.khs_id);
  } catch (err) {
    toast(err.message);
  } finally {
    button.disabled = false;
  }
}

function syncImportFile(file) {
  if (!file) {
    set("importFileName", "No file selected");
    $("previewImportButton").disabled = true;
    return false;
  }
  if (!/\.xlsx$/i.test(file.name || "")) {
    toast("Please choose an Excel workbook in .xlsx format.");
    return false;
  }
  set("importFileName", file.name);
  $("previewImportButton").disabled = false;
  $("importPreview").hidden = true;
  $("importFeedback").hidden = true;
  return true;
}

function bindImportDropzone() {
  const zone = document.querySelector(".upload-card");
  const input = $("importFile");
  if (!zone || !input) return;

  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("is-dragover");
  });
  ["dragleave", "dragend"].forEach((name) => zone.addEventListener(name, (event) => {
    if (name === "dragleave" && zone.contains(event.relatedTarget)) return;
    zone.classList.remove("is-dragover");
  }));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragover");
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (!file) return;
    if (!/\.xlsx$/i.test(file.name || "")) {
      toast("Only .xlsx Excel workbooks can be uploaded.");
      return;
    }
    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      syncImportFile(file);
    } catch (_) {
      toast("Use Choose file to select this workbook in your browser.");
    }
  });
}

function bind() {
  document.querySelectorAll(".nav-link[data-page]").forEach((el) => {
    el.addEventListener("click", (event) => {
      event.preventDefault();
      if (el.dataset.page === "register") {
        state.workflowStageFilter = null;
        state.workflowRoleFilter = null;
        state.attentionOnly = false;
      }
      go(el.dataset.page);
    });
  });
  document.querySelectorAll("[data-go]").forEach((el) =>
    el.addEventListener("click", () => {
      if (el.dataset.go === "register") {
        state.workflowStageFilter = null;
        state.workflowRoleFilter = null;
        state.attentionOnly = el.dataset.attentionOnly === "true";
        state.registerPage = 1;
        if (state.attentionOnly) clearRegisterFilters();
      }
      go(el.dataset.go);
    })
  );
  document.querySelectorAll("[data-queue-stage]").forEach((el) =>
    el.addEventListener("click", () => {
      state.workflowStageFilter = el.dataset.queueStage;
      state.workflowRoleFilter = null;
      state.attentionOnly = false;
      state.registerPage = 1;
      clearRegisterFilters();
      go("register");
    })
  );
  document.querySelectorAll("[data-queue-role]").forEach((el) =>
    el.addEventListener("click", () => {
      state.workflowStageFilter = null;
      state.workflowRoleFilter = el.dataset.queueRole;
      state.attentionOnly = false;
      state.registerPage = 1;
      clearRegisterFilters();
      go("register");
    })
  );
  $("refreshButton").addEventListener("click", () => loadPage(state.page).catch((e) => toast(e.message)));
  $("workflowRefresh").addEventListener("click", () => loadWorkflow().catch((e) => toast(e.message)));
  $("activityRefresh").addEventListener("click", () => { state.activityPage = 1; loadActivity().catch((e) => toast(e.message)); });
  $("refreshHistoryButton").addEventListener("click", () => { state.historyPage = 1; loadImportHistory().catch((e) => toast(e.message)); });
  ["newRequestButton", "createRequestButton"].forEach((id) => $(id).addEventListener("click", () => openForm("request").catch((e) => toast(e.message))));
  ["quickAddKhs", "overviewAddKhs", "createKhsButton"].forEach((id) => $(id).addEventListener("click", () => openForm("khs").catch((e) => toast(e.message))));
  $("recordForm").addEventListener("submit", saveRecord);
  $("documentUploadForm").addEventListener("submit", uploadEvidence);
  ["closeRecordDialog", "cancelRecord"].forEach((id) => $(id).addEventListener("click", () => $("recordDialog").close()));
  $("closeDialog").addEventListener("click", () => $("detailDialog").close());
  $("closeDialogBottom").addEventListener("click", () => $("detailDialog").close());
  $("editDetailButton").addEventListener("click", () => {
    const r = state.detail;
    if (!r) return;
    $("detailDialog").close();
    openForm("khs", r).catch((e) => toast(e.message));
  });
  $("exportKhsButton").addEventListener("click", () => { window.location.href = "/api/dashboard/export"; });
  $("downloadCurrentWorkbookButton").addEventListener("click", () => { window.location.href = "/api/imports/workbook.xlsx"; });
  $("requestSearch").addEventListener("input", () => {
    state.requestQuery = $("requestSearch").value.trim();
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => { state.requestPage = 1; loadRequests().catch((e) => toast(e.message)); }, 300);
  });
  $("requestSearchReset").addEventListener("click", () => { $("requestSearch").value = ""; state.requestQuery = ""; state.requestPage = 1; loadRequests().catch((e) => toast(e.message)); });
  $("requestPrevious").addEventListener("click", () => { if (state.requestPage > 1) { state.requestPage--; loadRequests().catch((e) => toast(e.message)); } });
  $("requestNext").addEventListener("click", () => { state.requestPage++; loadRequests().catch((e) => toast(e.message)); });
  $("requestSearch").addEventListener("change", () => { state.requestQuery = $("requestSearch").value.trim(); });
  $("searchInput").addEventListener("input", () => {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => { state.registerPage = 1; loadRegister().catch((e) => toast(e.message)); }, 300);
  });
  ["statusFilter", "executorFilter", "subtypeFilter", "waitingFilter", "stageFilter"].forEach((id) =>
    $(id).addEventListener("change", () => { state.registerPage = 1; loadRegister().catch((e) => toast(e.message)); })
  );
  $("resetFilters").addEventListener("click", () => {
    clearRegisterFilters();
    state.workflowStageFilter = null;
    state.workflowRoleFilter = null;
    state.attentionOnly = false;
    state.registerPage = 1;
    loadRegister().catch((e) => toast(e.message));
  });
  $("previousPage").addEventListener("click", () => { if (state.registerPage > 1) { state.registerPage--; loadRegister().catch((e) => toast(e.message)); } });
  $("nextPage").addEventListener("click", () => { state.registerPage++; loadRegister().catch((e) => toast(e.message)); });
  $("historyPrevious").addEventListener("click", () => { if (state.historyPage > 1) { state.historyPage--; loadImportHistory().catch((e) => toast(e.message)); } });
  $("historyNext").addEventListener("click", () => { state.historyPage++; loadImportHistory().catch((e) => toast(e.message)); });
  $("activityPrevious").addEventListener("click", () => { if (state.activityPage > 1) { state.activityPage--; loadActivity().catch((e) => toast(e.message)); } });
  $("activityNext").addEventListener("click", () => { state.activityPage++; loadActivity().catch((e) => toast(e.message)); });
  $("importFile").addEventListener("change", () => {
    const file = $("importFile").files[0];
    if (file && !syncImportFile(file)) $("importFile").value = "";
    else if (!file) syncImportFile(null);
  });
  bindImportDropzone();
  $("previewImportButton").addEventListener("click", previewWorkbook);
  $("confirmImportButton").addEventListener("click", confirmImport);
  $("acceptWarnings").addEventListener("change", () => {
    $("confirmImportButton").disabled = !state.importCanRun || (state.importWarnings && !$("acceptWarnings").checked);
  });
  $("requestBody").addEventListener("click", (event) => {
    const edit = event.target.closest("[data-edit-request]");
    const add = event.target.closest("[data-add-child]");
    if (edit) {
      const row = state.requests.find((r) => r.request_id === edit.dataset.editRequest);
      if (row) openForm("request", row).catch((e) => toast(e.message));
    }
    if (add) openForm("khs", null, add.dataset.addChild).catch((e) => toast(e.message));
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-view-khs]");
    if (button) openDetails(button.dataset.viewKhs);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bind();
  const initial = window.location.hash.replace("#", "");
  go(["overview", "requests", "register", "lp", "contracts", "workflow", "imports", "activity"].indexOf(initial) >= 0 ? initial : "overview");
});
})();