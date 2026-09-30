// ---------- storage keys & setup ----------
const API_URL = '/api/presourcing';

let projects = [];
let team = [];
let activeTab = 'overview';
let openProjectId = null;
let modal = null; 
let modalScroll = 0;
let filters = { priority:'all', status:'all' };
let storageOk = true;
let isSaving = false; 

function uid(p){ return p + '_' + Math.random().toString(36).slice(2,9); }
function todayStr(){ return new Date().toISOString().slice(0,10); }

// ---------- Fungsi Keamanan (XSS Protection) ----------
function escAttr(s){ 
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

// ---------- seed data (Fallback) ----------
function seedData(){
  team = ['Budi','Sari','Andi','Rahma','Fajar'];
  projects = [
    {
      id: uid('proj'), name:'Project Backbone Expansion',
      requestorName:'Marcel', requestorDept:'SA G&P',
      priority:'High', status:'ongoing', leadId:'Andi',
      sphMode:'item', projectSphAwal:null, projectSphFinal:null,
      createdAt:'2026-07-02', closedAt:null, targetRfs:'2026-10-15',
      pipelineStage:'4 - Negotiation', progressPct:85,
      comparison_docs: [],
      sows:[{ id:uid('sow'), name:'SoW Core', boqs:[{ id:uid('boq'), name:'BoQ Utama', items:[ {id:uid('item'), product:'Router', picIds:['Andi'], sphAwal:25000000000, sphFinal:null} ] }] }]
    },
    {
      id: uid('proj'), name:'Project Cloud Services',
      requestorName:'Farizky', requestorDept:'SA Digital',
      priority:'Urgent', status:'ongoing', leadId:'Fajar',
      sphMode:'project', projectSphAwal:30000000000, projectSphFinal:null,
      createdAt:'2026-08-15', closedAt:null, targetRfs: todayStr(), 
      pipelineStage:'2 - SPH Preparation', progressPct:40,
      comparison_docs: [],
      sows:[{ id:uid('sow'), name:'SoW Cloud', boqs:[{ id:uid('boq'), name:'BoQ AWS', items:[] }] }]
    }
  ];
}

// ---------- persistence ----------
async function loadAll(){
  try {
    const timestamp = new Date().getTime();
    const response = await fetch(`${API_URL}?t=${timestamp}`);
    if (!response.ok) throw new Error("Gagal terhubung ke Backend");
    
    const data = await response.json();
    if (!data.projects || !data.team || (data.projects.length === 0 && data.team.length === 0)) {
      seedData(); await saveAll(); 
    } else {
      projects = data.projects; team = data.team;
    }
    storageOk = true;
  } catch(e) {
    console.error("Backend error/offline:", e);
    storageOk = false;
    if(projects.length === 0) seedData();
  }
  render();
}

async function saveAll(){
  if (isSaving) return;
  isSaving = true;
  document.body.style.cursor = 'wait';

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projects: projects, team: team })
    });
    if (!response.ok) throw new Error("Gagal menyimpan ke Backend");
    storageOk = true;
  } catch(e) {
    console.error("Gagal menyimpan data:", e);
    storageOk = false; 
  } finally {
    isSaving = false; document.body.style.cursor = 'default';
  }
  render(); 
}

// ---------- computations ----------
function allItems(proj){
  const out=[]; (proj.sows||[]).forEach(s=> (s.boqs||[]).forEach(b=> (b.items||[]).forEach(it=> out.push(it)))); return out;
}
function projectSph(proj){
  if(proj.sphMode==='project') return { awal: proj.projectSphAwal, final: proj.projectSphFinal };
  const items = allItems(proj);
  let awal=0, final=0, hasAwal=false, hasFinal=true;
  items.forEach(it=>{
    if(it.sphAwal!=null){ awal += Number(it.sphAwal); hasAwal=true; }
    if(it.sphFinal==null){ hasFinal=false; } else { final += Number(it.sphFinal); }
  });
  return { awal: hasAwal?awal:null, final: (hasFinal && items.length)?final:null };
}
function efficiencyPct(awal, final){
  if(awal==null || final==null || awal<=0) return null;
  return (awal-final)/awal*100;
}
function durationDays(proj){
  const start = new Date(proj.createdAt);
  const end = proj.closedAt ? new Date(proj.closedAt) : new Date();
  return Math.max(0, Math.round((end-start)/(1000*60*60*24)));
}
function uniquePicsInProject(proj){
  const set = new Set();
  if(proj.leadId) set.add(proj.leadId);
  allItems(proj).forEach(it=> (it.picIds||[]).forEach(p=>set.add(p)));
  return [...set];
}
function valToM(val) {
    return ((val || 0) / 1000000000).toFixed(1);
}

function getDynamicStatus(proj) {
    if (proj.status === 'win' || proj.status === 'lose') return 'Completed';
    if (!proj.targetRfs) return 'Planned';
    
    const today = new Date(todayStr());
    const rfs = new Date(proj.targetRfs);
    const diffTime = rfs - today;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays < 0) return 'Overdue';
    if (diffDays <= 14) return 'At Risk';
    return 'On Track';
}
function badgeStatus(stat) {
    const cls = stat.toLowerCase().replace(' ', '-');
    return `<span class="badge badge-${cls}">${stat}</span>`;
}

function computePicStats(){
  const stats = {};
  team.forEach(m=> stats[m] = { leadCount:0, supportLoad:0, participationShare:0, winShare:0, effSum:0, effWeight:0 });
  projects.forEach(proj=>{
    if(proj.leadId && stats[proj.leadId]) stats[proj.leadId].leadCount++;
    const uniq = uniquePicsInProject(proj);
    if(proj.status!=='ongoing' && uniq.length){
      const share = 1/uniq.length;
      uniq.forEach(p=>{
        if(!stats[p]) return;
        stats[p].participationShare += share;
        if(proj.status==='win') stats[p].winShare += share;
      });
    }
    const eff = efficiencyPct(projectSph(proj).awal, projectSph(proj).final);
    allItems(proj).forEach(it=>{
      const pics = it.picIds && it.picIds.length ? it.picIds : [];
      if(!pics.length) return;
      const share = 1/pics.length;
      pics.forEach(p=>{
        if(!stats[p]) return;
        stats[p].supportLoad += share;
        if(eff!=null){ stats[p].effSum += eff*share; stats[p].effWeight += share; }
      });
    });
  });
  return stats;
}

function fmtIdr(n){ return n==null ? '—' : 'Rp ' + Math.round(n).toLocaleString('id-ID'); }
function fmtPct(n){ return n==null ? '—' : n.toFixed(1)+'%'; }

function render(){
  const app = document.getElementById('app');

  const pageTitle =
    activeTab === 'overview'
      ? 'Presourcing Overview'
      : activeTab === 'projects'
      ? 'Project & BoQ Management'
      : 'Team & Workload';

  const pageSub =
    activeTab === 'overview'
      ? 'Executive view of the current presourcing portfolio'
      : activeTab === 'projects'
      ? 'Detail project, BoQ, SPH, dan progress'
      : 'Distribusi project dan beban kerja tim';

  const lastUpdated = new Date().toLocaleTimeString('id-ID', {
    hour: '2-digit',
    minute: '2-digit'
  });

  app.innerHTML = `
    <div class="page-header-clean">

      <div>
        <div class="page-eyebrow">
          PRESOURCING CONTROL
        </div>

        <h1>
          ${pageTitle}
        </h1>

        <div class="page-sub">
          ${pageSub}
        </div>
      </div>

      <div class="page-meta">
        <span>
          Last updated
        </span>

        <strong>
          ${lastUpdated}
        </strong>

        <span class="page-status ${storageOk ? 'online' : 'offline'}">
          ${storageOk ? '● Online' : '● Offline'}
        </span>
      </div>

    </div>

    <div id="tabcontent"></div>
  `;

  const content = document.getElementById('tabcontent');

  if(activeTab === 'overview') {
    content.innerHTML = renderOverview();
  }

  if(activeTab === 'projects') {
    content.innerHTML = renderProjects();
  }

  if(activeTab === 'team') {
    content.innerHTML = renderTeam();
  }

  wireEvents();

  if(modal) {
    renderModal();
  }

  // sync navbar state
  document.querySelectorAll('.app-nav-item').forEach(el => {
    el.classList.toggle(
      'active',
      el.dataset.tab === activeTab
    );
  });
}

