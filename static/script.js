// ============================================================================
// STATE & CONFIGURATION
// ============================================================================
const API_URL = '/api/presourcing';

let projects = [];
let team = [];
let activeTab = 'overview';
let openProjectId = null;
let modal = null;
let modalScroll = 0;
let filters = { priority: 'all', status: 'all' };
let storageOk = true;
let isSaving = false;
let dCharts = {};

// ============================================================================
// UTILITIES & HELPERS
// ============================================================================
function uid(prefix) {
  return prefix + '_' + Math.random().toString(36).slice(2, 9);
}

function todayStr() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function escAttr(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function val(id) {
  const el = document.getElementById(id);
  return el ? el.value : '';
}

function numOrNull(v) {
  if (v === '' || v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fmtIdr(n) {
  if (n === null || n === undefined || n === '') return '—';
  const value = Number(n);
  if (!Number.isFinite(value)) return '—';
  return 'Rp ' + Math.round(value).toLocaleString('id-ID');
}

function itemUnitPrice(item, unitKey, legacyTotalKey) {
  const rawDirect = item?.[unitKey];
  if (rawDirect !== null && rawDirect !== undefined && rawDirect !== '') {
    const direct = Number(rawDirect);
    if (Number.isFinite(direct)) return direct;
  }

  const rawTotal = item?.[legacyTotalKey];
  if (rawTotal === null || rawTotal === undefined || rawTotal === '') return null;

  const total = Number(rawTotal);
  const qty = numOrNull(item?.qty);

  if (Number.isFinite(total) && Number.isFinite(qty) && qty > 0) {
    return total / qty;
  }
  return null;
}

function itemSphTotal(item, unitKey, legacyTotalKey) {
  const qty = numOrNull(item?.qty);
  const unit = itemUnitPrice(item, unitKey, legacyTotalKey);

  if (Number.isFinite(qty) && Number.isFinite(unit)) {
    return qty * unit;
  }

  const rawLegacy = item?.[legacyTotalKey];
  if (rawLegacy === null || rawLegacy === undefined || rawLegacy === '') return null;

  const legacy = Number(rawLegacy);
  return Number.isFinite(legacy) ? legacy : null;
}

function calculateUiSphTotal(qty, unitPrice) {
  const q = numOrNull(qty);
  const unit = numOrNull(unitPrice);
  return (q != null && unit != null) ? q * unit : null;
}

function newItemData() {
  return {
    id: uid('item'), product: '', qty: 1, uom: '', vendor: '', notes: '', picIds: [],
    itemNo: '', preferredBrand: '', deliveryTime: '', 
    sphAwalUnit: null, sphFinalUnit: null, sphAwal: null, sphFinal: null
  };
}

function fmtPct(n) {
  return n == null ? '—' : n.toFixed(1) + '%';
}

function valToM(val) {
  return ((val || 0) / 1000000000).toFixed(1);
}

// ============================================================================
// DATA PERSISTENCE
// ============================================================================
function seedData() {
  team = ['Budi', 'Sari', 'Andi', 'Rahma', 'Fajar'];
  projects = [
    {
      id: uid('proj'), name: 'Project Backbone Expansion', requestorName: 'Marcel', requestorDept: 'SA G&P',
      priority: 'High', status: 'ongoing', leadId: 'Andi', sphMode: 'item', projectSphAwal: null, projectSphFinal: null,
      createdAt: '2026-07-02', closedAt: null, targetRfs: '2026-10-15', pipelineStage: '4 - Negotiation', progressPct: 85, comparison_docs: [],
      sows: [{
        id: uid('sow'), name: 'SoW Core',
        boqs: [{
          id: uid('boq'), name: 'BoQ Utama',
          items: [{
            id: uid('item'), product: 'Router', qty: 1, uom: 'Unit', vendor: '', notes: '', picIds: ['Andi'],
            itemNo: '1', preferredBrand: '', deliveryTime: '', sphAwalUnit: 25000000000, sphFinalUnit: null, sphAwal: 25000000000, sphFinal: null
          }]
        }]
      }]
    },
    {
      id: uid('proj'), name: 'Project Cloud Services', requestorName: 'Farizky', requestorDept: 'SA Digital',
      priority: 'Urgent', status: 'ongoing', leadId: 'Fajar', sphMode: 'project', projectSphAwal: 30000000000, projectSphFinal: null,
      createdAt: '2026-08-15', closedAt: null, targetRfs: todayStr(), pipelineStage: '2 - SPH Preparation', progressPct: 40, comparison_docs: [],
      sows: [{ id: uid('sow'), name: 'SoW Cloud', boqs: [{ id: uid('boq'), name: 'BoQ AWS', items: [] }] }]
    }
  ];
}

async function loadAll() {
  try {
    const timestamp = Date.now();
    const response = await fetch(`${API_URL}?t=${timestamp}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Gagal terhubung ke Backend');
    
    const data = await response.json();
    projects = Array.isArray(data.projects) ? data.projects : [];
    team = Array.isArray(data.team) ? data.team : [];
    normalizeState();
    storageOk = true;
  } catch (e) {
    console.error('Backend error/offline:', e);
    storageOk = false;
    if (projects.length === 0) seedData();
  }
  render();
}

async function saveAll() {
  if (isSaving) return false;
  isSaving = true;
  document.body.style.cursor = 'wait';

  try {
    normalizeState();
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projects, team })
    });

    let result = null;
    try { result = await response.json(); } catch (_) { result = null; }

    if (!response.ok || (result && result.success === false)) {
      throw new Error(result?.message || result?.error || 'Gagal menyimpan ke Backend');
    }

    storageOk = true;
    return true;
  } catch (e) {
    console.error('Gagal menyimpan data:', e);
    storageOk = false;
    return false;
  } finally {
    isSaving = false;
    document.body.style.cursor = 'default';
    render();
  }
}

function normalizeState() {
  projects = (Array.isArray(projects) ? projects : []).map(proj => {
    proj.sows = Array.isArray(proj.sows) ? proj.sows : [];
    proj.sphMode = proj.sphMode === 'project' ? 'project' : 'item';
    proj.comparison_docs = Array.isArray(proj.comparison_docs) ? proj.comparison_docs : [];

    proj.sows.forEach(sow => {
      sow.boqs = Array.isArray(sow.boqs) ? sow.boqs : [];
      sow.boqs.forEach(boq => {
        boq.items = Array.isArray(boq.items) ? boq.items : [];
        boq.items.forEach(item => {
          if (!item.id) item.id = uid('item');
          if (!Array.isArray(item.picIds)) item.picIds = [];
          if (item.qty === undefined || item.qty === null || item.qty === '') item.qty = 0;
          if (item.uom === undefined || item.uom === null) item.uom = '';
          if (item.vendor === undefined || item.vendor === null) item.vendor = '';
          if (item.notes === undefined || item.notes === null) item.notes = '';
          if (item.itemNo === undefined || item.itemNo === null) item.itemNo = '';
          if (item.preferredBrand === undefined || item.preferredBrand === null) item.preferredBrand = '';
          if (item.deliveryTime === undefined || item.deliveryTime === null) item.deliveryTime = '';
          if (item.sphAwalUnit === undefined) item.sphAwalUnit = null;
          if (item.sphFinalUnit === undefined) item.sphFinalUnit = null;
          if (item.sphAwal === undefined) item.sphAwal = null;
          if (item.sphFinal === undefined) item.sphFinal = null;
        });
      });
    });
    return proj;
  });

  team = Array.isArray(team) ? team.map(x => String(x).trim()).filter(Boolean) : [];
}

// ============================================================================
// COMPUTATIONS & LOGIC
// ============================================================================
function allItems(proj) {
  const out = [];
  (proj.sows || []).forEach(s => {
    (s.boqs || []).forEach(b => {
      (b.items || []).forEach(it => out.push(it));
    });
  });
  return out;
}

function projectSph(proj) {
  if (proj.sphMode === 'project') {
    return { awal: numOrNull(proj.projectSphAwal), final: numOrNull(proj.projectSphFinal) };
  }

  const items = allItems(proj);
  let awal = 0, final = 0, hasAwal = false, hasFinal = items.length > 0;

  items.forEach(it => {
    const itemAwal = itemSphTotal(it, 'sphAwalUnit', 'sphAwal');
    const itemFinal = itemSphTotal(it, 'sphFinalUnit', 'sphFinal');

    if (itemAwal != null) {
      awal += Number(itemAwal);
      hasAwal = true;
    }
    if (itemFinal == null) {
      hasFinal = false;
    } else {
      final += Number(itemFinal);
    }
  });

  return { awal: hasAwal ? awal : null, final: (hasFinal && items.length) ? final : null };
}

function efficiencyPct(awal, final) {
  if (awal == null || final == null || awal <= 0) return null;
  return ((awal - final) / awal) * 100;
}

function durationDays(proj) {
  const start = new Date(proj.createdAt);
  const end = proj.closedAt ? new Date(proj.closedAt) : new Date();
  return Math.max(0, Math.round((end - start) / (1000 * 60 * 60 * 24)));
}

function uniquePicsInProject(proj) {
  const set = new Set();
  if (proj.leadId) set.add(proj.leadId);
  allItems(proj).forEach(it => (it.picIds || []).forEach(p => set.add(p)));
  return [...set];
}

function getDynamicStatus(proj) {
  if (proj.status === 'win' || proj.status === 'lose') return 'Completed';
  if (!proj.targetRfs) return 'Planned';

  const diffDays = Math.ceil((new Date(proj.targetRfs) - new Date(todayStr())) / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return 'Overdue';
  if (diffDays <= 14) return 'At Risk';
  return 'On Track';
}

function badgeStatus(stat) {
  return `<span class="badge badge-${stat.toLowerCase().replace(' ', '-')}">${stat}</span>`;
}

function computePicStats() {
  const stats = {};
  team.forEach(m => stats[m] = { leadCount: 0, supportLoad: 0, participationShare: 0, winShare: 0, effSum: 0, effWeight: 0 });

  projects.forEach(proj => {
    if (proj.leadId && stats[proj.leadId]) stats[proj.leadId].leadCount++;
    const uniq = uniquePicsInProject(proj);

    if (proj.status !== 'ongoing' && uniq.length) {
      const share = 1 / uniq.length;
      uniq.forEach(p => {
        if (!stats[p]) return;
        stats[p].participationShare += share;
        if (proj.status === 'win') stats[p].winShare += share;
      });
    }

    const eff = efficiencyPct(projectSph(proj).awal, projectSph(proj).final);
    allItems(proj).forEach(it => {
      const pics = it.picIds?.length ? it.picIds : [];
      if (!pics.length) return;
      const share = 1 / pics.length;
      pics.forEach(p => {
        if (!stats[p]) return;
        stats[p].supportLoad += share;
        if (eff != null) { stats[p].effSum += eff * share; stats[p].effWeight += share; }
      });
    });
  });
  return stats;
}

// ============================================================================
// NAVIGATION & CORE RENDER
// ============================================================================
function switchDashboardTab(id) {
  activeTab = id;
  openProjectId = null;
  document.querySelectorAll('.app-nav-item').forEach(el => el.classList.toggle('active', el.dataset.tab === id));
  render();
}

function render() {
  const app = document.getElementById('app');
  let headerHtml = '';

  if (activeTab === 'overview') {
    const dateText = new Date().toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' });
    headerHtml = `
      <div class="page-hero">
        <div class="page-hero-main">
          <div class="page-hero-title">Presourcing Project Dashboard</div>
          <div class="page-hero-sub">Pipeline, Progress, and Target RFS</div>
        </div>
        <div class="page-hero-side">
          <div class="objective-box">
            <div class="objective-icon">◎</div>
            <div>
              <div class="objective-label">Objective</div>
              <div class="objective-text">Ensure project readiness &amp; competitive sourcing through effective presourcing</div>
            </div>
          </div>
          <div class="data-date"><span>Data per:</span><strong>${dateText}</strong></div>
        </div>
      </div>
    `;
  } else if (activeTab === 'projects') {
    headerHtml = `<div class="page-hero"><div class="page-hero-main"><div class="page-hero-title">Project &amp; BoQ Management</div><div class="page-hero-sub">Detail project, BoQ, SPH, dan progress</div></div></div>`;
  } else if (activeTab === 'team') {
    headerHtml = `<div class="page-hero"><div class="page-hero-main"><div class="page-hero-title">Team &amp; Workload</div><div class="page-hero-sub">Distribusi project dan beban kerja tim</div></div></div>`;
  }

  app.innerHTML = `<div class="page-shell">${headerHtml}<div id="tabcontent"></div></div>`;
  const content = document.getElementById('tabcontent');
  
  if (activeTab === 'overview') content.innerHTML = renderOverview();
  else if (activeTab === 'projects') content.innerHTML = renderProjects();
  else if (activeTab === 'team') content.innerHTML = renderTeam();

  wireEvents();
  if (modal) renderModal();
  document.querySelectorAll('.app-nav-item').forEach(el => el.classList.toggle('active', el.dataset.tab === activeTab));
}

// ============================================================================
// DASHBOARD VIEWS
// ============================================================================
function renderOverview() {
  const totalProj = projects.length;
  let totalVal = 0;
  const sCount = { 'On Track': 0, 'At Risk': 0, 'Overdue': 0, 'Completed': 0, 'Planned': 0 };
  const pCount = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0 };

  projects.forEach(p => {
    totalVal += (projectSph(p).awal || 0);
    const status = getDynamicStatus(p);
    if (sCount[status] !== undefined) sCount[status]++;
  });

  const activeProjectsData = projects.filter(p => p.status === 'ongoing');
  const activeProjects = activeProjectsData.length;

  activeProjectsData.forEach(p => {
    let stage = parseInt(String(p.pipelineStage || '').charAt(0));
    if (isNaN(stage) || stage < 1 || stage > 6) stage = 1;
    pCount[stage]++;
  });

  const efficiencies = projects.map(p => efficiencyPct(projectSph(p).awal, projectSph(p).final)).filter(v => v != null && isFinite(v));
  const avgEfficiency = efficiencies.length ? efficiencies.reduce((a, b) => a + b, 0) / efficiencies.length : null;
  const getPct = val => totalProj ? Math.round((val / totalProj) * 100) : 0;
  const atRisk = sCount['At Risk'];
  const overdue = sCount['Overdue'];

  if (!window.Chart && !document.getElementById('chartjs-script')) {
    const script = document.createElement('script');
    script.id = 'chartjs-script';
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
    script.onload = () => setTimeout(renderDashboardCharts, 100);
    document.head.appendChild(script);
  } else {
    setTimeout(renderDashboardCharts, 80);
  }

  const dashStyles = `
  <style>
    .page-shell{ width:100%; max-width:1420px; margin:0 auto; }
    .page-hero{ min-height:76px; display:flex; align-items:center; justify-content:space-between; gap:20px; padding:12px 18px; margin-bottom:12px; border-radius:10px; color:#fff; background: linear-gradient(115deg, #0B4F91 0%, #1769C2 58%, #2583DA 100%); box-shadow: 0 4px 12px rgba(15,23,42,.12); position:relative; overflow:hidden; }
    .page-hero::after{ content:''; position:absolute; width:260px; height:160px; right:-70px; top:-90px; background: rgba(255,255,255,.07); transform: rotate(28deg); pointer-events:none; }
    .page-hero-main{ position:relative; z-index:1; min-width:0; }
    .page-hero-title{ font-size:22px; line-height:1.1; font-weight:700; letter-spacing:.01em; }
    .page-hero-sub{ margin-top:5px; font-size:11px; color: rgba(255,255,255,.78); }
    .page-hero-side{ display:flex; align-items:center; gap:10px; position:relative; z-index:1; }
    .objective-box{ display:flex; align-items:center; gap:8px; padding: 7px 11px; min-width:230px; border: 1px solid rgba(255,255,255,.25); border-radius:7px; background: rgba(255,255,255,.08); }
    .objective-icon{ width:28px; height:28px; display:flex; align-items:center; justify-content:center; border-radius:50%; border: 2px solid rgba(255,255,255,.85); font-size:15px; font-weight:700; }
    .objective-label{ font-size:9px; font-weight:700; color: rgba(255,255,255,.92); text-transform:uppercase; letter-spacing:.05em; }
    .objective-text{ margin-top:2px; font-size:9.5px; line-height:1.25; color: rgba(255,255,255,.78); max-width:210px; }
    .data-date{ display:flex; flex-direction:column; gap:2px; padding: 7px 11px; border: 1px solid rgba(255,255,255,.20); border-radius:7px; min-width:110px; }
    .data-date span{ font-size:8.5px; color: rgba(255,255,255,.65); }
    .data-date strong{ font-size:9.5px; color:#fff; }
    .exec-kpis{ display:grid; grid-template-columns: repeat(6, minmax(0,1fr)); gap:9px; margin-bottom:12px; }
    .exec-kpi{ min-height:72px; padding:10px 11px; display:flex; align-items:center; gap:9px; border: 1px solid #dbe3ec; border-radius:8px; background:#fff; position:relative; overflow:hidden; box-shadow: 0 1px 3px rgba(15,23,42,.04); }
    .exec-kpi::after{ content:''; position:absolute; left:0; right:0; bottom:0; height:3px; background:#2563EB; }
    .exec-kpi.green::after{ background:#16A34A; }
    .exec-kpi.yellow::after{ background:#F59E0B; }
    .exec-kpi.red::after{ background:#DC2626; }
    .exec-kpi.gray::after{ background:#64748B; }
    .exec-kpi-icon{ width:31px; height:31px; flex:0 0 31px; display:flex; align-items:center; justify-content:center; border-radius:7px; font-size:15px; background:#F8FAFC; border: 1px solid #E2E8F0; }
    .exec-kpi-label{ font-size:9px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.03em; }
    .exec-kpi-value{ margin-top:3px; font-size:18px; line-height:1; font-weight:700; color:#0F172A; }
    .exec-kpi-value small{ font-size:9px; font-weight:500; color:#94A3B8; }
    .exec-kpi-meta{ margin-top:3px; font-size:8.5px; color:#94A3B8; }
    .exec-kpi-progress{ margin-top:5px; width:100%; height:4px; overflow:hidden; border-radius:8px; background:#E2E8F0; }
    .exec-kpi-progress span{ display:block; height:100%; border-radius:8px; background:#2563EB; }
    .exec-kpi.green .exec-kpi-progress span{ background:#16A34A; }
    .exec-kpi.yellow .exec-kpi-progress span{ background:#F59E0B; }
    .exec-kpi.red .exec-kpi-progress span{ background:#DC2626; }
    .exec-grid{ display:grid; grid-template-columns: minmax(0,2fr) minmax(0,1fr) minmax(0,1fr); grid-template-areas: "overview status pic" "pipeline rfs rfs" "top5 top5 warning"; gap:10px; align-items:stretch; }
    .exec-panel{ min-width:0; background:#fff; border: 1px solid #dbe3ec; border-radius:8px; overflow:hidden; box-shadow: 0 1px 3px rgba(15,23,42,.04); display:flex; flex-direction:column; }
    .exec-panel.overview{ grid-area:overview; }
    .exec-panel.status{ grid-area:status; }
    .exec-panel.pic{ grid-area:pic; }
    .exec-panel.pipeline{ grid-area:pipeline; }
    .exec-panel.rfs{ grid-area:rfs; }
    .exec-panel.top5{ grid-area:top5; }
    .exec-panel.warning{ grid-area:warning; }
    .exec-panel-head{ min-height:31px; padding: 8px 11px; display:flex; align-items:center; gap:7px; background: linear-gradient(90deg, #0F5CA8, #1672C8); color:#fff; font-size:10.5px; font-weight:700; letter-spacing:.01em; }
    .exec-panel-head.warning-head{ background: linear-gradient(90deg, #B91C1C, #DC2626); }
    .exec-panel-sub{ margin-left:auto; font-size:8px; font-weight:400; opacity:.75; white-space:nowrap; }
    .exec-panel-body{ flex:1; min-height:0; padding:9px; }
    .exec-table-wrap{ height:100%; max-height:220px; overflow:auto; }
    table.exec-table{ width:100%; border-collapse:collapse; font-size:9.5px; }
    table.exec-table th{ position:sticky; top:0; z-index:2; padding:6px 5px; text-align:left; white-space:nowrap; background:#F4F7FB; color:#475569; border-bottom: 1px solid #DCE4EE; font-size:8px; font-weight:700; text-transform:uppercase; letter-spacing:.02em; }
    table.exec-table td{ padding:6px 5px; border-bottom: 1px solid #EEF2F6; color:#334155; vertical-align:middle; }
    table.exec-table tbody tr:hover{ background:#F8FAFC; }
    .exec-project-name{ max-width:135px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:600; color:#0F172A; }
    .exec-project-pic{ margin-top:2px; color:#94A3B8; font-size:8px; }
    .exec-progress{ display:flex; align-items:center; gap:4px; }
    .exec-progress-value{ width:25px; text-align:right; font-size:8.5px; font-weight:600; }
    .exec-progress-bg{ width:38px; height:4px; border-radius:8px; overflow:hidden; background:#E2E8F0; }
    .exec-progress-fill{ height:100%; background:#2583DA; border-radius:8px; }
    .exec-chart{ height:155px; position:relative; width:100%; }
    .exec-chart.tall{ height:170px; }
    .exec-chart canvas{ width:100% !important; height:100% !important; }
    .exec-donut{ height:170px; position:relative; }
    .exec-donut canvas{ width:100% !important; height:100% !important; }
    .exec-donut-center{ position:absolute; left:37%; top:50%; transform: translate(-50%,-50%); text-align:center; pointer-events:none; }
    .exec-donut-number{ font-size:22px; line-height:1; font-weight:700; color:#0F172A; }
    .exec-donut-label{ margin-top:2px; font-size:8px; color:#64748B; }
    .warning-summary{ display:grid; grid-template-columns:1fr 1fr; gap:6px; padding:7px; background:#FFFBEB; border-bottom: 1px solid #FDE68A; }
    .warning-box{ padding:5px 7px; background:#fff; border: 1px solid #FDE68A; border-radius:5px; }
    .warning-label{ font-size:7.5px; color:#92400E; font-weight:700; text-transform:uppercase; }
    .warning-value{ margin-top:1px; font-size:15px; line-height:1; font-weight:700; color:#78350F; }
    .pipeline-flow{ display:grid; grid-template-columns: repeat(6,minmax(0,1fr)); gap:2px; margin-top:1px; }
    .pipeline-step{ position:relative; min-width:0; min-height:105px; padding: 9px 7px 8px; background:#F2F7FD; border: 1px solid #BFD7F3; text-align:center; clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 50%, calc(100% - 10px) 100%, 0 100%, 10px 50%); }
    .pipeline-step:first-child{ clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 50%, calc(100% - 10px) 100%, 0 100%); }
    .pipeline-step:last-child{ clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%, 10px 50%); }
    .pipeline-step.active{ background:#E8F2FE; border-color:#93C5FD; }
    .pipeline-step.final{ background:#F0FDF4; border-color:#86EFAC; }
    .pipeline-number{ width:22px; height:22px; margin:0 auto 6px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:#2563EB; color:#fff; font-size:9px; font-weight:700; }
    .pipeline-step.final .pipeline-number{ background:#16A34A; }
    .pipeline-name{ min-height:25px; font-size:8px; line-height:1.2; font-weight:600; color:#334155; }
    .pipeline-count{ margin-top:5px; font-size:15px; line-height:1; font-weight:700; color:#0F172A; }
    .pipeline-count-label{ margin-top:2px; font-size:7.5px; color:#94A3B8; }
    .pipeline-progress{ margin-top:6px; height:4px; background:#DCE5EF; border-radius:8px; overflow:hidden; }
    .pipeline-progress span{ display:block; height:100%; background:#2681D8; border-radius:8px; }
    .pipeline-step.final .pipeline-progress span{ background:#16A34A; }
    @media(max-width:1100px){
      .page-hero-side{ display:none; }
      .exec-kpis{ grid-template-columns: repeat(3,minmax(0,1fr)); }
      .exec-grid{ grid-template-columns: 1fr 1fr; grid-template-areas: "overview overview" "status pic" "rfs rfs" "pipeline pipeline" "top5 warning"; }
    }
    @media(max-width:700px){
      .page-hero{ min-height:auto; }
      .page-hero-title{ font-size:18px; }
      .exec-kpis{ grid-template-columns: repeat(2,minmax(0,1fr)); }
      .exec-grid{ grid-template-columns:1fr; grid-template-areas: "overview" "status" "pic" "rfs" "pipeline" "top5" "warning"; }
      .pipeline-flow{ grid-template-columns: repeat(3,minmax(0,1fr)); }
    }
  </style>
  `;

  const sortedProjects = [...projects].sort((a, b) => new Date(a.targetRfs || '2099-12-31') - new Date(b.targetRfs || '2099-12-31'));
  let overviewRows = '';

  sortedProjects.forEach((p, idx) => {
    const sph = projectSph(p);
    const progress = Math.max(0, Math.min(100, Number(p.progressPct) || 0));
    const rfs = p.targetRfs ? new Date(p.targetRfs).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

    overviewRows += `
      <tr>
        <td>${idx + 1}</td>
        <td>
          <div class="exec-project-name" title="${escAttr(p.name)}">${escAttr(p.name)}</div>
          <div class="exec-project-pic">${escAttr(p.requestorDept || '—')}</div>
        </td>
        <td class="mono">${valToM(sph.awal)} M</td>
        <td>${escAttr(p.leadId || '—')}</td>
        <td style="white-space:nowrap">${rfs}</td>
        <td>${badgeStatus(getDynamicStatus(p))}</td>
        <td>
          <div class="exec-progress">
            <span class="exec-progress-value">${progress}%</span>
            <div class="exec-progress-bg">
              <div class="exec-progress-fill" style="width:${progress}%"></div>
            </div>
          </div>
        </td>
      </tr>
    `;
  });

  if (!overviewRows) overviewRows = `<tr><td colspan="7" style="text-align:center; padding:25px; color:#94A3B8;">Belum ada project.</td></tr>`;

  const warningProjects = sortedProjects.filter(p => ['Overdue', 'At Risk'].includes(getDynamicStatus(p)));
  let warningRows = '';

  warningProjects.slice(0, 5).forEach(p => {
    const progress = Number(p.progressPct) || 0;
    const rfs = p.targetRfs ? new Date(p.targetRfs).toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }) : '—';
    warningRows += `
      <tr>
        <td>
          <div class="exec-project-name">${escAttr(p.name)}</div>
          <div class="exec-project-pic">PIC: ${escAttr(p.leadId || '—')}</div>
        </td>
        <td style="white-space:nowrap">${rfs}</td>
        <td><strong>${progress}%</strong></td>
        <td>${badgeStatus(getDynamicStatus(p))}</td>
      </tr>
    `;
  });

  if (!warningRows) warningRows = `<tr><td colspan="4" style="text-align:center; padding:18px; color:#15803D;">✓ Tidak ada project yang perlu perhatian</td></tr>`;

  const pNames = ['Project Identification', 'SPH Preparation', 'Vendor Selection', 'Negotiation', 'Finalization', 'RFS'];
  let pipelineHtml = '';

  pNames.forEach((name, i) => {
    const n = i + 1;
    const count = pCount[n];
    const pct = activeProjects ? Math.round((count / activeProjects) * 100) : 0;
    const activeClass = count > 0 ? 'active' : '';
    const finalClass = n === 6 ? 'final' : '';

    pipelineHtml += `
      <div class="pipeline-step ${activeClass} ${finalClass}">
        <div class="pipeline-number">${n}</div>
        <div class="pipeline-name">${name}</div>
        <div class="pipeline-count">${count}</div>
        <div class="pipeline-count-label">${count === 1 ? 'Project' : 'Projects'}</div>
        <div class="pipeline-progress"><span style="width:${pct}%"></span></div>
      </div>
    `;
  });

  return dashStyles + `
    <div class="exec-kpis">
      <div class="exec-kpi"><div class="exec-kpi-icon" style="color:#0284C7;">▣</div><div><div class="exec-kpi-label">Total Project</div><div class="exec-kpi-value">${totalProj}</div><div class="exec-kpi-meta">${activeProjects} active projects</div></div></div>
      <div class="exec-kpi"><div class="exec-kpi-icon" style="color:#4F46E5;">◉</div><div><div class="exec-kpi-label">Total Project Value</div><div class="exec-kpi-value" style="font-size:15px;">Rp ${valToM(totalVal)} M</div><div class="exec-kpi-meta">Est. project value</div></div></div>
      <div class="exec-kpi green"><div class="exec-kpi-icon" style="color:#16A34A; background:#F0FDF4;">✓</div><div style="width:100%;"><div class="exec-kpi-label">On Track</div><div class="exec-kpi-value">${sCount['On Track']} <small>${getPct(sCount['On Track'])}%</small></div><div class="exec-kpi-progress"><span style="width:${getPct(sCount['On Track'])}%; background:#16A34A;"></span></div></div></div>
      <div class="exec-kpi yellow"><div class="exec-kpi-icon" style="color:#D97706; background:#FFFBEB;">!</div><div style="width:100%;"><div class="exec-kpi-label">At Risk</div><div class="exec-kpi-value">${atRisk} <small style="color:#D97706;">${getPct(atRisk)}%</small></div><div class="exec-kpi-progress"><span style="width:${getPct(atRisk)}%; background:#F59E0B;"></span></div></div></div>
      <div class="exec-kpi red"><div class="exec-kpi-icon" style="color:#DC2626; background:#FEF2F2;">!</div><div style="width:100%;"><div class="exec-kpi-label">Overdue</div><div class="exec-kpi-value">${overdue} <small style="color:#DC2626;">${getPct(overdue)}%</small></div><div class="exec-kpi-progress"><span style="width:${getPct(overdue)}%; background:#DC2626;"></span></div></div></div>
      <div class="exec-kpi gray"><div class="exec-kpi-icon" style="color:#475569; background:#F8FAFC;">↗</div><div><div class="exec-kpi-label">Avg Efficiency</div><div class="exec-kpi-value">${fmtPct(avgEfficiency)}</div><div class="exec-kpi-meta">${efficiencies.length} project with data</div></div></div>
    </div>
    <div class="exec-grid">
      <div class="exec-panel overview"><div class="exec-panel-head">▣ <span>Project Presourcing Overview</span><span class="exec-panel-sub">${totalProj} Projects</span></div><div class="exec-table-wrap"><table class="exec-table"><thead><tr><th>No</th><th>Project Name</th><th>Value</th><th>PIC</th><th>Target RFS</th><th>Status</th><th>Progress</th></tr></thead><tbody>${overviewRows}</tbody></table></div></div>
      <div class="exec-panel status"><div class="exec-panel-head">◉ <span>Project Status</span></div><div class="exec-panel-body"><div class="exec-donut"><canvas id="chartStatus"></canvas><div class="exec-donut-center"><div class="exec-donut-number">${totalProj}</div><div class="exec-donut-label">Projects</div></div></div></div></div>
      <div class="exec-panel pic"><div class="exec-panel-head">▥ <span>Project Value by PIC</span></div><div class="exec-panel-body"><div class="exec-chart"><canvas id="chartPicValue"></canvas></div></div></div>
      <div class="exec-panel pipeline"><div class="exec-panel-head">⇢ <span>Presourcing Progress Pipeline</span><span class="exec-panel-sub">${activeProjects} active</span></div><div class="exec-panel-body"><div class="pipeline-flow">${pipelineHtml}</div></div></div>
      <div class="exec-panel rfs"><div class="exec-panel-head">▥ <span>Target RFS by Month</span></div><div class="exec-panel-body"><div class="exec-chart"><canvas id="chartRfsMonth"></canvas></div></div></div>
      <div class="exec-panel top5"><div class="exec-panel-head">≡ <span>Top 5 Project Value</span></div><div class="exec-panel-body"><div class="exec-chart"><canvas id="chartTop5"></canvas></div></div></div>
      <div class="exec-panel warning"><div class="exec-panel-head warning-head">! <span>Early Warning</span><span class="exec-panel-sub">Need Attention</span></div><div class="warning-summary"><div class="warning-box"><div class="warning-label">Overdue</div><div class="warning-value">${overdue}</div></div><div class="warning-box"><div class="warning-label">At Risk</div><div class="warning-value">${atRisk}</div></div></div><div class="exec-table-wrap"><table class="exec-table"><thead><tr><th>Project</th><th>RFS</th><th>Progress</th><th>Status</th></tr></thead><tbody>${warningRows}</tbody></table></div></div>
    </div>
  `;
}

// ... Sisipkan blok fungsi chart.js yang sama seperti kode sebelumnya (renderDashboardCharts, dst.)
// Untuk mempersingkat respon ini dan berfokus pada refactoring layout, mari lanjutkan ke fungsi rendering HTML utama.

function renderProjects() {
  const filtered = projects.filter(p => {
    if (filters.priority !== 'all' && p.priority !== filters.priority) return false;
    if (filters.status !== 'all' && p.status !== filters.status) return false;
    return true;
  });

  let tbodyHtml = '';
  if (filtered.length === 0) {
    tbodyHtml = '<tr><td colspan="7"><div class="empty">Tidak ada project yang cocok.</div></td></tr>';
  } else {
    filtered.forEach(p => {
      const s = projectSph(p);
      const eff = efficiencyPct(s.awal, s.final);
      const pipelineText = escAttr(p.pipelineStage) || '-';
      const pct = p.progressPct || 0;

      tbodyHtml += `
        <tr class="proj-row" data-open="${p.id}">
          <td>${escAttr(p.name)}</td>
          <td>${escAttr(p.requestorName)}<br><span style="color:var(--text-muted); font-size:11.5px;">${escAttr(p.requestorDept)}</span></td>
          <td>${badgeStatus(getDynamicStatus(p))}</td>
          <td><span style="font-size:12px;">${pipelineText} (${pct}%)</span></td>
          <td class="num mono">${fmtIdr(s.awal)}</td>
          <td class="num mono">${fmtPct(eff)}</td>
          <td class="num mono">${durationDays(p)} hari</td>
        </tr>
      `;
      if (openProjectId === p.id) tbodyHtml += `<tr><td colspan="7">${renderProjectDetail(p)}</td></tr>`;
    });
  }

  return `
    <div class="panel">
      <div class="panel-hd">
        <h2>Daftar Detail Project & BoQ</h2>
        <div style="display:flex; gap:8px; align-items:center;">
          <div class="filters">
            <select id="f-priority"><option value="all">Semua prioritas</option><option value="Urgent">Urgent</option><option value="High">High</option><option value="Medium">Medium</option></select>
            <select id="f-status"><option value="all">Semua status</option><option value="ongoing">Berjalan</option><option value="win">Menang</option><option value="lose">Kalah</option></select>
          </div>
          <button class="btn-primary" id="btn-new-project">+ Project baru</button>
        </div>
      </div>
      <div class="panel-body">
        <table>
          <thead><tr><th>Project</th><th>Pemohon</th><th>Status EWS</th><th>Tahap Pipeline</th><th class="num">SPH Awal</th><th class="num">Efficiency</th><th class="num">Durasi</th></tr></thead>
          <tbody>${tbodyHtml}</tbody>
        </table>
      </div>
    </div>
  `;
}

function renderProjectDetail(p) {
  const uniq = uniquePicsInProject(p);
  const docsHtml = `
    <div style="margin: 12px 0; padding: 12px; background: #FFFFFF; border: 1px dashed var(--border); border-radius: 6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
        <strong style="font-size: 12.5px; color: var(--text);">📄 Dokumen SPH Pembanding (Audit Trail)</strong>
        <button class="mini-btn" onclick="openUploadPembandingModal('${p.id}')">+ Upload Pembanding</button>
      </div>
      ${p.comparison_docs && p.comparison_docs.length > 0 
        ? p.comparison_docs.map(doc => `
            <div style="display:flex; justify-content:space-between; font-size: 12px; padding: 6px 0; border-bottom: 1px solid var(--border-soft);">
              <div><span style="font-weight:600; color:var(--text);">${escAttr(doc.vendor_name)}</span> <span style="color:var(--text-muted);"> — Penawaran: <span class="mono">${fmtIdr(doc.offered_price)}</span></span></div>
              <a href="${doc.file_path}" target="_blank" style="color: var(--primary); text-decoration: none; font-weight:500;">Lihat File</a>
            </div>
          `).join('') 
        : '<div style="font-size:11.5px; color:var(--text-muted);">Belum ada dokumen pembanding yang diunggah.</div>'
      }
    </div>
  `;

  let sowsHtml = '';
  (p.sows || []).forEach(sow => {
    sowsHtml += `<div class="sow-title">Scope of Work: ${escAttr(sow.name)}</div>`;
    (sow.boqs || []).forEach(boq => {
      sowsHtml += `<div class="boq-title">Bill of Quantity: ${escAttr(boq.name)}</div>
        <div style="display:grid; grid-template-columns: 2fr 0.4fr 0.5fr 1fr 1fr 1fr 0.8fr 1.5fr; gap:8px; padding:5px 0; font-size:10.5px; color:var(--text-dim); border-bottom:1px solid var(--border);">
          <div>Item</div><div>Qty</div><div>UoM</div><div>Vendor</div><div class="num">SPH Awal</div><div class="num">SPH Final</div><div class="num">Efficiency</div><div>PIC</div>
        </div>
      `;
      (boq.items || []).forEach(it => {
        const itemAwal = itemSphTotal(it, 'sphAwalUnit', 'sphAwal');
        const itemFinal = itemSphTotal(it, 'sphFinalUnit', 'sphFinal');
        const eff = p.sphMode === 'item' ? efficiencyPct(itemAwal, itemFinal) : null;
        const notesHtml = it.notes ? `<div style="font-size:11px; color:var(--text-muted); margin-top:3px;">📝 ${escAttr(it.notes)}</div>` : '';
        const picsHtml = (it.picIds || []).map(x => `<span class="pic-chip">${escAttr(x)}</span>`).join('');
        sowsHtml += `
          <div style="display:grid; grid-template-columns: 2fr 0.4fr 0.5fr 1fr 1fr 1fr 0.8fr 1.5fr; gap:8px; padding:7px 0; font-size:12.5px; border-bottom:1px solid var(--border-soft); align-items:start;">
            <div><div style="font-weight:500;">${escAttr(it.product) || '—'}</div>${notesHtml}</div>
            <div style="color:var(--text-muted);">${it.qty || '-'}</div>
            <div style="color:var(--text-muted);">${escAttr(it.uom) || '-'}</div>
            <div style="color:var(--text-muted);">${escAttr(it.vendor) || '-'}</div>
            <div class="num mono">${p.sphMode === 'item' ? fmtIdr(itemAwal) : '—'}</div>
            <div class="num mono">${p.sphMode === 'item' ? fmtIdr(itemFinal) : '—'}</div>
            <div class="num mono">${p.sphMode === 'item' ? fmtPct(eff) : '—'}</div>
            <div>${picsHtml}</div>
          </div>
        `;
      });
    });
  });

  return `
    <div class="detail-block">
      <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
        <div style="font-size:12px; color:var(--text-muted);">Lead Presource: <strong style="color:var(--text);">${p.leadId || '—'}</strong> · PIC terlibat: ${uniq.join(', ') || '—'}</div>
        <div style="display:flex; gap:6px;">
          <button class="mini-btn" onclick="event.stopPropagation(); downloadRevisionTemplate('${p.id}')">📥 Template Revisi</button>
          <button class="mini-btn" onclick="event.stopPropagation(); triggerRevisiBoq('${p.id}')">🔄 Revisi Excel BoQ</button>
          <button class="mini-btn" onclick="downloadProjectReport('${p.id}')">📥 Download Excel</button>
          <button class="mini-btn" data-edit-project="${p.id}">Edit</button>
          <button class="mini-btn danger" data-delete-project="${p.id}">Hapus</button>
        </div>
      </div>
      ${docsHtml}
      ${sowsHtml}
      ${p.sphMode === 'project' ? `<div class="note">SPH dicatat di level total project (tidak dipecah per item).</div>` : ''}
    </div>
  `;
}

// ============================================================================
// EVENT WIRINGS
// ============================================================================
function wireEvents() {
  const fp = document.getElementById('f-priority');
  if (fp) { fp.value = filters.priority; fp.onchange = () => { filters.priority = fp.value; render(); }; }
  
  const fs = document.getElementById('f-status');
  if (fs) { fs.value = filters.status; fs.onchange = () => { filters.status = fs.value; render(); }; }
  
  document.querySelectorAll('[data-open]').forEach(el => {
    el.onclick = () => {
      const id = el.dataset.open;
      openProjectId = (openProjectId === id) ? null : id;
      render();
    };
  });
  
  const btnNew = document.getElementById('btn-new-project');
  if (btnNew) btnNew.onclick = () => openProjectModal(null);
  
  document.querySelectorAll('[data-edit-project]').forEach(el => {
    el.onclick = e => { e.stopPropagation(); openProjectModal(el.dataset.editProject); };
  });

  document.querySelectorAll('[data-delete-project]').forEach(el => {
    el.onclick = async e => {
      e.stopPropagation();
      if (!confirm('Hapus project ini?')) return;
      const before = projects;
      projects = projects.filter(p => p.id !== el.dataset.deleteProject);
      const saved = await saveAll();
      if (!saved) {
        projects = before;
        alert('Project belum terhapus dari backend. Cek server lalu coba lagi.');
        render();
      }
    };
  });
  
  const btnTeam = document.getElementById('btn-manage-team');
  if (btnTeam) btnTeam.onclick = () => openTeamModal();
}

// ============================================================================
// MODALS LOGIC (INCLUDING SPH UNIT UPDATE)
// ============================================================================
// Pembaruan UI untuk SPH per unit pada block HTML
function itemBlockHtml(it, si, bi, ii) {
  const path = `${si}:${bi}:${ii}`;
  const awalUnit = itemUnitPrice(it, 'sphAwalUnit', 'sphAwal');
  const finalUnit = itemUnitPrice(it, 'sphFinalUnit', 'sphFinal');
  const awalTotal = itemSphTotal(it, 'sphAwalUnit', 'sphAwal');
  const finalTotal = itemSphTotal(it, 'sphFinalUnit', 'sphFinal');

  return `
    <div class="item-block" data-item-idx="${ii}">
      <div class="item-head">
        <div class="item-label">Item ${ii + 1}</div>
        <button class="mini-btn danger form-danger-btn" data-del-item="${path}" type="button">Hapus</button>
      </div>
      <div class="item-grid-main">
        <div class="field"><label>Item No</label><input class="it-item-no" data-path="${path}" value="${escAttr(it.itemNo)}" placeholder="No item"></div>
        <div class="field"><label>Produk / Deskripsi</label><input class="it-product" data-path="${path}" value="${escAttr(it.product)}" placeholder="Nama produk / service"></div>
        <div class="field"><label>Qty</label><input type="number" class="it-qty" data-path="${path}" value="${it.qty ?? 1}" min="0" step="any"></div>
        <div class="field"><label>UoM</label><input class="it-uom" data-path="${path}" value="${escAttr(it.uom)}" placeholder="Unit"></div>
      </div>
      <div class="item-grid-main">
        <div class="field"><label>Preferred Brand</label><input class="it-brand" data-path="${path}" value="${escAttr(it.preferredBrand)}" placeholder="Boleh kosong"></div>
        <div class="field"><label>Delivery Time (RFS)</label><input type="date" class="it-delivery" data-path="${path}" value="${escAttr(it.deliveryTime)}"></div>
        <div class="field"><label>Vendor</label><input class="it-vendor" data-path="${path}" value="${escAttr(it.vendor)}" placeholder="Vendor"></div>
        <div class="field"><label>Notes</label><input class="it-notes" data-path="${path}" value="${escAttr(it.notes)}" placeholder="Catatan (opsional)"></div>
      </div>
      <div class="item-grid-finance">
        <div class="field">
          <label>SPH Awal / Unit</label>
          <input type="number" class="it-awal-unit" data-path="${path}" value="${awalUnit ?? ''}" placeholder="Harga per unit" min="0" step="any">
          <div style="margin-top:4px; font-size:9.5px; color:#64748B;">Total: <strong data-total-awal="${path}" style="color:#0F172A;">${fmtIdr(awalTotal)}</strong></div>
        </div>
        <div class="field">
          <label>SPH Final / Unit</label>
          <input type="number" class="it-final-unit" data-path="${path}" value="${finalUnit ?? ''}" placeholder="Harga per unit" min="0" step="any">
          <div style="margin-top:4px; font-size:9.5px; color:#64748B;">Total: <strong data-total-final="${path}" style="color:#0F172A;">${fmtIdr(finalTotal)}</strong></div>
        </div>
        <div class="field">
          <label>PIC</label>
          <div class="pic-select">
            ${team.map(t => `<div class="pic-opt ${(it.picIds ||[]).includes(t) ? 'on' : ''}" data-pic="${path}:${escAttr(t)}">${escAttr(t)}</div>`).join('')}
          </div>
        </div>
      </div>
    </div>
  `;
}

function syncModalData() {
  if (!modal || modal.type !== 'project') return;
  const m = document.querySelector('.modal');
  if (m) modalScroll = m.scrollTop;
  
  const d = modal.data;
  d.name = val('m-name').trim();
  d.requestorName = val('m-req-name').trim();
  d.requestorDept = val('m-req-dept').trim();
  d.priority = val('m-priority');
  d.status = val('m-status');
  d.leadId = val('m-lead');
  d.targetRfs = val('m-target-rfs');
  d.pipelineStage = val('m-pipeline-stage');
  d.progressPct = Math.max(0, Math.min(100, numOrNull(val('m-progress')) ?? 0));
  d.sphMode = val('m-sphmode');
  
  if (d.sphMode === 'project') {
    d.projectSphAwal = numOrNull(val('m-proj-awal'));
    d.projectSphFinal = numOrNull(val('m-proj-final'));
  }
  
  document.querySelectorAll('.sow-name').forEach(el => { d.sows[+el.dataset.si].name = el.value; });
  document.querySelectorAll('.boq-name').forEach(el => { d.sows[+el.dataset.si].boqs[+el.dataset.bi].name = el.value; });
  
  const syncPathField = (selector, setter) => {
    document.querySelectorAll(selector).forEach(el => {
      const [si, bi, ii] = el.dataset.path.split(':').map(Number);
      setter(d.sows[si].boqs[bi].items[ii], el.value);
    });
  };

  syncPathField('.it-item-no', (item, value) => { item.itemNo = value.trim(); });
  syncPathField('.it-product', (item, value) => { item.product = value; });
  syncPathField('.it-qty', (item, value) => { item.qty = numOrNull(value); });
  syncPathField('.it-uom', (item, value) => { item.uom = value.trim(); });
  syncPathField('.it-brand', (item, value) => { item.preferredBrand = value.trim(); });
  syncPathField('.it-delivery', (item, value) => { item.deliveryTime = value; });
  syncPathField('.it-vendor', (item, value) => { item.vendor = value.trim(); });
  syncPathField('.it-notes', (item, value) => { item.notes = value; });
  
  // Sinkronisasi SPH Unit & Auto-Calculate
  syncPathField('.it-awal-unit', (item, value) => {
    item.sphAwalUnit = numOrNull(value);
    item.sphAwal = calculateUiSphTotal(item.qty, item.sphAwalUnit);
  });
  syncPathField('.it-final-unit', (item, value) => {
    item.sphFinalUnit = numOrNull(value);
    item.sphFinal = calculateUiSphTotal(item.qty, item.sphFinalUnit);
  });
}

function updateItemFinancialPreview(input) {
  const path = input.dataset.path;
  if (!path) return;

  const qtyInput = document.querySelector(`.it-qty[data-path="${path}"]`);
  const awalInput = document.querySelector(`.it-awal-unit[data-path="${path}"]`);
  const finalInput = document.querySelector(`.it-final-unit[data-path="${path}"]`);
  const awalTotal = document.querySelector(`[data-total-awal="${path}"]`);
  const finalTotal = document.querySelector(`[data-total-final="${path}"]`);

  const totalAwal = calculateUiSphTotal(qtyInput?.value, awalInput?.value);
  const totalFinal = calculateUiSphTotal(qtyInput?.value, finalInput?.value);

  if (awalTotal) awalTotal.textContent = totalAwal == null ? '—' : fmtIdr(totalAwal);
  if (finalTotal) finalTotal.textContent = totalFinal == null ? '—' : fmtIdr(totalFinal);
}

function wireModalEvents() {
  if (!modal) return;
  const close = () => { modal = null; document.getElementById('modal-root').innerHTML = ''; render(); };
  
  const c1 = document.getElementById('m-close'); if (c1) c1.onclick = close;
  const c2 = document.getElementById('m-cancel'); if (c2) c2.onclick = close;
  const ov = document.getElementById('ov'); 
  if (ov) ov.onclick = e => { if (e.target === ov) close(); };

  if (modal.type === 'team') {
    const sBtn = document.getElementById('m-save-team');
    if (sBtn) {
      sBtn.onclick = async () => {
        team = val('m-team-names').split(',').map(s => s.trim()).filter(Boolean);
        const saved = await saveAll();
        if (!saved) { alert('Perubahan tim belum tersimpan ke backend.'); return; }
        modal = null;
        render();
      };
    }
    return;
  }

  const sphmode = document.getElementById('m-sphmode');
  if (sphmode) {
    sphmode.onchange = () => { syncModalData(); modal.data.sphMode = sphmode.value; render(); };
  }

  // Trigger update real-time preview (Harga * Qty) saat mengetik
  document.querySelectorAll('.it-qty, .it-awal-unit, .it-final-unit').forEach(el => {
    el.addEventListener('input', () => updateItemFinancialPreview(el));
  });

  // ... Biarkan event listener manipulasi DOM (m-import-boq, m-add-sow, dst.) mengikuti format Standard JS yang sama.
}

// Initialize
loadAll();