(() => {
"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  page: "overview",
  requestPage: 1,
  registerPage: 1,
  historyPage: 1,
  activityPage: 1,
  activityQuery: "",
  activityEntity: "",
  saving: false,
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


const itemFieldGroups = [
  { id:"supplier-contract", title:"Supplier & contract", description:"The request, supplier, owner, and contract identity.", fields:["request_id","vendor_name","executor_code","subtype","dispatch_date","contract_start_date","contract_end_date"] },
  { id:"commercial-approvals", title:"Commercial & MI approvals", description:"Commercial checkpoints and approvals required before LP circulation.", fields:["boq_confirmation_date","negotiation_date","final_negotiation_date","mi_head_approval_date","mi_sm_approval_date","mi_gm_approval_date","legal_submission_date"] },
  { id:"lp-circulation", title:"LP Circulation", description:"Record each submission, completion, and approval date only when supported by evidence.", fields:["lp_circulation_start_date","lp_contract_team_completion_date","lp_junior_manager_approval_date","lp_senior_manager_approval_date","lp_gm_scm_approval_date","lp_completion_date"] },
  { id:"khs-injection", title:"KHS Injection", description:"This phase starts only after Director-signed LP completion.", fields:["khs_inject_start_date","khs_inject_completion_date"] },
  { id:"coordination", title:"Coordination & next action", description:"Who currently holds the action, why it is waiting, and contextual notes.", fields:["waiting_for","waiting_reason","remarks"] }
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

function syncRefreshVisibility(page) {
  const refresh = $("refreshButton");
  if (!refresh) return;
  const pageSpecific = {
    overview: "overviewRefresh",
    lp: "lpRefresh",
    contracts: "contractRefresh",
    workflow: "workflowRefresh",
    activity: "activityRefresh"
  };
  refresh.hidden = !!pageSpecific[page];
}

function closeMobileNavigation() {
  const sidebar = document.querySelector(".sidebar");
  const toggle = $("mobileNavToggle");
  if (sidebar) sidebar.classList.remove("nav-open");
  if (toggle) {
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open navigation");
  }
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
  syncRefreshVisibility(page);
  closeMobileNavigation();
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
      api("/api/dashboard/khs?attention=true&per_page=5"),
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
      "lpQueueTotal", "lpContractTeamCount", "lpJuniorCount", "lpSeniorCount",
      "lpGeneralCount", "lpDirectorCount", "lpPrerequisiteCount",
      "lpLegacyUnverifiedCount", "lpTimelineGapsCount"
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

  set("lpContractTeamCount", countFor(lp, "contract_team"));
  set("lpJuniorCount", countFor(lp, "junior_manager"));
  set("lpSeniorCount", countFor(lp, "senior_manager"));
  set("lpGeneralCount", countFor(lp, "general_manager"));
  set("lpDirectorCount", countFor(lp, "director"));
  set("lpQueueTotal", data.lp_active_total);
  set("lpPrerequisiteCount", data.lp_prerequisite_exceptions || 0);
  set("lpLegacyUnverifiedCount", data.lp_legacy_unverified || 0);
  set("lpTimelineGapsCount", data.lp_timeline_gaps || 0);
  set(
    "lpQueueNote",
    "Current LP stage is derived from the ordered milestone dates. Exceptions are kept outside the approval lanes."
  );
}

function renderAttention(rows) {
  const body = $("attentionBody");
  if (!body) return;
  if (!rows.length) {
    emptyRow("attentionBody", 6, "No records currently require attention.");
    return;
  }
  body.innerHTML = rows.map((r) => {
    const age = r.lp_stage_age_days == null ? "—" :
      r.lp_stage_age_days + (r.lp_stage_age_days === 1 ? " day in stage" : " days in stage");
    const exception = r.lp_started_without_mi_gm_approval
      ? '<span class="exception-label">MI GM prerequisite exception</span>' : "";
    const waitingFor = r.waiting_for ||
      (r.lp_started_without_mi_gm_approval ? "Review prerequisite" : "Review next action");
    return `<tr>
      <td data-label="REQUEST / KHS"><span class="cell-primary">${esc(r.request_subject || "Untitled request")}</span>
      <span class="cell-secondary">${esc(r.khs_id)} · ${esc(r.request_id)}</span></td>
      <td data-label="VENDOR">${esc(r.vendor_name)}</td>
      <td data-label="CURRENT STAGE">${esc(r.current_stage_name || r.current_stage_code)}${exception}</td>
      <td data-label="WAITING FOR / NEXT ACTION"><span class="cell-primary">${esc(waitingFor)}</span>
      ${r.waiting_reason ? '<span class="cell-secondary">' + esc(r.waiting_reason) + "</span>" : ""}</td>
      <td data-label="STAGE AGE / UPDATED"><span class="cell-primary">${esc(age)}</span>
      <span class="cell-secondary">Updated ${esc(fmt(r.last_updated_date || r.updated_at))}</span></td>
      <td data-label="ACTION"><button class="view-button" data-view-khs="${esc(r.khs_id)}"
      aria-label="Open KHS ${esc(r.khs_id)}">View record</button></td>
    </tr>`;
  }).join("");
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

function renderActiveRegisterFilters() {
  const container = $("activeRegisterFilters");
  if (!container) return;
  const filters = [];
  const controls = [
    ["searchInput", "Search"],
    ["statusFilter", "LP status"],
    ["executorFilter", "Executor"],
    ["subtypeFilter", "Contract type"],
    ["waitingFilter", "Waiting for"],
    ["stageFilter", "Workflow stage"]
  ];
  controls.forEach(([id, label]) => {
    const control = $(id);
    if (!control || !control.value) return;
    const option = control.tagName === "SELECT" ? control.options[control.selectedIndex] : null;
    const value = option ? option.textContent : control.value;
    filters.push({id, label, value});
  });
  if (state.workflowStageFilter) filters.push({id:"workflowStageFilter",label:"Stage",value:state.workflowStageFilter.replace(/_/g," ")});
  if (state.workflowRoleFilter) filters.push({id:"workflowRoleFilter",label:"Approval role",value:state.workflowRoleFilter.replace(/_/g," ")});
  if (state.attentionOnly) filters.push({id:"attentionOnly",label:"Queue",value:"Needs attention"});
  container.hidden = filters.length === 0;
  container.innerHTML = filters.map((filter) =>
    '<button type="button" class="filter-chip" data-clear-filter="' + esc(filter.id) + '">' +
    '<span>' + esc(filter.label) + ': ' + esc(filter.value) + '</span><span aria-hidden="true">×</span></button>'
  ).join("") + (filters.length ? '<button type="button" class="clear-all-filters" data-clear-filter="all">Clear all</button>' : "");
  const summary = document.querySelector(".filter-more summary");
  if (summary) summary.textContent = filters.length ? "More filters · " + filters.length + " active" : "More filters";
}

function clearOneRegisterFilter(id) {
  if (id === "all") {
    clearRegisterFilters();
    state.workflowStageFilter = null;
    state.workflowRoleFilter = null;
    state.attentionOnly = false;
  } else if (id === "workflowStageFilter") {
    state.workflowStageFilter = null;
  } else if (id === "workflowRoleFilter") {
    state.workflowRoleFilter = null;
  } else if (id === "attentionOnly") {
    state.attentionOnly = false;
  } else {
    const control = $(id);
    if (control) control.value = "";
  }
  state.registerPage = 1;
  loadRegister().catch((error) => toast(error.message));
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
  if (!result.data.length) emptyRow("registerBody", 6, "No KHS records match the current filters.");
  else body.innerHTML = result.data.map((r) => {
    const stage = r.lp_stage_label || r.current_stage_name || "Not started";
    const stageAge = r.lp_stage_age_days == null
      ? (r.lp_timeline_has_gaps ? "Historical dates need review" : "No active LP stage")
      : r.lp_stage_age_days + (r.lp_stage_age_days === 1 ? " day in stage" : " days in stage");
    const lpStatus = String(r.lp_status || "not_started").replace(/_/g, " ");
    const injection = r.khs_inject_completion_date
      ? '<span class="status-badge status-completed">Fully injected</span><span class="cell-secondary">' + esc(fmt(r.khs_inject_completion_date)) + "</span>"
      : r.khs_inject_start_date
        ? '<span class="status-badge status-in_progress">Injection started</span><span class="cell-secondary">' + esc(fmt(r.khs_inject_start_date)) + "</span>"
        : '<span class="status-badge status-neutral">Not started</span>';
    const exception = r.lp_prerequisite_exception || r.lp_started_without_mi_gm_approval
      ? '<span class="exception-label">MI GM prerequisite review</span>'
      : r.lp_legacy_unverified
        ? '<span class="exception-label">Director sign-off unverified</span>'
        : r.lp_timeline_has_gaps
          ? '<span class="exception-label">Historical timeline gaps</span>' : "";
    return "<tr>" +
      '<td><span class="cell-primary">' + esc(r.request_subject || "Untitled request") + '</span>' +
      '<span class="cell-secondary">' + esc(r.vendor_name) + " · " + esc(r.khs_id) + '</span>' +
      '<span class="cell-tertiary">' + esc(r.executor_name || r.executor_code || "Unassigned") + "</span></td>" +
      '<td><span class="cell-primary">' + esc(stage) + '</span>' +
      '<span class="cell-secondary">' + esc(stageAge) + "</span>" + exception + "</td>" +
      '<td><span class="status-badge status-' + esc(r.lp_status || "not_started") + '">' + esc(lpStatus) + "</span></td>" +
      "<td>" + injection + "</td>" +
      '<td><span class="cell-primary">' + esc(r.waiting_for || (exception ? "Review data / prerequisite" : "No waiting owner recorded")) + '</span>' +
      (r.waiting_reason ? '<span class="cell-secondary">' + esc(r.waiting_reason) + "</span>" : "") + "</td>" +
      '<td><button type="button" class="view-button" data-view-khs="' + esc(r.khs_id) + '">Details</button></td>' +
      "</tr>";
  }).join("");
  renderActiveRegisterFilters();
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
  const rows = result.data || [];
  wrap.innerHTML = rows.length ? rows.map((r) =>
    '<button type="button" class="workflow-stage" data-workflow-stage="' + esc(r.stage_code) + '">' +
    '<span class="workflow-stage-top"><span>' + esc(r.stage_name) + '</span><strong>' + esc(r.total) + "</strong></span>" +
    '<span class="workflow-stage-bottom">' + esc(r.completed) + ' completed <span>Open matching records →</span></span>' +
    "</button>"
  ).join("") : '<div class="empty-state">No workflow stage data is available.</div>';
}

async function loadLPCirculation() {
  const params = new URLSearchParams({ page: String(state.lpPage), per_page: String(state.perPage) });
  const q = $("lpSearch") ? $("lpSearch").value.trim() : "";
  const stage = $("lpStageFilter") ? $("lpStageFilter").value : "";
  if (q) params.set("q", q);
  if (stage) params.set("stage", stage);
  const result = await api("/api/dashboard/lp-circulation?" + params.toString());
  const summary = result.summary || {};
  const byStage = summary.by_stage || {};
  set("lpTotalRecords", summary.total_lp_records || 0);
  set("lpCountContractTeam", byStage.contract_team || 0);
  set("lpCountJunior", byStage.junior_manager || 0);
  set("lpCountSenior", byStage.senior_manager || 0);
  set("lpCountGm", byStage.general_manager || 0);
  set("lpCountDirector", byStage.director || 0);
  set("lpCountCompleted", byStage.completed || 0);
  set("lpCountPrerequisite", summary.prerequisite_exceptions || 0);
  set("lpCountLegacyUnverified", byStage.legacy_unverified || 0);
  set("lpCountLegacy", byStage.legacy_incomplete || 0);

  const body = $("lpBody");
  if (!body) return;
  if (!result.data.length) {
    emptyRow("lpBody", 8, "No LP records match the selected stage.");
  } else {
    body.innerHTML = result.data.map((r) => {
      const age = r.lp_stage_age_days == null ? "—" : r.lp_stage_age_days + " days";
      const history = r.lp_timeline_has_gaps
        ? '<span class="status-badge status-warning">Partial history</span>'
        : '<span class="status-badge status-completed">Recorded</span>';
      const prerequisiteFlag = r.lp_prerequisite_exception
        ? '<span class="exception-label">MI GM prerequisite exception</span>' : "";
      const legacyFlag = r.lp_legacy_unverified
        ? '<span class="exception-label">Legacy Director sign-off unverified</span>' : "";
      return "<tr><td><span class=\"cell-primary\">" + esc(r.khs_id) + "</span>" +
        "<span class=\"cell-secondary\">" + esc(r.vendor_name) + "</span></td>" +
        "<td><span class=\"cell-primary\">" + esc(r.request_subject || "Untitled request") + "</span>" +
        "<span class=\"cell-secondary\">" + esc(r.request_id) + "</span></td>" +
        "<td><span class=\"cell-primary\">" + esc(r.lp_stage_label || "—") + "</span>" +
        prerequisiteFlag + legacyFlag +
        (r.waiting_for ? "<span class=\"cell-secondary\">Waiting for " + esc(r.waiting_for) + "</span>" : "") + "</td>" +
        "<td>" + esc(age) + "</td><td>" + esc(fmt(r.lp_circulation_start_date)) + "</td>" +
        "<td>" + esc(r.waiting_reason || "—") + "</td><td>" + history + "</td>" +
        "<td><button type=\"button\" class=\"view-button\" data-view-khs=\"" + esc(r.khs_id) + "\">Details</button></td></tr>";
    }).join("");
  }
  const p = result.pagination || {};
  set("lpPagination", "Page " + p.page + " of " + p.total_pages + " · " + p.total_records + " LP records");
  $("lpPrevious").disabled = !p.has_previous;
  $("lpNext").disabled = !p.has_next;
}

function lifecycleStatusLabel(status) {
  const labels = {
    missing_dates: "Missing contract dates",
    invalid_dates: "Invalid contract dates",
    expired: "Expired",
    critical_7d: "Final warning · 7 days",
    urgent_14d: "Urgent · 14 days",
    urgent_1m: "Action required · 1 month",
    watch_3m: "Renewal watch · 3 months",
    prep_6m: "Renewal preparation · 6 months",
    active: "Active · over 6 months",
    not_fully_injected: "Not fully injected"
  };
  return labels[status] || status || "—";
}

function lifecycleBadgeClass(status) {
  if (status === "expired" || status === "critical_7d") return "status-danger";
  if (status === "urgent_14d" || status === "urgent_1m") return "status-warning";
  if (status === "watch_3m" || status === "prep_6m") return "status-in_progress";
  if (status === "active") return "status-completed";
  return "status-neutral";
}

function contractOperationalStatusLabel(status) {
  const labels = {
    upcoming: "Upcoming",
    active: "Active",
    expired: "Expired",
    missing_dates: "Missing dates",
    invalid_dates: "Invalid dates",
    not_fully_injected: "Not fully injected"
  };
  return labels[status] || status || "—";
}

function contractOperationalBadgeClass(status) {
  if (status === "expired") return "status-danger";
  if (status === "upcoming") return "status-in_progress";
  if (status === "active") return "status-completed";
  return "status-neutral";
}

function timeRemainingLabel(days) {
  if (days == null) return "Dates required";
  if (days < 0) return Math.abs(days) + " days overdue";
  if (days === 0) return "Expires today";
  return days + " days remaining";
}

async function loadContractLifecycle() {
  const params = new URLSearchParams({ page: String(state.contractPage), per_page: String(state.perPage) });
  const q = $("contractSearch") ? $("contractSearch").value.trim() : "";
  const status = $("contractStatusFilter") ? $("contractStatusFilter").value : "";
  if (q) params.set("q", q);
  if (status) params.set("status", status);
  const result = await api("/api/dashboard/contracts/lifecycle?" + params.toString());
  const summary = result.summary || {};
  set("contractTotal", summary.total_fully_injected || 0);
  set("contractSixMonths", summary.expiring_within_6_months || 0);
  set("contractThreeMonths", summary.expiring_within_3_months || 0);
  set("contractOneMonth", summary.expiring_within_1_month || 0);
  set("contractExpired", summary.expired || 0);
  set("contractMissingDates", summary.missing_contract_dates || 0);

  const body = $("contractBody");
  if (!body) return;
  if (!result.data.length) {
    emptyRow("contractBody", 9, "No fully injected contracts match this lifecycle filter.");
  } else {
    body.innerHTML = result.data.map((r) => {
      const statusValue = r.contract_renewal_alert_status || r.contract_lifecycle_status;
      const badge = lifecycleBadgeClass(statusValue);
      const operationalStatus = r.contract_operational_status;
      const operationalBadge = contractOperationalBadgeClass(operationalStatus);
      return "<tr><td><span class=\"cell-primary\">" + esc(r.khs_id) + "</span>" +
        "<span class=\"cell-secondary\">" + esc(r.vendor_name) + "</span></td>" +
        "<td><span class=\"cell-primary\">" + esc(r.request_subject || "Untitled request") + "</span>" +
        "<span class=\"cell-secondary\">" + esc(r.request_id) + "</span></td>" +
        "<td>" + esc(fmt(r.khs_inject_completion_date)) + "</td>" +
        "<td>" + esc(fmt(r.contract_start_date)) + " – " + esc(fmt(r.contract_end_date)) + "</td>" +
        "<td>" + esc(r.contract_duration_label || "—") + "</td>" +
        "<td><span class=\"cell-primary\">" + esc(timeRemainingLabel(r.contract_days_remaining)) + "</span>" +
        (r.contract_days_remaining != null && r.contract_days_remaining >= 0 && r.contract_days_remaining <= 30
          ? "<span class=\"cell-secondary\">Renewal action due</span>" : "") + "</td>" +
        "<td><span class=\"status-badge " + operationalBadge + "\">" + esc(contractOperationalStatusLabel(operationalStatus)) + "</span></td>" +
        "<td><span class=\"status-badge " + badge + "\">" + esc(lifecycleStatusLabel(statusValue)) + "</span></td>" +
        "<td><button type=\"button\" class=\"view-button\" data-view-khs=\"" + esc(r.khs_id) + "\">Details</button></td></tr>";
    }).join("");
  }
  const p = result.pagination || {};
  set("contractPagination", "Page " + p.page + " of " + p.total_pages + " · " + p.total_records + " contracts");
  $("contractPrevious").disabled = !p.has_previous;
  $("contractNext").disabled = !p.has_next;
}

function renderLPTimeline(record) {
  const container = $("lpTimeline");
  if (!container) return;
  const stages = [
    ["lp_circulation_start_date", "User submitted", "LP circulation started", null],
    ["lp_contract_team_completion_date", "Tim Kontrak", "Contract Team completion", "contract_team"],
    ["lp_junior_manager_approval_date", "Junior Manager Vendor Management", "Vendor Management approval", "junior_manager"],
    ["lp_senior_manager_approval_date", "Senior Manager Strategic Sourcing", "Strategic Sourcing approval", "senior_manager"],
    ["lp_gm_scm_approval_date", "GM SCM", "General Management approval", "general_manager"],
    ["lp_completion_date", "Director sign-off", "Director-signed LP completion", "director"]
  ];
  const currentIndex = stages.findIndex((stage) => stage[3] && stage[3] === record.lp_stage_key);
  const gapFields = new Set(record.lp_timeline_gaps || []);
  const prerequisiteException = !!record.lp_prerequisite_exception;
  const legacyUnverified = !!record.lp_legacy_unverified;
  const hasGaps = !!record.lp_timeline_has_gaps;
  const completed = record.lp_stage_key === "completed";
  const notStarted = record.lp_stage_key === "not_started";
  const reviewRequired = prerequisiteException || legacyUnverified || hasGaps;
  const lastRecordedIndex = stages.reduce((last, stage, index) => record[stage[0]] ? index : last, -1);

  let currentTitle = "Review required";
  let currentMeta = "The available milestone history does not support a reliable active-stage assignment.";
  let upcomingTitle = "After verification";
  let upcomingMeta = "No next approval stage has been inferred.";
  let ageTitle = "Not calculated";
  let ageMeta = "Stage age is withheld until the current stage can be established.";

  if (currentIndex >= 1 && !reviewRequired) {
    currentTitle = stages[currentIndex][1];
    currentMeta = "The next approval or completion milestone is outstanding.";
    const age = record.lp_stage_age_days;
    if (age !== null && age !== undefined && Number.isFinite(Number(age))) {
      const days = Number(age);
      ageTitle = days + (days === 1 ? " day" : " days");
      ageMeta = record.lp_stage_started_date ? "Since " + fmt(record.lp_stage_started_date) : "Since the last recorded LP milestone";
    }
    upcomingTitle = stages[currentIndex + 1] ? stages[currentIndex + 1][1] : "LP completed";
    upcomingMeta = stages[currentIndex + 1] ? "Next milestone in sequence" : "Final LP milestone";
  } else if (completed) {
    currentTitle = "LP completed";
    currentMeta = "Director sign-off recorded on " + fmt(record.lp_completion_date) + ".";
    upcomingTitle = "KHS Injection";
    upcomingMeta = "The post-LP contract phase.";
    ageTitle = "—";
    ageMeta = "There is no active LP stage.";
  } else if (notStarted) {
    currentTitle = "Not started";
    currentMeta = "LP circulation has not been initiated.";
    upcomingTitle = "User submission";
    upcomingMeta = "First milestone in the LP route.";
    ageTitle = "—";
    ageMeta = "The clock starts when LP is submitted.";
  } else if (prerequisiteException) {
    currentTitle = "Prerequisite review";
    currentMeta = "The LP start date does not satisfy the MI GM approval prerequisite.";
  } else if (legacyUnverified) {
    currentTitle = "Director sign-off unverified";
    currentMeta = "A legacy completion label is not proof of a Director-signed LP.";
  } else if (hasGaps) {
    currentTitle = "Historical timeline incomplete";
    currentMeta = "Missing historical dates prevent a reliable current-stage assignment.";
  }

  const badge = $("lpTimelineStage");
  if (badge) {
    badge.className = "status-badge " + (completed ? "status-completed" :
      currentIndex >= 1 && !reviewRequired ? "status-in_progress" :
      notStarted ? "status-not_started" : "status-missing");
    badge.textContent = completed ? "LP completed" :
      currentIndex >= 1 && !reviewRequired ? "In progress" :
      notStarted ? "Not started" : "Review required";
  }
  set("lpCurrentStage", currentTitle);
  set("lpCurrentStageMeta", currentMeta);
  set("lpStageAge", ageTitle);
  set("lpStageAgeMeta", ageMeta);
  set("lpUpcomingStage", upcomingTitle);
  set("lpUpcomingMeta", upcomingMeta);

  container.innerHTML = stages.map((stage, index) => {
    const dateValue = record[stage[0]];
    const isDone = !!dateValue;
    const isCurrent = index === currentIndex && !reviewRequired;
    const isGap = !isDone && gapFields.has(stage[0]);
    let stateClass = "upcoming";
    let stateLabel = "Upcoming";
    let timeLabel = "Not yet reached";

    if (isDone) {
      stateClass = "done";
      stateLabel = "Completed";
      timeLabel = fmt(dateValue);
    } else if (isGap) {
      stateClass = "gap";
      stateLabel = "Date not recorded";
      timeLabel = "No historical date on record";
    } else if (isCurrent) {
      stateClass = "current";
      stateLabel = "Current Stage";
      timeLabel = record.lp_stage_started_date ? "Waiting since " + fmt(record.lp_stage_started_date) : "Awaiting completion";
    } else if (legacyUnverified) {
      stateClass = "review";
      stateLabel = "Unverified";
      timeLabel = "No Director-signed date recorded";
    } else if (prerequisiteException && index === 1) {
      stateClass = "review";
      stateLabel = "On hold";
      timeLabel = "MI GM prerequisite requires review";
    } else if (hasGaps && index <= lastRecordedIndex) {
      stateClass = "review";
      stateLabel = "Needs verification";
      timeLabel = "Historical sequence cannot be confirmed";
    }

    return '<div class="lp-timeline-item ' + stateClass + '" role="listitem">' +
      '<span class="lp-timeline-marker" aria-hidden="true">' + (isDone ? "✓" : String(index + 1).padStart(2, "0")) + "</span>" +
      '<div class="lp-timeline-content"><div class="lp-timeline-meta"><strong>' + esc(stage[1]) +
      '</strong><span class="lp-timeline-state">' + esc(stateLabel) + "</span></div>" +
      "<small>" + esc(stage[2]) + "</small><time>" + esc(timeLabel) + "</time></div></div>";
  }).join("");

  const notice = $("lpTimelineNotice");
  if (notice) {
    const noticeText = prerequisiteException
      ? "Prerequisite exception: LP circulation was recorded before MI GM approval, or the approval date is missing. The active approver is not inferred."
      : legacyUnverified
        ? "Legacy completion is not equivalent to Director sign-off. LP remains unverified until the Director-signed completion date is supported by evidence."
        : hasGaps
          ? "Historical timeline contains missing milestone dates. Recorded dates are preserved, and the current approver is not inferred from incomplete history."
          : "";
    notice.hidden = !noticeText;
    notice.textContent = noticeText;
  }
}

function renderContractDetail(record) {
  const summary = record.contract_lifecycle || {};
  const operationalStatus = summary.contract_operational_status || "not_fully_injected";
  const badge = $("contractDetailStatus");
  if (badge) {
    badge.className = "status-badge " + contractOperationalBadgeClass(operationalStatus);
    badge.textContent = contractOperationalStatusLabel(operationalStatus);
  }
  const items = [
    ["Contract status", summary.contract_operational_status_label || contractOperationalStatusLabel(operationalStatus)],
    ["Renewal alert", summary.contract_renewal_alert_label || summary.contract_lifecycle_label],
    ["Contract start", record.contract_start_date],
    ["Contract end", record.contract_end_date],
    ["Contract term", summary.contract_duration_label],
    ["Time remaining", timeRemainingLabel(summary.contract_days_remaining)],
    ["Injection started", record.khs_inject_start_date],
    ["Fully injected", record.khs_inject_completion_date]
  ];
  const grid = $("contractDetailGrid");
  if (grid) {
    grid.innerHTML = items.map((item) =>
      '<div class="contract-detail-item"><span>' + esc(item[0]) + '</span><strong>' + esc(fmt(item[1])) + "</strong></div>"
    ).join("");
  }
}

async function loadActivity() {
  const params = new URLSearchParams({
    page: String(state.activityPage),
    per_page: "25"
  });
  if (state.activityQuery) params.set("q", state.activityQuery);
  if (state.activityEntity) params.set("entity_type", state.activityEntity);
  const result = await api("/api/dashboard/activity?" + params.toString());
  const body = $("activityBody");
  if (!body) return;
  if (!result.data.length) emptyRow("activityBody", 6, "No activity matches the current filters.");
  else body.innerHTML = result.data.map((r) => {
    const changes = typeof r.changes === "string" ? r.changes : JSON.stringify(r.changes || {});
    return "<tr><td>" + esc(fmt(r.occurred_at)) + "</td><td>" + esc(r.entity_type) + "</td><td>" +
      esc(r.entity_id) + "</td><td>" + esc(r.action) + "</td><td>" + esc(r.actor) +
      '<td title="' + esc(changes) + '">' + esc(changes.length > 90 ? changes.slice(0, 90) + "…" : changes) + "</td></tr>";
  }).join("");
  const p = result.pagination || {};
  set("activityPagination", "Page " + p.page + " of " + p.total_pages + " · " + p.total_records + " activities");
  $("activityPrevious").disabled = !p.has_previous;
  $("activityNext").disabled = !p.has_next;
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
  const id = "field-" + name;
  const value = record && record[name] != null ? String(record[name]).slice(0, 10) : "";
  let control = "";
  if (type === "date") {
    control = '<input id="' + id + '" type="date" name="' + name + '" value="' + esc(value) + '" aria-label="' + esc(label) + '">';
  } else if (type === "textarea") {
    control = '<textarea id="' + id + '" name="' + name + '" rows="3" aria-label="' + esc(label) + '">' + esc(record && record[name] || "") + "</textarea>";
  } else if (type === "request") {
    const opts = state.requests.map((r) => '<option value="' + esc(r.request_id) + '">' +
      esc(r.request_subject + (r.vendor_summary ? " · " + r.vendor_summary : "")) + "</option>").join("");
    control = '<select id="' + id + '" name="request_id" required aria-label="' + esc(label) + '"><option value="">Select request</option>' + opts + "</select>";
  } else if (type === "executor") {
    const opts = state.executors.map((r) => '<option value="' + esc(r.executor_code) + '">' +
      esc(r.executor_code + " · " + r.display_name) + "</option>").join("");
    const legacy = record && record.executor_code && !state.executors.some((r) => r.executor_code === record.executor_code)
      ? '<option value="' + esc(record.executor_code) + '">' + esc(record.executor_code + " · current / inactive") + "</option>" : "";
    control = '<select id="' + id + '" name="executor_code" required aria-label="' + esc(label) + '"><option value="">Select executor</option>' + legacy + opts + "</select>";
  } else if (type === "subtype") {
    const current = record && record.subtype && !["Renewal", "Kontrak Baru"].includes(record.subtype)
      ? '<option value="' + esc(record.subtype) + '">' + esc(record.subtype) + "</option>" : "";
    control = '<select id="' + id + '" name="subtype" aria-label="' + esc(label) + '"><option value="">Select type</option>' + current + '<option>Renewal</option><option>Kontrak Baru</option></select>';
  } else {
    const required = ["request_subject", "vendor_name"].includes(name) ? " required" : "";
    control = '<input id="' + id + '" type="text" name="' + name + '" value="' + esc(record && record[name] || "") + '"' + required + ' aria-label="' + esc(label) + '">';
  }
  const full = type === "textarea";
  return '<div class="form-field' + (full ? " full" : "") + '"><label for="' + id + '">' + esc(label) + '</label>' + control + "</div>";
}

function renderGroupedKhsFields(record, editing) {
  const fieldMap = new Map(itemFields.map((field) => [field[0], field]));
  return itemFieldGroups.map((group) => {
    const fields = group.fields.filter((name) => !(editing && name === "request_id"));
    const fieldMarkup = fields.map((name, index) => {
      const html = fillDialogField(fieldMap.get(name), record, "khs");
      if (group.id !== "lp-circulation") return html;
      return '<div class="lp-form-step"><span class="lp-form-step-index" aria-hidden="true">' +
        String(index + 1).padStart(2, "0") + "</span>" + html + "</div>";
    }).join("");
    const isLp = group.id === "lp-circulation";
    return '<section class="form-section form-section-' + esc(group.id) + '">' +
      '<div class="form-section-heading"><div><h3>' + esc(group.title) +
      "</h3><p>" + esc(group.description) + "</p></div>" +
      (isLp ? '<span class="form-section-count">6 milestones</span>' : "") +
      '</div><div class="form-section-grid' + (isLp ? " lp-form-grid" : "") + '">' +
      fieldMarkup + "</div></section>";
  }).join("");
}

async function openForm(kind, record, parentRequestId) {
  if (kind === "khs") {
    const [, rq] = await Promise.all([
      ensureFilters(),
      api("/api/dashboard/requests?per_page=100")
    ]);
    state.requests = rq.data || [];
  }
  const editing = !!record;
  const defs = kind === "request" ? requestFields : itemFields.filter((f) =>
    !(editing && (f[0] === "request_id"))
  );
  state.editing = { kind: kind, record: record || null, original: record || {} };
  state.saving = false;
  const saveButton = $("saveRecord");
  if (saveButton) { saveButton.disabled = false; saveButton.textContent = "Save record"; }
  const recordError = $("recordError");
  if (recordError) { recordError.hidden = true; recordError.textContent = ""; }
  $("dialogEyebrow").textContent = editing ? "EDIT RECORD" : "NEW RECORD";
  $("dialogTitle").textContent = (editing ? "Edit " : "Create ") + (kind === "request" ? "Request" : "KHS item");
  $("dialogHint").textContent = kind === "khs"
    ? "Enter milestone dates only when supported by a recorded submission, approval, or completion. MI GM approval and LP chronology are validated when saved."
    : "Request ID is generated automatically when the record is saved.";
  const fieldsContainer = $("dialogFields");
  fieldsContainer.className = kind === "request" ? "form-grid" : "form-sections";
  fieldsContainer.innerHTML = kind === "request"
    ? defs.map((def) => fillDialogField(def, record, kind)).join("")
    : renderGroupedKhsFields(record, editing);
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
  if (!edit || state.saving) return;
  const form = $("recordForm");
  const button = $("saveRecord");
  const errorBox = $("recordError");
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
      state.editing = null;
      return;
    }
  }
  const base = "/api/dashboard/" + (edit.kind === "request" ? "requests" : "khs");
  const url = edit.record ? base + "/" + encodeURIComponent(edit.record[edit.kind === "request" ? "request_id" : "khs_id"]) : base;
  const method = edit.record ? "PATCH" : "POST";
  state.saving = true;
  button.disabled = true;
  button.textContent = "Saving…";
  if (errorBox) { errorBox.hidden = true; errorBox.textContent = ""; }
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
    if (errorBox) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
    }
    toast(err.message);
  } finally {
    state.saving = false;
    if ($("recordDialog").open) {
      button.disabled = false;
      button.textContent = "Save record";
    }
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
      (r.lp_prerequisite_exception ? '<span class="status-badge status-error">MI GM prerequisite exception</span>' : "");
    renderLPTimeline(r);
    renderContractDetail(r);

    const detailGroups = [
      { title:"Supplier & request", items:[
        ["Request subject",r.request_subject],["Request ID",r.request_id],
        ["Vendor",r.vendor_name],["Executor",r.executor_name || r.executor_code],["Contract type",r.subtype]
      ]},
      { title:"Commercial & approval history", items:[
        ["Dispatch",r.dispatch_date],["BOQ confirmation",r.boq_confirmation_date],
        ["Contract start",r.contract_start_date],["Contract end",r.contract_end_date],
        ["Negotiation",r.negotiation_date],["Final negotiation",r.final_negotiation_date],
        ["MI Head approval",r.mi_head_approval_date],["MI SM approval",r.mi_sm_approval_date],
        ["MI GM approval",r.mi_gm_approval_date],["Legal submission",r.legal_submission_date]
      ]},
      { title:"Coordination & next action", items:[
        ["Waiting for",r.waiting_for],["Waiting reason",r.waiting_reason],
        ["Remarks",r.remarks],["Last updated",r.last_updated_date || r.updated_at]
      ]}
    ];
    const detailGrid = $("detailGrid");
    detailGrid.innerHTML = detailGroups.map((group) =>
      '<section class="detail-group"><h4>' + esc(group.title) +
      '</h4><div class="detail-group-fields">' +
      group.items.map((item) =>
        '<div class="detail-item"><span class="detail-label">' + esc(item[0]) +
        '</span><span class="detail-value">' + esc(fmt(item[1])) + "</span></div>"
      ).join("") + "</div></section>"
    ).join("");

    const history = result.history || [];
    if (history.length) {
      detailGrid.insertAdjacentHTML("beforeend",
        '<section class="detail-group detail-group-wide"><h4>Recent activity</h4>' +
        '<ol class="detail-history-list">' +
        history.slice(0, 5).map((entry) =>
          "<li><time>" + esc(fmt(entry.occurred_at)) + "</time><strong>" +
          esc(entry.action) + "</strong><span>" + esc(entry.actor) + "</span></li>"
        ).join("") + "</ol></section>"
      );
    }

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

  const plan = result.change_plan || {};
  const changePlan = $("changePlan");
  if (changePlan) {
    changePlan.hidden = false;
    set("changePlanCount", (plan.total_records || 0) + " records checked");
    set("planNew", plan.new_records || 0);
    set("planUpdated", plan.updated_records || 0);
    set("planUnchanged", plan.unchanged_records || 0);
    set("planFields", plan.changed_fields_count || 0);
    const changes = plan.changes || [];
    $("changePlanBody").innerHTML = changes.length
      ? changes.map((item) =>
          "<tr><td><strong>" + esc(item.id || "—") + "</strong><span class=\"cell-secondary\">" +
          esc(item.entity || "—") + "</span></td><td>" + esc(item.operation || "—") +
          "</td><td>" + esc((item.changed_fields || []).join(", ") || "—") + "</td></tr>"
        ).join("")
      : '<tr><td colspan="3" class="table-message">No record fields will change. The uploaded values match the current database.</td></tr>';
  }

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

function decorateResponsiveTableRows(tbody) {
  const table = tbody.closest("table");
  if (!table) return;
  const headers = Array.from(table.querySelectorAll("thead th")).map((th) => th.textContent.trim());
  tbody.querySelectorAll("tr").forEach((row) => {
    const cells = Array.from(row.children).filter((cell) => cell.tagName === "TD");
    if (cells.length === 1 && cells[0].hasAttribute("colspan")) {
      cells[0].removeAttribute("data-label");
      return;
    }
    cells.forEach((cell, index) => {
      const label = headers[index] || (index === cells.length - 1 ? "Action" : "Details");
      cell.dataset.label = label;
    });
  });
}

function observeResponsiveTables() {
  document.querySelectorAll(".table-wrap tbody").forEach((tbody) => {
    decorateResponsiveTableRows(tbody);
    const observer = new MutationObserver(() => decorateResponsiveTableRows(tbody));
    observer.observe(tbody, {childList:true, subtree:true});
  });
}

function bind() {
  const navToggle = $("mobileNavToggle");
  if (navToggle) navToggle.addEventListener("click", () => {
    const sidebar = document.querySelector(".sidebar");
    const open = sidebar.classList.toggle("nav-open");
    navToggle.setAttribute("aria-expanded", String(open));
    navToggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
  });
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
  document.querySelectorAll("[data-lp-queue-stage]").forEach((el) =>
    el.addEventListener("click", () => {
      const filter = $("lpStageFilter");
      if (filter) filter.value = el.dataset.lpQueueStage;
      state.lpPage = 1;
      go("lp");
    })
  );
  $("refreshButton").addEventListener("click", () => loadPage(state.page).catch((e) => toast(e.message)));
  $("overviewRefresh").addEventListener("click", () => loadOverview().catch((e) => toast(e.message)));
  const workflowCards = $("workflowCards");
  workflowCards.addEventListener("click", (event) => {
    const card = event.target.closest("[data-workflow-stage]");
    if (!card) return;
    state.workflowStageFilter = card.dataset.workflowStage;
    state.workflowRoleFilter = null;
    state.attentionOnly = false;
    state.registerPage = 1;
    clearRegisterFilters();
    go("register");
  });
  $("workflowRefresh").addEventListener("click", () => loadWorkflow().catch((e) => toast(e.message)));
  $("lpRefresh").addEventListener("click", () => { state.lpPage = 1; loadLPCirculation().catch((e) => toast(e.message)); });
  $("contractRefresh").addEventListener("click", () => { state.contractPage = 1; loadContractLifecycle().catch((e) => toast(e.message)); });
  $("activityRefresh").addEventListener("click", () => { state.activityPage = 1; loadActivity().catch((e) => toast(e.message)); });
  $("activitySearch").addEventListener("input", () => {
    state.activityQuery = $("activitySearch").value.trim();
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => { state.activityPage = 1; loadActivity().catch((e) => toast(e.message)); }, 300);
  });
  $("activityEntityFilter").addEventListener("change", () => {
    state.activityEntity = $("activityEntityFilter").value;
    state.activityPage = 1;
    loadActivity().catch((e) => toast(e.message));
  });
  $("activityReset").addEventListener("click", () => {
    $("activitySearch").value = "";
    $("activityEntityFilter").value = "";
    state.activityQuery = "";
    state.activityEntity = "";
    state.activityPage = 1;
    loadActivity().catch((e) => toast(e.message));
  });
  $("lpSearch").addEventListener("input", () => {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => { state.lpPage = 1; loadLPCirculation().catch((e) => toast(e.message)); }, 300);
  });
  $("lpStageFilter").addEventListener("change", () => { state.lpPage = 1; loadLPCirculation().catch((e) => toast(e.message)); });
  $("lpReset").addEventListener("click", () => {
    $("lpSearch").value = ""; $("lpStageFilter").value = ""; state.lpPage = 1;
    loadLPCirculation().catch((e) => toast(e.message));
  });
  document.querySelectorAll("[data-lp-stage]").forEach((el) => el.addEventListener("click", () => {
    $("lpStageFilter").value = el.dataset.lpStage || "";
    state.lpPage = 1;
    loadLPCirculation().catch((e) => toast(e.message));
  }));
  $("lpPrevious").addEventListener("click", () => { if (state.lpPage > 1) { state.lpPage--; loadLPCirculation().catch((e) => toast(e.message)); } });
  $("lpNext").addEventListener("click", () => { state.lpPage++; loadLPCirculation().catch((e) => toast(e.message)); });

  $("contractSearch").addEventListener("input", () => {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => { state.contractPage = 1; loadContractLifecycle().catch((e) => toast(e.message)); }, 300);
  });
  $("contractStatusFilter").addEventListener("change", () => { state.contractPage = 1; loadContractLifecycle().catch((e) => toast(e.message)); });
  $("contractReset").addEventListener("click", () => {
    $("contractSearch").value = ""; $("contractStatusFilter").value = ""; state.contractPage = 1;
    loadContractLifecycle().catch((e) => toast(e.message));
  });
  document.querySelectorAll("[data-contract-status]").forEach((el) => el.addEventListener("click", () => {
    $("contractStatusFilter").value = el.dataset.contractStatus || "";
    $("contractSearch").value = "";
    state.contractPage = 1;
    go("contracts");
  }));
  $("contractPrevious").addEventListener("click", () => { if (state.contractPage > 1) { state.contractPage--; loadContractLifecycle().catch((e) => toast(e.message)); } });
  $("contractNext").addEventListener("click", () => { state.contractPage++; loadContractLifecycle().catch((e) => toast(e.message)); });


  $("refreshHistoryButton").addEventListener("click", () => { state.historyPage = 1; loadImportHistory().catch((e) => toast(e.message)); });
  ["newRequestButton", "createRequestButton"].forEach((id) => $(id).addEventListener("click", () => openForm("request").catch((e) => toast(e.message))));
  $("createKhsButton").addEventListener("click", () => openForm("khs").catch((e) => toast(e.message)));
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
  $("searchInput").addEventListener("input", () => {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => { state.registerPage = 1; loadRegister().catch((e) => toast(e.message)); }, 300);
  });
  $("activeRegisterFilters").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-clear-filter]");
    if (chip) clearOneRegisterFilter(chip.dataset.clearFilter);
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
  ["lpBody", "contractBody"].forEach((id) => $(id).addEventListener("click", (event) => {
    const button = event.target.closest("[data-view-khs]");
    if (button) openDetails(button.dataset.viewKhs);
  }));
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
  observeResponsiveTables();
  bind();
  const initial = window.location.hash.replace("#", "");
  go(["overview", "requests", "register", "lp", "contracts", "workflow", "imports", "activity"].indexOf(initial) >= 0 ? initial : "overview");
});
})();