function tabBtn(id,label){
  return `<div class="tab ${activeTab===id?'active':''}" data-tab="${id}">${label}</div>`;
}

function switchDashboardTab(id) {
  activeTab = id;
  openProjectId = null;

  document.querySelectorAll('.app-nav-item').forEach(el => {
    el.classList.toggle(
      'active',
      el.dataset.tab === id
    );
  });

  render();
}
// --------------------------------------------------------
// RENDER OVERVIEW: EXECUTIVE DASHBOARD (PIXEL-PERFECT MOCKUP ALIGNMENT)
// --------------------------------------------------------
function renderOverview(){
  const totalProj = projects.length;
  const activeProj = projects.filter(p => p.status === 'ongoing').length;

  let totalVal = 0;
  let effSum = 0;
  let effCount = 0;

  const sCount = {
    'On Track': 0,
    'At Risk': 0,
    'Overdue': 0,
    'Completed': 0,
    'Planned': 0
  };

  const pCount = {
    1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0
  };

  projects.forEach(p => {
    const sph = projectSph(p);
    totalVal += (sph.awal || 0);

    const eff = efficiencyPct(sph.awal, sph.final);
    if (eff != null) {
      effSum += eff;
      effCount++;
    }

    const stat = getDynamicStatus(p);
    sCount[stat]++;

    if (p.status === 'ongoing') {
      const stage = parseInt((p.pipelineStage || '1').charAt(0));
      if (!isNaN(stage) && stage >= 1 && stage <= 6) {
        pCount[stage]++;
      }
    }
  });

  const avgEff = effCount ? effSum / effCount : null;
  const criticalCount = sCount['Overdue'];
  const watchCount = sCount['At Risk'];

  const pct = (n) => totalProj ? Math.round((n / totalProj) * 100) : 0;

  // Load Chart.js once
  if (!window.Chart && !document.getElementById('chartjs-script')) {
    const script = document.createElement('script');
    script.id = 'chartjs-script';
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
    script.onload = () => setTimeout(renderDashboardCharts, 100);
    document.head.appendChild(script);
  } else {
    setTimeout(renderDashboardCharts, 100);
  }

  const sortedProjects = [...projects].sort((a, b) => {
    const da = a.targetRfs ? new Date(a.targetRfs).getTime() : Infinity;
    const db = b.targetRfs ? new Date(b.targetRfs).getTime() : Infinity;
    return da - db;
  });

  // ---------- PROJECT TABLE ----------
  let overviewRows = '';

  if (!sortedProjects.length) {
    overviewRows = `
      <tr>
        <td colspan="7">
          <div class="ux-empty">Belum ada project.</div>
        </td>
      </tr>
    `;
  } else {
    sortedProjects.forEach((p, idx) => {
      const sph = projectSph(p);
      const status = getDynamicStatus(p);
      const progress = Math.max(0, Math.min(100, Number(p.progressPct) || 0));

      const rfs = p.targetRfs
        ? new Date(p.targetRfs).toLocaleDateString('id-ID', {
            day: '2-digit',
            month: 'short',
            year: 'numeric'
          })
        : '—';

      overviewRows += `
        <tr>
          <td class="ux-no">${idx + 1}</td>

          <td>
            <div class="ux-project-name" title="${escAttr(p.name)}">
              ${escAttr(p.name) || 'Unnamed Project'}
            </div>
            <div class="ux-project-meta">
              ${escAttr(p.requestorDept || '—')}
            </div>
          </td>

          <td class="mono">
            ${valToM(sph.awal)} M
          </td>

          <td>
            <div class="ux-pic">${escAttr(p.leadId || '—')}</div>
          </td>

          <td class="ux-nowrap">${rfs}</td>

          <td>${badgeStatus(status)}</td>

          <td>
            <div class="ux-progress-wrap">
              <div class="ux-progress-head">
                <span>${progress}%</span>
              </div>
              <div class="ux-progress-track">
                <div
                  class="ux-progress-fill"
                  style="width:${progress}%"
                ></div>
              </div>
            </div>
          </td>
        </tr>
      `;
    });
  }

  // ---------- EARLY WARNING ----------
  const attentionProjects = sortedProjects.filter(p => {
    const s = getDynamicStatus(p);
    return s === 'Overdue' || s === 'At Risk';
  });

  let ewsRows = '';

  if (!attentionProjects.length) {
    ewsRows = `
      <tr>
        <td colspan="4">
          <div class="ux-safe-state">
            <div class="ux-safe-icon">✓</div>
            <div>
              <strong>Tidak ada project yang perlu perhatian khusus</strong>
              <span>Seluruh project masih dalam kondisi terkendali.</span>
            </div>
          </div>
        </td>
      </tr>
    `;
  } else {
    attentionProjects.forEach(p => {
      const status = getDynamicStatus(p);
      const progress = Math.max(0, Math.min(100, Number(p.progressPct) || 0));

      const rfs = p.targetRfs
        ? new Date(p.targetRfs).toLocaleDateString('id-ID', {
            day: '2-digit',
            month: 'short'
          })
        : '—';

      ewsRows += `
        <tr>
          <td>
            <div class="ux-ew-project">${escAttr(p.name)}</div>
            <div class="ux-project-meta">
              PIC: ${escAttr(p.leadId || '—')}
            </div>
          </td>

          <td class="ux-nowrap">${rfs}</td>

          <td>
            <div class="ux-ew-progress">${progress}%</div>
          </td>

          <td>${badgeStatus(status)}</td>
        </tr>
      `;
    });
  }

  // ---------- PIPELINE ----------
  const pipelineNames = [
  'Project Identification',
  'SPH Preparation',
  'Vendor Selection',
  'Negotiation',
  'Finalization',
  'RFS'
  ];

  let pipelineHtml = '';

  pipelineNames.forEach((name, i) => {
    const stageNo = i + 1;
    const count = pCount[stageNo];
    const pct = totalProj ? Math.round((count / totalProj) * 100) : 0;

    const isActive = count > 0 && stageNo < 6;
    const isFinal = stageNo === 6;

    pipelineHtml += `
        <div class="ux-pipeline-stage ${isActive ? 'is-active' : ''} ${isFinal ? 'is-final' : ''}">

          <div class="ux-pipeline-top">
            <div class="ux-pipeline-no">${stageNo}</div>
            <div class="ux-pipeline-count">${count}</div>
          </div>

          <div class="ux-pipeline-name">${name}</div>

          <div class="ux-pipeline-label">
            ${count === 1 ? '1 project' : `${count} projects`}
          </div>

          <div class="ux-pipeline-share">
            <div
              class="ux-pipeline-share-fill"
              style="width:${pct}%;">
            </div>
          </div>

        </div>
      `;
  });

  const dashStyles = `
    <style>
      .ux-overview {
        display:flex;
        flex-direction:column;
        gap:16px;
      }

      .ux-kpi-grid {
        display:grid;
        grid-template-columns:repeat(6, minmax(0, 1fr));
        gap:12px;
      }

      .ux-kpi {
        background:#fff;
        border:1px solid #e2e8f0;
        border-radius:10px;
        padding:15px 16px;
        min-height:88px;
        position:relative;
        overflow:hidden;
      }

      .ux-kpi::before {
        content:'';
        position:absolute;
        left:0;
        top:0;
        bottom:0;
        width:3px;
        background:#2563eb;
      }

      .ux-kpi.warning::before { background:#f59e0b; }
      .ux-kpi.danger::before { background:#dc2626; }
      .ux-kpi.success::before { background:#16a34a; }
      .ux-kpi.neutral::before { background:#64748b; }

      .ux-kpi-label {
        color:#64748b;
        font-size:11px;
        margin-bottom:7px;
        font-weight:600;
        letter-spacing:.01em;
      }

      .ux-kpi-value {
        font-size:22px;
        line-height:1.1;
        font-weight:700;
        color:#0f172a;
      }

      .ux-kpi-sub {
        margin-top:5px;
        font-size:10.5px;
        color:#94a3b8;
      }

      .ux-grid-main {
        display:grid;
        grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);
        gap:16px;
      }

      .ux-grid-half {
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:16px;
      }

      .ux-panel {
        background:#fff;
        border:1px solid #e2e8f0;
        border-radius:10px;
        overflow:hidden;
        min-width:0;
      }

      .ux-panel-hd {
        display:flex;
        align-items:center;
        justify-content:space-between;
        padding:13px 16px;
        border-bottom:1px solid #e2e8f0;
      }

      .ux-panel-title {
        font-size:13px;
        font-weight:700;
        color:#0f172a;
      }

      .ux-panel-sub {
        font-size:10.5px;
        color:#94a3b8;
        margin-top:2px;
      }

      .ux-panel-body {
        padding:14px 16px;
      }

      .ux-table-wrap {
        max-height:320px;
        overflow:auto;
      }

      .ux-table {
        width:100%;
        border-collapse:collapse;
      }

      .ux-table th {
        position:sticky;
        top:0;
        z-index:2;
        background:#f8fafc;
        color:#64748b;
        font-size:10px;
        font-weight:700;
        text-transform:uppercase;
        letter-spacing:.03em;
        padding:9px 10px;
        border-bottom:1px solid #e2e8f0;
        white-space:nowrap;
      }

      .ux-table td {
        padding:10px;
        border-bottom:1px solid #f1f5f9;
        font-size:11.5px;
        color:#334155;
        vertical-align:middle;
      }

      .ux-table tbody tr:hover {
        background:#f8fafc;
      }

      .ux-no {
        color:#94a3b8 !important;
        width:30px;
      }

      .ux-project-name {
        font-size:11.8px;
        font-weight:600;
        color:#0f172a;
        max-width:190px;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
      }

      .ux-project-meta {
        margin-top:2px;
        font-size:10px;
        color:#94a3b8;
      }

      .ux-pic {
        font-weight:600;
        color:#334155;
      }

      .ux-nowrap {
        white-space:nowrap;
      }

      .ux-progress-wrap {
        min-width:70px;
      }

      .ux-progress-head {
        display:flex;
        justify-content:flex-end;
        font-size:10px;
        color:#475569;
        margin-bottom:3px;
      }

      .ux-progress-track {
        height:5px;
        background:#e2e8f0;
        border-radius:10px;
        overflow:hidden;
      }

      .ux-progress-fill {
        height:100%;
        background:#2563eb;
        border-radius:10px;
      }

      .ux-chart {
        height:230px;
        position:relative;
      }

      .ux-chart canvas {
        width:100% !important;
        height:100% !important;
      }

      .ux-warning-summary {
        display:flex;
        gap:10px;
        padding:12px 16px;
        border-bottom:1px solid #e2e8f0;
        background:#fffbeb;
      }

      .ux-warning-box {
        flex:1;
        border:1px solid #fde68a;
        background:#fff;
        border-radius:7px;
        padding:9px 11px;
      }

      .ux-warning-label {
        font-size:10px;
        color:#92400e;
        font-weight:600;
      }

      .ux-warning-value {
        margin-top:2px;
        font-size:18px;
        font-weight:700;
        color:#78350f;
      }

      .ux-safe-state {
        display:flex;
        align-items:center;
        gap:10px;
        padding:22px 16px;
      }

      .ux-safe-icon {
        width:28px;
        height:28px;
        border-radius:50%;
        display:flex;
        align-items:center;
        justify-content:center;
        background:#dcfce7;
        color:#15803d;
        font-weight:700;
      }

      .ux-safe-state strong {
        display:block;
        font-size:11.5px;
        color:#166534;
      }

      .ux-safe-state span {
        display:block;
        margin-top:2px;
        font-size:10.5px;
        color:#64748b;
      }

      .ux-ew-project {
        font-size:11.5px;
        font-weight:600;
        color:#0f172a;
        max-width:220px;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
      }

      .ux-ew-progress {
        font-weight:700;
        color:#334155;
      }

      .ux-pipeline {
  display:grid;
  grid-template-columns:repeat(6, minmax(0,1fr));
  gap:0;
  padding:8px 4px 4px;
}

.ux-pipeline-stage {
  min-width:0;
  position:relative;
  padding:12px 14px 12px 18px;
  background:#f8fafc;
  border-top:1px solid #e2e8f0;
  border-bottom:1px solid #e2e8f0;
  border-left:1px solid #e2e8f0;
}

.ux-pipeline-stage:first-child {
  border-radius:8px 0 0 8px;
}

.ux-pipeline-stage:last-child {
  border-right:1px solid #e2e8f0;
  border-radius:0 8px 8px 0;
}

.ux-pipeline-stage:not(:last-child)::after {
  content:'';
  position:absolute;
  top:50%;
  right:-10px;
  width:18px;
  height:18px;
  transform:translateY(-50%) rotate(45deg);
  background:#f8fafc;
  border-top:1px solid #e2e8f0;
  border-right:1px solid #e2e8f0;
  z-index:3;
}

.ux-pipeline-stage.is-active {
  background:#eff6ff;
  border-color:#bfdbfe;
}

.ux-pipeline-stage.is-active::after {
  background:#eff6ff;
  border-color:#bfdbfe;
}

.ux-pipeline-stage.is-final {
  background:#f0fdf4;
  border-color:#bbf7d0;
}

.ux-pipeline-stage.is-final::after {
  background:#f0fdf4;
  border-color:#bbf7d0;
}

.ux-pipeline-top {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:8px;
}

.ux-pipeline-no {
  width:24px;
  height:24px;
  border-radius:50%;
  display:flex;
  align-items:center;
  justify-content:center;
  background:#e2e8f0;
  color:#64748b;
  font-size:10px;
  font-weight:700;
}

.ux-pipeline-stage.is-active .ux-pipeline-no {
  background:#2563eb;
  color:#fff;
}

.ux-pipeline-stage.is-final .ux-pipeline-no {
  background:#16a34a;
  color:#fff;
}

.ux-pipeline-count {
  font-size:18px;
  line-height:1;
  font-weight:700;
  color:#0f172a;
}

.ux-pipeline-name {
  margin-top:9px;
  min-height:28px;
  font-size:10.5px;
  line-height:1.25;
  color:#475569;
  font-weight:600;
}

.ux-pipeline-label {
  margin-top:5px;
  font-size:9.5px;
  color:#94a3b8;
}

.ux-pipeline-share {
  margin-top:7px;
  height:4px;
  background:#e2e8f0;
  border-radius:10px;
  overflow:hidden;
}

.ux-pipeline-share-fill {
  height:100%;
  background:#93c5fd;
  border-radius:10px;
}

.ux-pipeline-stage.is-active .ux-pipeline-share-fill {
  background:#2563eb;
}

.ux-pipeline-stage.is-final .ux-pipeline-share-fill {
  background:#16a34a;
}

@media(max-width:900px) {
  .ux-pipeline {
    grid-template-columns:repeat(3,1fr);
    gap:8px;
  }

  .ux-pipeline-stage,
  .ux-pipeline-stage:first-child,
  .ux-pipeline-stage:last-child {
    border:1px solid #e2e8f0;
    border-radius:8px;
  }

  .ux-pipeline-stage::after {
    display:none;
  }
}

@media(max-width:600px) {
  .ux-pipeline {
    grid-template-columns:repeat(2,1fr);
  }
}
    </style>
  `;

  return dashStyles + `
    <div class="ux-overview">

      <!-- KPI -->
      <div class="ux-kpi-grid">

        <div class="ux-kpi">
          <div class="ux-kpi-label">TOTAL PROJECT</div>
          <div class="ux-kpi-value">${totalProj}</div>
          <div class="ux-kpi-sub">${activeProj} sedang berjalan</div>
        </div>

        <div class="ux-kpi">
          <div class="ux-kpi-label">TOTAL PROJECT VALUE</div>
          <div class="ux-kpi-value" style="font-size:18px;">
            Rp ${valToM(totalVal)} M
          </div>
          <div class="ux-kpi-sub">Berdasarkan SPH Awal</div>
        </div>

        <div class="ux-kpi success">
          <div class="ux-kpi-label">ON TRACK</div>
          <div class="ux-kpi-value">${sCount['On Track']}</div>
          <div class="ux-kpi-sub">${pct(sCount['On Track'])}% dari portfolio</div>
        </div>

        <div class="ux-kpi warning">
          <div class="ux-kpi-label">AT RISK</div>
          <div class="ux-kpi-value">${watchCount}</div>
          <div class="ux-kpi-sub">Perlu monitoring</div>
        </div>

        <div class="ux-kpi danger">
          <div class="ux-kpi-label">OVERDUE</div>
          <div class="ux-kpi-value">${criticalCount}</div>
          <div class="ux-kpi-sub">Target RFS terlewat</div>
        </div>

        <div class="ux-kpi neutral">
          <div class="ux-kpi-label">AVG EFFICIENCY</div>
          <div class="ux-kpi-value">${fmtPct(avgEff)}</div>
          <div class="ux-kpi-sub">${effCount} project dengan data lengkap</div>
        </div>

      </div>

      <!-- PROJECT OVERVIEW + PIC VALUE -->
      <div class="ux-grid-main">

        <div class="ux-panel">
          <div class="ux-panel-hd">
            <div>
              <div class="ux-panel-title">Project Presourcing Overview</div>
              <div class="ux-panel-sub">Portfolio aktif dan target RFS</div>
            </div>
            <div class="ux-panel-sub">${totalProj} project</div>
          </div>

          <div class="ux-table-wrap">
            <table class="ux-table">
              <thead>
                <tr>
                  <th>No</th>
                  <th>Project</th>
                  <th>Value</th>
                  <th>PIC</th>
                  <th>Target RFS</th>
                  <th>Status</th>
                  <th>Progress</th>
                </tr>
              </thead>
              <tbody>
                ${overviewRows}
              </tbody>
            </table>
          </div>
        </div>

        <div class="ux-panel">
          <div class="ux-panel-hd">
            <div>
              <div class="ux-panel-title">Project Value by PIC</div>
              <div class="ux-panel-sub">Distribusi nilai portfolio berdasarkan lead presource</div>
            </div>
          </div>

          <div class="ux-panel-body">
            <div class="ux-chart">
              <canvas id="chartPicValue"></canvas>
            </div>
          </div>
        </div>

      </div>

      <!-- EARLY WARNING + RFS -->
      <div class="ux-grid-half">

        <div class="ux-panel">
          <div class="ux-panel-hd">
            <div>
              <div class="ux-panel-title">Target RFS by Month</div>
              <div class="ux-panel-sub">Volume project dan nilai SPH awal</div>
            </div>
          </div>

          <div class="ux-panel-body">
            <div class="ux-chart">
              <canvas id="chartRfsMonth"></canvas>
            </div>
          </div>
        </div>

        <div class="ux-panel">
          <div class="ux-panel-hd">
            <div>
              <div class="ux-panel-title">Early Warning</div>
              <div class="ux-panel-sub">Project yang membutuhkan perhatian</div>
            </div>
          </div>

          <div class="ux-warning-summary">
            <div class="ux-warning-box">
              <div class="ux-warning-label">OVERDUE</div>
              <div class="ux-warning-value">${criticalCount}</div>
            </div>
            <div class="ux-warning-box">
              <div class="ux-warning-label">AT RISK</div>
              <div class="ux-warning-value">${watchCount}</div>
            </div>
          </div>

          <div class="ux-table-wrap">
            <table class="ux-table">
              <thead>
                <tr>
                  <th>Project</th>
                  <th>RFS</th>
                  <th>Progress</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                ${ewsRows}
              </tbody>
            </table>
          </div>
        </div>

      </div>

      <!-- TOP 5 + STATUS -->
      <div class="ux-grid-half">

        <div class="ux-panel">
          <div class="ux-panel-hd">
            <div>
              <div class="ux-panel-title">Top 5 Project Value</div>
              <div class="ux-panel-sub">Project dengan SPH Awal terbesar</div>
            </div>
          </div>

          <div class="ux-panel-body">
            <div class="ux-chart">
              <canvas id="chartTop5"></canvas>
            </div>
          </div>
        </div>

        <div class="ux-panel">
          <div class="ux-panel-hd">
            <div>
              <div class="ux-panel-title">Project Status</div>
              <div class="ux-panel-sub">Distribusi kondisi portfolio saat ini</div>
            </div>
          </div>

          <div class="ux-panel-body">
            <div class="ux-chart">
              <canvas id="chartStatus"></canvas>
            </div>
          </div>
        </div>

      </div>

      <!-- PIPELINE -->
      <div class="ux-panel">

        <div class="ux-panel-hd">
          <div>
            <div class="ux-panel-title">Presourcing Progress Pipeline</div>
            <div class="ux-panel-sub">Distribusi project berdasarkan tahapan presourcing</div>
          </div>
        </div>

        <div class="ux-panel-body">
          <div class="ux-pipeline">
            ${pipelineHtml}
          </div>
        </div>

      </div>

    </div>
  `;
}

// Global variable untuk menyimpan instance grafik agar tidak terjadi duplikasi/memory leak
let dCharts = {}; 

function renderDashboardCharts() {
    if (typeof Chart === 'undefined') return;

    // ----------------------------------------------------
    // COMMON CHART CONFIG
    // ----------------------------------------------------
    const chartFont = {
        family: "'Inter', 'Segoe UI', Arial, sans-serif",
        size: 10
    };

    const axisColor = '#64748b';
    const gridColor = '#eef2f7';
    const primary = '#2563eb';
    const primarySoft = '#93c5fd';
    const dark = '#0f172a';

    const destroyChart = (key) => {
        if (dCharts[key]) {
            dCharts[key].destroy();
            dCharts[key] = null;
        }
    };

    const fmtRpM = (value) => {
        const num = Number(value) || 0;
        return `Rp ${num.toLocaleString('id-ID', {
            minimumFractionDigits: 1,
            maximumFractionDigits: 1
        })} M`;
    };

    // ----------------------------------------------------
    // 1. PROJECT STATUS — DONUT
    // ----------------------------------------------------
    const statusLabels = ['On Track', 'At Risk', 'Overdue', 'Completed', 'Planned'];
    const statusColors = ['#16a34a', '#f59e0b', '#dc2626', '#2563eb', '#cbd5e1'];

    const sCount = {
        'On Track': 0,
        'At Risk': 0,
        'Overdue': 0,
        'Completed': 0,
        'Planned': 0
    };

    projects.forEach(p => {
        const status = getDynamicStatus(p);
        if (sCount[status] !== undefined) {
            sCount[status]++;
        }
    });

    const statusData = statusLabels.map(label => sCount[label]);

    const ctxStatus = document.getElementById('chartStatus');

    if (ctxStatus) {
        destroyChart('status');

        const hasStatusData = statusData.some(v => v > 0);

        dCharts.status = new Chart(ctxStatus, {
            type: 'doughnut',
            data: {
                labels: hasStatusData ? statusLabels : ['Belum ada data'],
                datasets: [{
                    data: hasStatusData ? statusData : [1],
                    backgroundColor: hasStatusData ? statusColors : ['#e2e8f0'],
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '72%',

                layout: {
                    padding: 4
                },

                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            usePointStyle: true,
                            pointStyle: 'circle',
                            boxWidth: 7,
                            boxHeight: 7,
                            padding: 12,
                            color: axisColor,
                            font: chartFont
                        }
                    },

                    tooltip: {
                        padding: 10,
                        callbacks: {
                            label: function(ctx) {
                                if (!hasStatusData) {
                                    return ' Belum ada data';
                                }

                                const value = ctx.raw || 0;
                                const total = statusData.reduce((a, b) => a + b, 0);
                                const pct = total ? Math.round((value / total) * 100) : 0;

                                return ` ${ctx.label}: ${value} project (${pct}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    // ----------------------------------------------------
    // 2. TARGET RFS BY MONTH — BAR + LINE
    // ----------------------------------------------------
    const rfsData = {};

    projects.forEach(p => {
        if (!p.targetRfs) return;

        const d = new Date(p.targetRfs);
        if (isNaN(d.getTime())) return;

        const months = [
            'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
            'Jul', 'Ags', 'Sep', 'Okt', 'Nov', 'Des'
        ];

        const key = `${months[d.getMonth()]} ${d.getFullYear()}`;
        const sortK = d.getFullYear() * 100 + d.getMonth();

        if (!rfsData[key]) {
            rfsData[key] = {
                count: 0,
                val: 0,
                sortK
            };
        }

        rfsData[key].count += 1;
        rfsData[key].val += (projectSph(p).awal || 0);
    });

    const rfsKeys = Object.keys(rfsData).sort(
        (a, b) => rfsData[a].sortK - rfsData[b].sortK
    );

    const ctxRfs = document.getElementById('chartRfsMonth');

    if (ctxRfs) {
        destroyChart('rfsMonth');

        dCharts.rfsMonth = new Chart(ctxRfs, {
            type: 'bar',

            data: {
                labels: rfsKeys,

                datasets: [
                    {
                        type: 'bar',
                        label: 'Jumlah Project',
                        data: rfsKeys.map(k => rfsData[k].count),

                        backgroundColor: primarySoft,
                        borderColor: primarySoft,
                        borderWidth: 0,

                        borderRadius: 5,
                        borderSkipped: false,

                        barPercentage: 0.6,
                        categoryPercentage: 0.7,

                        yAxisID: 'y'
                    },

                    {
                        type: 'line',
                        label: 'Project Value',
                        data: rfsKeys.map(k =>
                            Number((rfsData[k].val / 1000000000).toFixed(1))
                        ),

                        borderColor: dark,
                        backgroundColor: dark,

                        borderWidth: 2,
                        pointRadius: 3,
                        pointHoverRadius: 5,

                        tension: 0.3,
                        fill: false,

                        yAxisID: 'y1'
                    }
                ]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                interaction: {
                    mode: 'index',
                    intersect: false
                },

                scales: {
                    x: {
                        grid: {
                            display: false
                        },
                        border: {
                            display: false
                        },
                        ticks: {
                            color: axisColor,
                            font: chartFont,
                            maxRotation: 0,
                            autoSkip: true
                        }
                    },

                    y: {
                        beginAtZero: true,

                        ticks: {
                            color: axisColor,
                            font: chartFont,
                            precision: 0,
                            stepSize: 1
                        },

                        grid: {
                            color: gridColor
                        },

                        border: {
                            display: false
                        }
                    },

                    y1: {
                        beginAtZero: true,
                        position: 'right',

                        ticks: {
                            color: axisColor,
                            font: chartFont,
                            callback: value => `Rp ${value} M`
                        },

                        grid: {
                            drawOnChartArea: false
                        },

                        border: {
                            display: false
                        }
                    }
                },

                plugins: {
                    legend: {
                        position: 'bottom',

                        labels: {
                            usePointStyle: true,
                            pointStyle: 'circle',
                            boxWidth: 7,
                            boxHeight: 7,
                            padding: 14,
                            color: axisColor,
                            font: chartFont
                        }
                    },

                    tooltip: {
                        padding: 10,

                        callbacks: {
                            label: function(ctx) {
                                if (ctx.dataset.label === 'Jumlah Project') {
                                    return ` ${ctx.raw} project`;
                                }

                                return ` ${fmtRpM(ctx.raw)}`;
                            }
                        }
                    }
                }
            }
        });
    }

    // ----------------------------------------------------
    // 3. TOP 5 PROJECT VALUE — HORIZONTAL BAR
    // ----------------------------------------------------
    const top5 = [...projects]
        .filter(p => p.status !== 'lose')
        .map(p => ({
            name: p.name || 'Unnamed Project',
            val: Number(((projectSph(p).awal || 0) / 1000000000).toFixed(1))
        }))
        .sort((a, b) => b.val - a.val)
        .slice(0, 5);

    const ctxTop5 = document.getElementById('chartTop5');

    if (ctxTop5) {
        destroyChart('top5');

        dCharts.top5 = new Chart(ctxTop5, {
            type: 'bar',

            data: {
                labels: top5.map(t => {
                    const name = t.name;
                    return name.length > 28
                        ? name.substring(0, 28) + '...'
                        : name;
                }),

                datasets: [{
                    label: 'Project Value',
                    data: top5.map(t => t.val),

                    backgroundColor: primary,
                    borderWidth: 0,

                    borderRadius: 5,
                    borderSkipped: false,

                    barPercentage: 0.62,
                    categoryPercentage: 0.72
                }]
            },

            options: {
                indexAxis: 'y',

                responsive: true,
                maintainAspectRatio: false,

                scales: {
                    x: {
                        beginAtZero: true,

                        grid: {
                            color: gridColor
                        },

                        border: {
                            display: false
                        },

                        ticks: {
                            color: axisColor,
                            font: chartFont,

                            callback: value =>
                                `Rp ${value} M`
                        }
                    },

                    y: {
                        grid: {
                            display: false
                        },

                        border: {
                            display: false
                        },

                        ticks: {
                            color: '#334155',
                            font: {
                                ...chartFont,
                                weight: '500'
                            }
                        }
                    }
                },

                plugins: {
                    legend: {
                        display: false
                    },

                    tooltip: {
                        padding: 10,

                        callbacks: {
                            label: ctx =>
                                ` ${fmtRpM(ctx.raw)}`
                        }
                    }
                }
            }
        });
    }

    // ----------------------------------------------------
    // 4. PROJECT VALUE BY PIC — HORIZONTAL BAR
    // ----------------------------------------------------
    const picValData = {};

    team.forEach(m => {
        picValData[m] = 0;
    });

    projects.forEach(p => {
        if (!p.leadId) return;

        if (picValData[p.leadId] === undefined) {
            picValData[p.leadId] = 0;
        }

        picValData[p.leadId] += (
            (projectSph(p).awal || 0) / 1000000000
        );
    });

    const picData = Object.entries(picValData)
        .map(([name, value]) => ({
            name,
            value: Number(value.toFixed(1))
        }))
        .filter(x => x.value > 0)
        .sort((a, b) => b.value - a.value);

    const ctxPic = document.getElementById('chartPicValue');

    if (ctxPic) {
        destroyChart('picVal');

        dCharts.picVal = new Chart(ctxPic, {
            type: 'bar',

            data: {
                labels: picData.map(x => x.name),

                datasets: [{
                    label: 'Project Value',
                    data: picData.map(x => x.value),

                    backgroundColor: '#3b82f6',
                    borderWidth: 0,

                    borderRadius: 5,
                    borderSkipped: false,

                    barPercentage: 0.58,
                    categoryPercentage: 0.72
                }]
            },

            options: {
                indexAxis: 'y',

                responsive: true,
                maintainAspectRatio: false,

                scales: {
                    x: {
                        beginAtZero: true,

                        grid: {
                            color: gridColor
                        },

                        border: {
                            display: false
                        },

                        ticks: {
                            color: axisColor,
                            font: chartFont,

                            callback: value =>
                                `Rp ${value} M`
                        }
                    },

                    y: {
                        grid: {
                            display: false
                        },

                        border: {
                            display: false
                        },

                        ticks: {
                            color: '#334155',
                            font: {
                                ...chartFont,
                                weight: '500'
                            }
                        }
                    }
                },

                plugins: {
                    legend: {
                        display: false
                    },

                    tooltip: {
                        padding: 10,

                        callbacks: {
                            label: ctx =>
                                ` ${fmtRpM(ctx.raw)}`
                        }
                    }
                }
            }
        });
    }
}

// --------------------------------------------------------
// RENDER DETAIL PROJECTS (Tabel Lengkap)
// --------------------------------------------------------
function renderProjects(){
  const filtered = projects.filter(p=>{
    if(filters.priority!=='all' && p.priority!==filters.priority) return false;
    if(filters.status!=='all' && p.status!==filters.status) return false;
    return true;
  });

  let tbodyHtml = '';
  if(filtered.length === 0){
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
          <td class="num mono">${durationDays(p)}hari</td>
        </tr>
      `;
      if (openProjectId === p.id) {
        tbodyHtml += `<tr><td colspan="7">${renderProjectDetail(p)}</td></tr>`;
      }
    });
  }

  return `
    <div class="panel">
      <div class="panel-hd">
        <h2>Daftar Detail Project & BoQ</h2>
        <div style="display:flex; gap:8px; align-items:center;">
          <div class="filters">
            <select id="f-priority">
              <option value="all">Semua prioritas</option>
              <option value="Urgent">Urgent</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
            </select>
            <select id="f-status">
              <option value="all">Semua status</option>
              <option value="ongoing">Berjalan</option>
              <option value="win">Menang</option>
              <option value="lose">Kalah</option>
            </select>
          </div>
          <button class="btn-primary" id="btn-new-project">+ Project baru</button>
        </div>
      </div>
      <div class="panel-body">
        <table>
          <thead><tr>
            <th>Project</th><th>Pemohon</th><th>Status EWS</th><th>Tahap Pipeline</th>
            <th class="num">SPH Awal</th><th class="num">Efficiency</th><th class="num">Durasi</th>
          </tr></thead>
          <tbody>
            ${tbodyHtml}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderProjectDetail(p){
  const uniq = uniquePicsInProject(p);
  
  const docsHtml = `
    <div style="margin: 12px 0; padding: 12px; background: #FFFFFF; border: 1px dashed var(--border); border-radius: 6px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
            <strong style="font-size: 12.5px; color: var(--text);">📄 Dokumen SPH Pembanding (Audit Trail)</strong>
            <button class="mini-btn" onclick="openUploadPembandingModal('${p.id}')">+ Upload Pembanding</button>
        </div>
        ${p.comparison_docs && p.comparison_docs.length > 0 ? 
            p.comparison_docs.map(doc => `
                <div style="display:flex; justify-content:space-between; font-size: 12px; padding: 6px 0; border-bottom: 1px solid var(--border-soft);">
                    <div>
                        <span style="font-weight:600; color:var(--text);">${escAttr(doc.vendor_name)}</span> 
                        <span style="color:var(--text-muted);"> — Penawaran: <span class="mono">${fmtIdr(doc.offered_price)}</span></span>
                    </div>
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
      sowsHtml += `
        <div class="boq-title">Bill of Quantity: ${escAttr(boq.name)}</div>
        <div style="display:grid; grid-template-columns: 2fr 0.4fr 0.5fr 1fr 1fr 1fr 0.8fr 1.5fr; gap:8px; padding:5px 0; font-size:10.5px; color:var(--text-dim); border-bottom:1px solid var(--border);">
          <div>Item</div><div>Qty</div><div>UoM</div><div>Vendor</div><div class="num">SPH Awal</div><div class="num">SPH Final</div><div class="num">Efficiency</div><div>PIC</div>
        </div>
      `;
      let itemsHtml = '';
      (boq.items || []).forEach(it => {
        const eff = p.sphMode === 'item' ? efficiencyPct(it.sphAwal, it.sphFinal) : null;
        const notesHtml = it.notes ? `<div style="font-size:11px; color:var(--text-muted); margin-top:3px;">📝 ${escAttr(it.notes)}</div>` : '';
        const picsHtml = (it.picIds || []).map(x => `<span class="pic-chip">${escAttr(x)}</span>`).join('');
        itemsHtml += `
          <div style="display:grid; grid-template-columns: 2fr 0.4fr 0.5fr 1fr 1fr 1fr 0.8fr 1.5fr; gap:8px; padding:7px 0; font-size:12.5px; border-bottom:1px solid var(--border-soft); align-items:start;">
            <div><div style="font-weight:500;">${escAttr(it.product) || '—'}</div>${notesHtml}</div>
            <div style="color:var(--text-muted);">${it.qty || '-'}</div>
            <div style="color:var(--text-muted);">${escAttr(it.uom) || '-'}</div>
            <div style="color:var(--text-muted);">${escAttr(it.vendor) || '-'}</div>
            <div class="num mono">${p.sphMode==='item'?fmtIdr(it.sphAwal):'—'}</div>
            <div class="num mono">${p.sphMode==='item'?fmtIdr(it.sphFinal):'—'}</div>
            <div class="num mono">${p.sphMode==='item'?fmtPct(eff):'—'}</div>
            <div>${picsHtml}</div>
          </div>
        `;
      });
      sowsHtml += itemsHtml; 
    });
  });

  return `
    <div class="detail-block">
      <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
        <div style="font-size:12px; color:var(--text-muted);">Lead Presource: <strong style="color:var(--text);">${p.leadId||'—'}</strong> · PIC terlibat: ${uniq.join(', ')||'—'}</div>
        <div style="display:flex; gap:6px;">
          <button class="mini-btn" onclick="event.stopPropagation(); triggerRevisiBoq('${p.id}')">🔄 Revisi Excel BoQ</button>
          <button class="mini-btn" onclick="downloadProjectReport('${p.id}')">📥 Download Excel</button>
          <button class="mini-btn" data-edit-project="${p.id}">Edit</button>
          <button class="mini-btn danger" data-delete-project="${p.id}">Hapus</button>
        </div>
      </div>
      ${docsHtml}
      ${sowsHtml}
      ${p.sphMode==='project' ? `<div class="note">SPH dicatat di level total project (tidak dipecah per item).</div>` : ''}
    </div>
  `;
}

function renderTeam(){
  const stats = computePicStats();
  const rows = team.map(m=>{
    const s = stats[m];
    const winRate = s.participationShare>0 ? (s.winShare/s.participationShare*100) : null;
    const avgEff = s.effWeight>0 ? (s.effSum/s.effWeight) : null;
    return {name:m, ...s, winRate, avgEff};
  }).sort((a,b)=>b.supportLoad-a.supportLoad);
  
  return `
    <div class="panel">
      <div class="panel-hd">
        <h2>Beban &amp; performa tim (fractional split)</h2>
        <button class="btn-ghost" id="btn-manage-team">Kelola anggota tim</button>
      </div>
      <div class="panel-body">
        <table>
          <thead><tr>
            <th>Anggota</th><th class="num">Lead Count</th><th class="num">Support Load</th><th class="num">Win Rate</th><th class="num">Avg Efficiency</th>
          </tr></thead>
          <tbody>
          ${rows.map(r=>`<tr>
            <td>${escAttr(r.name)}</td>
            <td class="num mono">${r.leadCount}</td>
            <td class="num mono">${r.supportLoad.toFixed(2)}</td>
            <td class="num mono">${fmtPct(r.winRate)}</td>
            <td class="num mono">${fmtPct(r.avgEff)}</td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function wireEvents(){
  document.querySelectorAll('[data-tab]').forEach(el=> el.onclick = ()=>{ activeTab = el.dataset.tab; openProjectId=null; render(); });
  const fp = document.getElementById('f-priority'); if(fp){ fp.value=filters.priority; fp.onchange=()=>{filters.priority=fp.value; render();}; }
  const fs = document.getElementById('f-status'); if(fs){ fs.value=filters.status; fs.onchange=()=>{filters.status=fs.value; render();}; }
  document.querySelectorAll('[data-open]').forEach(el=> el.onclick = ()=>{ const id=el.dataset.open; openProjectId = openProjectId===id?null:id; render(); });
  const btnNew = document.getElementById('btn-new-project'); if(btnNew) btnNew.onclick = ()=> openProjectModal(null);
  document.querySelectorAll('[data-edit-project]').forEach(el=> el.onclick=(e)=>{ e.stopPropagation(); openProjectModal(el.dataset.editProject); });
  document.querySelectorAll('[data-delete-project]').forEach(el=> el.onclick=(e)=>{ e.stopPropagation(); if(confirm('Hapus project ini?')){ projects = projects.filter(p=>p.id!==el.dataset.deleteProject); saveAll(); render(); } });
  const btnTeam = document.getElementById('btn-manage-team'); if(btnTeam) btnTeam.onclick = ()=> openTeamModal();
}

function downloadProjectReport(projectId) { window.location.href = `/api/download_report?project_id=${projectId}`; }

function triggerRevisiBoq(projectId) {
    const fileInput = document.createElement('input');
    fileInput.type = 'file'; fileInput.accept = '.xlsx, .xls'; fileInput.style.display = 'none'; 
    document.body.appendChild(fileInput);
    fileInput.onchange = async (e) => {
        const file = e.target.files[0];
        document.body.removeChild(fileInput); 
        if (!file) return;
        if (!confirm(`Unggah revisi BoQ untuk project ini?`)) return;
        const formData = new FormData();
        formData.append('file', file); formData.append('ticket_id', projectId);
        document.body.style.cursor = 'wait';
        try {
            const res = await fetch('/api/revisi_boq', { method: 'POST', body: formData });
            const result = await res.json();
            if (res.ok && result.success) { alert(result.message); loadAll(); } 
            else alert(`Gagal merevisi BoQ: ${result.message}`);
        } catch (error) {
            alert('Terjadi kesalahan saat mengunggah file.');
        } finally { document.body.style.cursor = 'default'; }
    };
    fileInput.click();
}

function blankProject(){
  return {
    id: uid('proj'), name:'', requestorName:'', requestorDept:'',
    priority:'Medium', status:'ongoing', leadId: team[0]||'',
    sphMode:'item', projectSphAwal:null, projectSphFinal:null,
    createdAt: todayStr(), closedAt:null, targetRfs: '', pipelineStage: '1 - Project Identification', progressPct: 0,
    comparison_docs: [],
    sows:[{ id:uid('sow'), name:'', boqs:[{ id:uid('boq'), name:'', items:[{ id:uid('item'), product:'', qty:1, vendor:'', notes:'', picIds:[], sphAwal:null, sphFinal:null }] }] }]
  };
}
function openProjectModal(id){
  modalScroll = 0; 
  const existing = id ? JSON.parse(JSON.stringify(projects.find(p=>p.id===id))) : blankProject();
  modal = { type:'project', data: existing, isNew: !id };
  render();
}
function openTeamModal(){ 
  modalScroll = 0; 
  modal = { type:'team', data:{ names: team.join(', ') } }; render(); 
}
function renderModal(){
  let root = document.getElementById('modal-root');
  if(!root){ root = document.createElement('div'); root.id='modal-root'; document.body.appendChild(root); }
  if(modal.type==='project') root.innerHTML = projectModalHtml(modal.data, modal.isNew);
  if(modal.type==='team') root.innerHTML = teamModalHtml(modal.data);
  wireModalEvents();
  const m = document.querySelector('.modal');
  if(m) m.scrollTop = modalScroll;
}

function projectModalHtml(d, isNew){
  return `
  <div class="overlay" id="ov" style="z-index: 100;">
    <div class="modal">
      <div class="modal-hd">
        <h3>${isNew?'Project baru':'Edit project'}</h3>
        <button class="mini-btn" id="m-close" type="button">Tutup</button>
      </div>
      <div class="modal-body">
        <div class="field"><label>Nama project</label><input id="m-name" value="${escAttr(d.name)}"></div>
        <div class="grid2">
          <div class="field"><label>Nama pemohon (SA)</label><input id="m-req-name" value="${escAttr(d.requestorName)}"></div>
          <div class="field"><label>Departemen</label><input id="m-req-dept" value="${escAttr(d.requestorDept)}"></div>
        </div>
        
        <div class="grid3" style="background: #f8f9fa; padding: 12px; border-radius: 6px; margin-bottom: 12px; border: 1px dashed #ced4da;">
           <div class="field" style="margin:0;"><label>Target RFS</label><input type="date" id="m-target-rfs" value="${escAttr(d.targetRfs)}"></div>
           <div class="field" style="margin:0;"><label>Tahap Pipeline</label>
             <select id="m-pipeline-stage">
                <option value="1 - Project Identification" ${d.pipelineStage==='1 - Project Identification'?'selected':''}>1 - Identification</option>
                <option value="2 - SPH Preparation" ${d.pipelineStage==='2 - SPH Preparation'?'selected':''}>2 - SPH Prep</option>
                <option value="3 - Vendor Selection" ${d.pipelineStage==='3 - Vendor Selection'?'selected':''}>3 - Vendor Select</option>
                <option value="4 - Negotiation" ${d.pipelineStage==='4 - Negotiation'?'selected':''}>4 - Negotiation</option>
                <option value="5 - Finalization" ${d.pipelineStage==='5 - Finalization'?'selected':''}>5 - Finalization</option>
                <option value="6 - RFS" ${d.pipelineStage==='6 - RFS'?'selected':''}>6 - RFS</option>
             </select>
           </div>
           <div class="field" style="margin:0;"><label>Progress (%)</label><input type="number" id="m-progress" min="0" max="100" value="${d.progressPct || 0}"></div>
        </div>

        <div class="grid3">
          <div class="field"><label>Prioritas</label>
            <select id="m-priority">${['Medium','High','Urgent'].map(x=>`<option ${d.priority===x?'selected':''}>${x}</option>`).join('')}</select>
          </div>
          <div class="field"><label>Status (Tutup Project)</label>
            <select id="m-status">
              <option value="ongoing" ${d.status==='ongoing'?'selected':''}>Berjalan</option>
              <option value="win" ${d.status==='win'?'selected':''}>Menang (Win)</option>
              <option value="lose" ${d.status==='lose'?'selected':''}>Kalah (Lose)</option>
            </select>
          </div>
          <div class="field"><label>Lead Presource</label>
            <select id="m-lead">${team.map(t=>`<option ${d.leadId===t?'selected':''}>${escAttr(t)}</option>`).join('')}</select>
          </div>
        </div>
        
        <div class="field"><label>Mode SPH</label>
          <select id="m-sphmode">
            <option value="item" ${d.sphMode==='item'?'selected':''}>Per item/produk</option>
            <option value="project" ${d.sphMode==='project'?'selected':''}>Total project saja</option>
          </select>
        </div>
        <div id="m-project-sph" style="${d.sphMode==='project'?'':'display:none'}">
          <div class="grid2">
            <div class="field"><label>SPH Awal (total)</label><input type="number" id="m-proj-awal" value="${d.projectSphAwal??''}"></div>
            <div class="field"><label>SPH Final (total)</label><input type="number" id="m-proj-final" value="${d.projectSphFinal??''}"></div>
          </div>
        </div>
        <div id="sows-container">${d.sows.map((sow,si)=>sowBlockHtml(sow,si)).join('')}</div>
        <button class="mini-btn" id="m-add-sow" type="button">+ Tambah SoW</button>
      </div>
      <div class="modal-ft">
        <button class="btn-ghost" id="m-cancel" type="button">Batal</button>
        <button class="btn-primary" id="m-save" type="button">Simpan</button>
      </div>
    </div>
  </div>`;
}

function sowBlockHtml(sow, si){
  return `<div class="sow-block" data-sow-idx="${si}">
    <div class="field"><label>Scope of Work</label><input class="sow-name" data-si="${si}" value="${escAttr(sow.name)}"></div>
    ${sow.boqs.map((boq,bi)=>boqBlockHtml(boq,si,bi)).join('')}
    <button class="mini-btn" data-add-boq="${si}" type="button">+ Tambah BoQ</button>
    <button class="mini-btn danger" data-del-sow="${si}" type="button" style="float:right;">Hapus SoW</button>
  </div>`;
}
function boqBlockHtml(boq, si, bi){
  return `<div class="boq-block" data-boq-idx="${bi}">
    <div class="field"><label>Bill of Quantity</label><input class="boq-name" data-si="${si}" data-bi="${bi}" value="${escAttr(boq.name)}"></div>
    ${boq.items.map((it,ii)=>itemBlockHtml(it,si,bi,ii)).join('')}
    <button class="mini-btn" data-add-item="${si}:${bi}" type="button">+ Tambah item/produk</button>
    <button class="mini-btn danger" data-del-boq="${si}:${bi}" type="button" style="float:right;">Hapus BoQ</button>
  </div>`;
}
function itemBlockHtml(it, si, bi, ii){
  return `<div class="item-block" data-item-idx="${ii}">
    <div style="display:grid; grid-template-columns: 2fr 0.4fr 0.6fr 1.5fr; gap:12px; margin-bottom:12px;">
      <div class="field" style="margin:0;"><label>Produk</label><input class="it-product" data-path="${si}:${bi}:${ii}" value="${escAttr(it.product)}"></div>
      <div class="field" style="margin:0;"><label>Qty</label><input type="number" class="it-qty" data-path="${si}:${bi}:${ii}" value="${it.qty??1}"></div>
      <div class="field" style="margin:0;"><label>UoM</label><input class="it-uom" data-path="${si}:${bi}:${ii}" value="${escAttr(it.uom)}"></div>
      <div class="field" style="margin:0;"><label>Vendor</label><input class="it-vendor" data-path="${si}:${bi}:${ii}" value="${escAttr(it.vendor)}"></div>
    </div>
    <div class="grid3">
      <div class="field"><label>SPH Awal item</label><input type="number" class="it-awal" data-path="${si}:${bi}:${ii}" value="${it.sphAwal??''}"></div>
      <div class="field"><label>SPH Final item</label><input type="number" class="it-final" data-path="${si}:${bi}:${ii}" value="${it.sphFinal??''}"></div>
      <div class="field"><label>PIC</label><div class="pic-select">${team.map(t=>`<div class="pic-opt ${it.picIds.includes(t)?'on':''}" data-pic="${si}:${bi}:${ii}:${escAttr(t)}">${escAttr(t)}</div>`).join('')}</div></div>
    </div>
  </div>`;
}
function teamModalHtml(d){
  return `<div class="overlay" id="ov" style="z-index: 100;"><div class="modal" style="max-width:480px;"><div class="modal-hd"><h3>Kelola tim</h3><button class="mini-btn" id="m-close">Tutup</button></div>
    <div class="modal-body"><textarea id="m-team-names" rows="4">${escAttr(d.names)}</textarea></div>
    <div class="modal-ft"><button class="btn-ghost" id="m-cancel">Batal</button><button class="btn-primary" id="m-save-team">Simpan</button></div>
  </div></div>`;
}

function syncModalData() {
  if(!modal || modal.type !== 'project') return;
  const m = document.querySelector('.modal');
  if(m) modalScroll = m.scrollTop;
  const d = modal.data;
  d.name = val('m-name'); d.requestorName = val('m-req-name'); d.requestorDept = val('m-req-dept');
  d.priority = val('m-priority'); d.status = val('m-status'); d.leadId = val('m-lead');
  d.targetRfs = val('m-target-rfs'); d.pipelineStage = val('m-pipeline-stage'); d.progressPct = numOrNull(val('m-progress')) || 0;
  d.sphMode = val('m-sphmode');
  if(d.sphMode==='project'){
    d.projectSphAwal = numOrNull(document.getElementById('m-proj-awal').value);
    d.projectSphFinal = numOrNull(document.getElementById('m-proj-final').value);
  }
  document.querySelectorAll('.sow-name').forEach(el=> d.sows[+el.dataset.si].name = el.value);
  document.querySelectorAll('.boq-name').forEach(el=> d.sows[+el.dataset.si].boqs[+el.dataset.bi].name = el.value);
  document.querySelectorAll('.it-qty').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].qty = numOrNull(el.value); });
  document.querySelectorAll('.it-uom').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].uom = el.value; });
  document.querySelectorAll('.it-vendor').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].vendor = el.value; });
  document.querySelectorAll('.it-product').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].product = el.value; });
  document.querySelectorAll('.it-awal').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].sphAwal = numOrNull(el.value); });
  document.querySelectorAll('.it-final').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].sphFinal = numOrNull(el.value); });
}

function wireModalEvents(){
  if (!modal) return;
  const close = ()=>{ modal=null; document.getElementById('modal-root').innerHTML=''; render(); };
  const c1 = document.getElementById('m-close'); if(c1) c1.onclick = close;
  const c2 = document.getElementById('m-cancel'); if(c2) c2.onclick = close;
  const ov = document.getElementById('ov'); if(ov) ov.onclick = (e) => { if(e.target === ov) close(); };

  if(modal.type==='team'){
    const sBtn = document.getElementById('m-save-team');
    if(sBtn) sBtn.onclick = ()=>{ team = val('m-team-names').split(',').map(s=>s.trim()).filter(Boolean); modal=null; render(); saveAll(); };
    return;
  }
  const sphmode = document.getElementById('m-sphmode');
  if(sphmode) sphmode.onchange = ()=>{ syncModalData(); modal.data.sphMode = sphmode.value; render(); };

  document.getElementById('m-add-sow').onclick = ()=>{
    syncModalData(); modal.data.sows.push({id:uid('sow'), name:'', boqs:[{id:uid('boq'), name:'', items:[{id:uid('item'), product:'', qty:1, vendor:'', picIds:[], sphAwal:null, sphFinal:null}]}]}); render();
  };
  document.querySelectorAll('[data-add-boq]').forEach(el=> el.onclick=()=>{ syncModalData(); modal.data.sows[+el.dataset.addBoq].boqs.push({id:uid('boq'), name:'', items:[{id:uid('item'), product:'', qty:1, vendor:'', picIds:[], sphAwal:null, sphFinal:null}]}); render(); });
  document.querySelectorAll('[data-add-item]').forEach(el=>{ const [si,bi] = el.dataset.addItem.split(':').map(Number); el.onclick = ()=>{ syncModalData(); modal.data.sows[si].boqs[bi].items.push({id:uid('item'), product:'', qty:1, vendor:'', picIds:[], sphAwal:null, sphFinal:null}); render(); }; });
  document.querySelectorAll('[data-del-sow]').forEach(el=> el.onclick=()=>{ syncModalData(); modal.data.sows.splice(+el.dataset.delSow,1); render(); });
  document.querySelectorAll('[data-del-boq]').forEach(el=>{ const [si,bi] = el.dataset.delBoq.split(':').map(Number); el.onclick=()=>{ syncModalData(); modal.data.sows[si].boqs.splice(bi,1); render(); }; });
  document.querySelectorAll('[data-del-item]').forEach(el=>{ const [si,bi,ii] = el.dataset.delItem.split(':').map(Number); el.onclick=()=>{ syncModalData(); modal.data.sows[si].boqs[bi].items.splice(ii,1); render(); }; });
  document.querySelectorAll('[data-pic]').forEach(el=>{
    const [si,bi,ii,name] = el.dataset.pic.split(':');
    el.onclick = ()=>{ syncModalData(); const arr = modal.data.sows[+si].boqs[+bi].items[+ii].picIds; const idx = arr.indexOf(name); if(idx>=0) arr.splice(idx,1); else arr.push(name); render(); };
  });

  document.getElementById('m-save').onclick = ()=>{
    syncModalData(); const d = modal.data; const idx = projects.findIndex(p=>p.id===d.id);
    if(idx>=0) projects[idx]=d; else projects.push(d);
    document.getElementById('modal-root').innerHTML = ''; modal = null; render(); saveAll();
  };
}

function val(id){ const el=document.getElementById(id); return el?el.value:''; }
function numOrNull(v){ return (v===''||v==null) ? null : Number(v); }

function openUploadPembandingModal(projectId) {
    const modalHtml = `
        <div class="overlay" id="upload-pembanding-modal" style="z-index: 100;">
            <div class="modal" style="max-width: 420px;">
                <div class="modal-hd">
                    <h3>Unggah SPH Pembanding</h3>
                    <button class="btn-ghost" style="padding: 4px 8px;" onclick="closeUploadPembandingModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="field"><label>Nama Vendor</label><input type="text" id="up-vendor-name"></div>
                    <div class="field"><label>Harga Penawaran SPH</label><input type="number" id="up-vendor-price"></div>
                    <div class="field"><label>Lampiran File</label><input type="file" id="up-vendor-file" accept=".pdf, .xls, .xlsx, .jpg, .png"></div>
                </div>
                <div class="modal-ft">
                    <button class="btn-ghost" onclick="closeUploadPembandingModal()">Batal</button>
                    <button class="btn-primary" onclick="submitUploadPembanding('${projectId}')">Simpan</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}
function closeUploadPembandingModal() { const m = document.getElementById('upload-pembanding-modal'); if (m) m.remove(); }
async function submitUploadPembanding(projectId) {
    const name = document.getElementById('up-vendor-name').value;
    const price = document.getElementById('up-vendor-price').value;
    const file = document.getElementById('up-vendor-file').files[0];
    if (!name || !price || !file) { alert("Semua kolom wajib diisi!"); return; }
    const formData = new FormData();
    formData.append('ticket_id', projectId); formData.append('vendor_name', name);
    formData.append('offered_price', price); formData.append('file', file);
    document.body.style.cursor = 'wait';
    try {
        const res = await fetch('/api/upload_comparison', { method: 'POST', body: formData });
        const result = await res.json();
        if (res.ok && result.success) { alert("Dokumen berhasil ditambahkan!"); closeUploadPembandingModal(); loadAll(); } 
        else alert(`Gagal: ${result.message}`);
    } catch (err) {
        alert("Terjadi kesalahan sistem."); closeUploadPembandingModal();
    } finally { document.body.style.cursor = 'default'; }
}

loadAll();