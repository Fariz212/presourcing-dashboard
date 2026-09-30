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

// ---------- Navigation Logic ----------
function switchDashboardTab(id) {
  activeTab = id;
  openProjectId = null;
  document.querySelectorAll('.app-nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === id);
  });
  render();
}

function render(){
  const app = document.getElementById('app');
  let headerHtml = '';

  // HEADER LOGIC
  if(activeTab === 'overview'){
    const now = new Date();
    const dateText = now.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' });
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
          <div class="data-date">
            <span>Data per:</span>
            <strong>${dateText}</strong>
          </div>
        </div>
      </div>
    `;
  } 
  else if(activeTab === 'projects'){
    headerHtml = `
      <div class="page-hero">
        <div class="page-hero-main">
          <div class="page-hero-title">Project &amp; BoQ Management</div>
          <div class="page-hero-sub">Detail project, BoQ, SPH, dan progress</div>
        </div>
      </div>
    `;
  } else if(activeTab === 'team'){
    headerHtml = `
      <div class="page-hero">
        <div class="page-hero-main">
          <div class="page-hero-title">Team &amp; Workload</div>
          <div class="page-hero-sub">Distribusi project dan beban kerja tim</div>
        </div>
      </div>
    `;
  }

  app.innerHTML = `
    <div class="page-shell">
      ${headerHtml}
      <div id="tabcontent"></div>
    </div>
  `;

  const content = document.getElementById('tabcontent');
  if(activeTab === 'overview') content.innerHTML = renderOverview();
  else if(activeTab === 'projects') content.innerHTML = renderProjects();
  else if(activeTab === 'team') content.innerHTML = renderTeam();

  wireEvents();
  if(modal) renderModal();

  // Set active nav state on first render
  document.querySelectorAll('.app-nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === activeTab);
  });
}

// --------------------------------------------------------
// RENDER OVERVIEW: EXECUTIVE DASHBOARD
// --------------------------------------------------------
function renderOverview(){
  const totalProj = projects.length;
  let totalVal = 0;
  
  const sCount = { 'On Track': 0, 'At Risk': 0, 'Overdue': 0, 'Completed': 0, 'Planned': 0 };
  const pCount = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0 };

  // Hitung Nilai dan Status untuk SEMUA project
  projects.forEach(p => {
    totalVal += (projectSph(p).awal || 0);
    const status = getDynamicStatus(p);
    if(sCount[status] !== undefined) sCount[status]++;
  });

  // Filter HANYA project yang aktif untuk perhitungan Pipeline
  const activeProjectsData = projects.filter(p => p.status === 'ongoing');
  const activeProjects = activeProjectsData.length;

  // Hitung posisi Pipeline (Diskrit)
  activeProjectsData.forEach(p => {
    let stage = parseInt(String(p.pipelineStage || '').charAt(0));
    
    // Jika format pipeline kosong / bukan angka standar (misal: "- (0%)"), 
    // asumsikan project baru masuk dan tempatkan di Stage 1
    if(isNaN(stage) || stage < 1 || stage > 6){
      stage = 1;
    }
    
    // Tambahkan +1 HANYA pada stage tempat project tersebut berada saat ini
    pCount[stage]++;
  });

  const efficiencies = projects.map(p => efficiencyPct(projectSph(p).awal, projectSph(p).final)).filter(v => v != null && isFinite(v));
  const avgEfficiency = efficiencies.length ? efficiencies.reduce((a,b) => a+b, 0) / efficiencies.length : null;
  
  const getPct = val => totalProj ? Math.round((val / totalProj) * 100) : 0;
  
  // (Variabel activeProjects sudah dideklarasikan di atas, sehingga deklarasi lamanya dihapus dari sini)
  const atRisk = sCount['At Risk'];
  const overdue = sCount['Overdue'];

  if(!window.Chart && !document.getElementById('chartjs-script')){
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
    
    /* HERO */
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

    /* KPI */
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

    /* MAIN EXECUTIVE GRID */
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

    /* TABLE */
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

    /* CHARTS */
    .exec-chart{ height:155px; position:relative; width:100%; }
    .exec-chart.tall{ height:170px; }
    .exec-chart canvas{ width:100% !important; height:100% !important; }
    .exec-donut{ height:170px; position:relative; }
    .exec-donut canvas{ width:100% !important; height:100% !important; }
    .exec-donut-center{ position:absolute; left:37%; top:50%; transform: translate(-50%,-50%); text-align:center; pointer-events:none; }
    .exec-donut-number{ font-size:22px; line-height:1; font-weight:700; color:#0F172A; }
    .exec-donut-label{ margin-top:2px; font-size:8px; color:#64748B; }

    /* EARLY WARNING */
    .warning-summary{ display:grid; grid-template-columns:1fr 1fr; gap:6px; padding:7px; background:#FFFBEB; border-bottom: 1px solid #FDE68A; }
    .warning-box{ padding:5px 7px; background:#fff; border: 1px solid #FDE68A; border-radius:5px; }
    .warning-label{ font-size:7.5px; color:#92400E; font-weight:700; text-transform:uppercase; }
    .warning-value{ margin-top:1px; font-size:15px; line-height:1; font-weight:700; color:#78350F; }

    /* PIPELINE */
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

    /* RESPONSIVE */
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

  const sortedProjects = [...projects].sort((a,b) => new Date(a.targetRfs || '2099-12-31') - new Date(b.targetRfs || '2099-12-31'));
  let overviewRows = '';

  sortedProjects.forEach((p, idx) => {
    const sph = projectSph(p);
    const progress = Math.max(0, Math.min(100, Number(p.progressPct) || 0));
    const rfs = p.targetRfs ? new Date(p.targetRfs).toLocaleDateString('id-ID', {day:'2-digit', month:'short', year:'numeric'}) : '—';

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

  if(!overviewRows) overviewRows = `<tr><td colspan="7" style="text-align:center; padding:25px; color:#94A3B8;">Belum ada project.</td></tr>`;

  const warningProjects = sortedProjects.filter(p => ['Overdue','At Risk'].includes(getDynamicStatus(p)));
  let warningRows = '';

  warningProjects.slice(0,5).forEach(p => {
    const progress = Number(p.progressPct) || 0;
    const rfs = p.targetRfs ? new Date(p.targetRfs).toLocaleDateString('id-ID', {day:'2-digit', month:'short'}) : '—';
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

  if(!warningRows) warningRows = `<tr><td colspan="4" style="text-align:center; padding:18px; color:#15803D;">✓ Tidak ada project yang perlu perhatian</td></tr>`;

 const pNames = ['Project Identification', 'SPH Preparation', 'Vendor Selection', 'Negotiation', 'Finalization', 'RFS'];
  let pipelineHtml = '';

  pNames.forEach((name, i) => {
    const n = i + 1;
    const count = pCount[n];
    
    // UBAH BARIS INI: Gunakan activeProjects sebagai pembagi persentase
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
      <div class="exec-kpi">
        <div class="exec-kpi-icon" style="color:#0284C7;">▣</div>
        <div>
          <div class="exec-kpi-label">Total Project</div>
          <div class="exec-kpi-value">${totalProj}</div>
          <div class="exec-kpi-meta">${activeProjects} active projects</div>
        </div>
      </div>
      <div class="exec-kpi">
        <div class="exec-kpi-icon" style="color:#4F46E5;">◉</div>
        <div>
          <div class="exec-kpi-label">Total Project Value</div>
          <div class="exec-kpi-value" style="font-size:15px;">Rp ${valToM(totalVal)} M</div>
          <div class="exec-kpi-meta">Est. project value</div>
        </div>
      </div>
      <div class="exec-kpi green">
        <div class="exec-kpi-icon" style="color:#16A34A; background:#F0FDF4;">✓</div>
        <div style="width:100%;">
          <div class="exec-kpi-label">On Track</div>
          <div class="exec-kpi-value">${sCount['On Track']} <small>${getPct(sCount['On Track'])}%</small></div>
          <div class="exec-kpi-progress"><span style="width:${getPct(sCount['On Track'])}%; background:#16A34A;"></span></div>
        </div>
      </div>
      <div class="exec-kpi yellow">
        <div class="exec-kpi-icon" style="color:#D97706; background:#FFFBEB;">!</div>
        <div style="width:100%;">
          <div class="exec-kpi-label">At Risk</div>
          <div class="exec-kpi-value">${atRisk} <small style="color:#D97706;">${getPct(atRisk)}%</small></div>
          <div class="exec-kpi-progress"><span style="width:${getPct(atRisk)}%; background:#F59E0B;"></span></div>
        </div>
      </div>
      <div class="exec-kpi red">
        <div class="exec-kpi-icon" style="color:#DC2626; background:#FEF2F2;">!</div>
        <div style="width:100%;">
          <div class="exec-kpi-label">Overdue</div>
          <div class="exec-kpi-value">${overdue} <small style="color:#DC2626;">${getPct(overdue)}%</small></div>
          <div class="exec-kpi-progress"><span style="width:${getPct(overdue)}%; background:#DC2626;"></span></div>
        </div>
      </div>
      <div class="exec-kpi gray">
        <div class="exec-kpi-icon" style="color:#475569; background:#F8FAFC;">↗</div>
        <div>
          <div class="exec-kpi-label">Avg Efficiency</div>
          <div class="exec-kpi-value">${fmtPct(avgEfficiency)}</div>
          <div class="exec-kpi-meta">${efficiencies.length} project with data</div>
        </div>
      </div>
    </div>

    <div class="exec-grid">
      <div class="exec-panel overview">
        <div class="exec-panel-head">▣ <span>Project Presourcing Overview</span><span class="exec-panel-sub">${totalProj} Projects</span></div>
        <div class="exec-table-wrap">
          <table class="exec-table">
            <thead><tr><th>No</th><th>Project Name</th><th>Value</th><th>PIC</th><th>Target RFS</th><th>Status</th><th>Progress</th></tr></thead>
            <tbody>${overviewRows}</tbody>
          </table>
        </div>
      </div>

      <div class="exec-panel status">
        <div class="exec-panel-head">◉ <span>Project Status</span></div>
        <div class="exec-panel-body">
          <div class="exec-donut">
            <canvas id="chartStatus"></canvas>
            <div class="exec-donut-center">
              <div class="exec-donut-number">${totalProj}</div>
              <div class="exec-donut-label">Projects</div>
            </div>
          </div>
        </div>
      </div>

      <div class="exec-panel pic">
        <div class="exec-panel-head">▥ <span>Project Value by PIC</span></div>
        <div class="exec-panel-body">
          <div class="exec-chart"><canvas id="chartPicValue"></canvas></div>
        </div>
      </div>

      <div class="exec-panel pipeline">
        <div class="exec-panel-head">⇢ <span>Presourcing Progress Pipeline</span><span class="exec-panel-sub">${activeProjects} active</span></div>
        <div class="exec-panel-body">
          <div class="pipeline-flow">${pipelineHtml}</div>
        </div>
      </div>

      <div class="exec-panel rfs">
        <div class="exec-panel-head">▥ <span>Target RFS by Month</span></div>
        <div class="exec-panel-body">
          <div class="exec-chart"><canvas id="chartRfsMonth"></canvas></div>
        </div>
      </div>

      <div class="exec-panel top5">
        <div class="exec-panel-head">≡ <span>Top 5 Project Value</span></div>
        <div class="exec-panel-body">
          <div class="exec-chart"><canvas id="chartTop5"></canvas></div>
        </div>
      </div>

      <div class="exec-panel warning">
        <div class="exec-panel-head warning-head">! <span>Early Warning</span><span class="exec-panel-sub">Need Attention</span></div>
        <div class="warning-summary">
          <div class="warning-box"><div class="warning-label">Overdue</div><div class="warning-value">${overdue}</div></div>
          <div class="warning-box"><div class="warning-label">At Risk</div><div class="warning-value">${atRisk}</div></div>
        </div>
        <div class="exec-table-wrap">
          <table class="exec-table">
            <thead><tr><th>Project</th><th>RFS</th><th>Progress</th><th>Status</th></tr></thead>
            <tbody>${warningRows}</tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

let dCharts = {}; 

function renderDashboardCharts() {
    if (typeof Chart === 'undefined') return;

    const chartFont = { family: "'Inter', 'Segoe UI', Arial, sans-serif", size: 10 };
    const axisColor = '#64748b';
    const gridColor = '#eef2f7';
    const primarySoft = '#93c5fd';
    const dark = '#0f172a';

    const destroyChart = (key) => {
        if (dCharts[key]) { dCharts[key].destroy(); dCharts[key] = null; }
    };
    const fmtRpM = (value) => `Rp ${(Number(value) || 0).toLocaleString('id-ID', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} M`;

    // 1. PROJECT STATUS (DONUT)
    const statusLabels = ['On Track', 'At Risk', 'Overdue', 'Completed', 'Planned'];
    const statusColors = ['#16a34a', '#f59e0b', '#dc2626', '#2563eb', '#cbd5e1'];
    const sCount = { 'On Track': 0, 'At Risk': 0, 'Overdue': 0, 'Completed': 0, 'Planned': 0 };

    projects.forEach(p => {
        const status = getDynamicStatus(p);
        if (sCount[status] !== undefined) sCount[status]++;
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
                    borderWidth: 0, hoverOffset: 4
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: '72%',
                layout: { padding: 4 },
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { usePointStyle: true, pointStyle: 'circle', boxWidth: 7, boxHeight: 7, padding: 12, color: axisColor, font: chartFont }
                    },
                    tooltip: {
                        padding: 10,
                        callbacks: {
                            label: function(ctx) {
                                if (!hasStatusData) return ' Belum ada data';
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

    // 2. TARGET RFS BY MONTH (MIXED BAR/LINE)
    const rfsData = {};
    projects.forEach(p => {
        if (!p.targetRfs) return;
        const d = new Date(p.targetRfs);
        if (isNaN(d.getTime())) return;
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Ags', 'Sep', 'Okt', 'Nov', 'Des'];
        const key = `${months[d.getMonth()]} ${d.getFullYear()}`;
        const sortK = d.getFullYear() * 100 + d.getMonth();

        if (!rfsData[key]) rfsData[key] = { count: 0, val: 0, sortK };
        rfsData[key].count += 1;
        rfsData[key].val += (projectSph(p).awal || 0);
    });

    const rfsKeys = Object.keys(rfsData).sort((a, b) => rfsData[a].sortK - rfsData[b].sortK);
    const ctxRfs = document.getElementById('chartRfsMonth');

    if (ctxRfs) {
        destroyChart('rfsMonth');
        dCharts.rfsMonth = new Chart(ctxRfs, {
            type: 'bar',
            data: {
                labels: rfsKeys,
                datasets: [
                    { type: 'bar', label: 'Jumlah Project', data: rfsKeys.map(k => rfsData[k].count), backgroundColor: primarySoft, borderColor: primarySoft, borderWidth: 0, borderRadius: 5, barPercentage: 0.6, categoryPercentage: 0.7, yAxisID: 'y' },
                    { type: 'line', label: 'Project Value', data: rfsKeys.map(k => Number((rfsData[k].val / 1000000000).toFixed(1))), borderColor: dark, backgroundColor: dark, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, tension: 0.3, fill: false, yAxisID: 'y1' }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { grid: { display: false }, border: { display: false }, ticks: { color: axisColor, font: chartFont, maxRotation: 0, autoSkip: true } },
                    y: { beginAtZero: true, ticks: { color: axisColor, font: chartFont, precision: 0, stepSize: 1 }, grid: { color: gridColor }, border: { display: false } },
                    y1: { beginAtZero: true, position: 'right', ticks: { color: axisColor, font: chartFont, callback: value => `Rp ${value} M` }, grid: { drawOnChartArea: false }, border: { display: false } }
                },
                plugins: {
                    legend: { position: 'bottom', labels: { usePointStyle: true, pointStyle: 'circle', boxWidth: 7, boxHeight: 7, padding: 14, color: axisColor, font: chartFont } },
                    tooltip: { padding: 10, callbacks: { label: function(ctx) { return ctx.dataset.label === 'Jumlah Project' ? ` ${ctx.raw} project` : ` ${fmtRpM(ctx.raw)}`; } } }
                }
            }
        });
    }

    // 3. TOP 5 PROJECT VALUE (HORIZONTAL BAR)
    const top5 = [...projects]
        .filter(p => p.status !== 'lose')
        .map(p => ({ name: p.name || 'Unnamed Project', val: Number(((projectSph(p).awal || 0) / 1000000000).toFixed(1)) }))
        .sort((a, b) => b.val - a.val)
        .slice(0, 5);

    const ctxTop5 = document.getElementById('chartTop5');
    if (ctxTop5) {
        destroyChart('top5');
        dCharts.top5 = new Chart(ctxTop5, {
            type: 'bar',
            data: {
                labels: top5.map(t => t.name.length > 24 ? t.name.substring(0, 24) + '...' : t.name),
                datasets: [{ label: 'Project Value', data: top5.map(t => t.val), backgroundColor: '#2563EB', borderWidth: 0, borderRadius: 5, barPercentage: 0.55, categoryPercentage: 0.72 }]
            },
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                layout: { padding: { left: 4, right: 10, top: 4, bottom: 2 } },
                scales: {
                    x: { beginAtZero: true, grid: { color: '#EEF2F7' }, border: { display: false }, ticks: { color: '#94A3B8', font: { family: "'Space Grotesk', sans-serif", size: 9 }, callback: value => `Rp ${value} M` } },
                    y: { grid: { display: false }, border: { display: false }, ticks: { color: '#475569', font: { family: "'Space Grotesk', sans-serif", size: 9.5, weight: '500' } } }
                },
                plugins: { legend: { display: false }, tooltip: { padding: 9, callbacks: { label: ctx => ` Rp ${Number(ctx.raw).toLocaleString('id-ID')} M` } } }
            }
        });
    }

    // 4. PROJECT VALUE BY PIC (HORIZONTAL BAR)
    const picValData = {};
    team.forEach(m => picValData[m] = 0);
    projects.forEach(p => {
        if (!p.leadId) return;
        if (picValData[p.leadId] === undefined) picValData[p.leadId] = 0;
        picValData[p.leadId] += ((projectSph(p).awal || 0) / 1000000000);
    });

    const picData = Object.entries(picValData)
        .map(([name, value]) => ({ name, value: Number(value.toFixed(1)) }))
        .filter(x => x.value > 0)
        .sort((a, b) => b.value - a.value);

    const ctxPic = document.getElementById('chartPicValue');
    if (ctxPic) {
        destroyChart('picVal');
        dCharts.picVal = new Chart(ctxPic, {
            type: 'bar',
            data: {
                labels: picData.map(x => x.name),
                datasets: [{ label: 'Project Value', data: picData.map(x => x.value), backgroundColor: '#3b82f6', borderWidth: 0, borderRadius: 5, barPercentage: 0.58, categoryPercentage: 0.72 }]
            },
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { beginAtZero: true, grid: { color: gridColor }, border: { display: false }, ticks: { color: axisColor, font: chartFont, callback: value => `Rp ${value} M` } },
                    y: { grid: { display: false }, border: { display: false }, ticks: { color: '#334155', font: { ...chartFont, weight: '500' } } }
                },
                plugins: { legend: { display: false }, tooltip: { padding: 10, callbacks: { label: ctx => ` ${fmtRpM(ctx.raw)}` } } }
            }
        });
    }
}

// --------------------------------------------------------
// RENDER DETAIL PROJECTS & TEAM 
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
          <thead><tr><th>Project</th><th>Pemohon</th><th>Status EWS</th><th>Tahap Pipeline</th><th class="num">SPH Awal</th><th class="num">Efficiency</th><th class="num">Durasi</th></tr></thead>
          <tbody>${tbodyHtml}</tbody>
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
                    <div><span style="font-weight:600; color:var(--text);">${escAttr(doc.vendor_name)}</span> <span style="color:var(--text-muted);"> — Penawaran: <span class="mono">${fmtIdr(doc.offered_price)}</span></span></div>
                    <a href="${doc.file_path}" target="_blank" style="color: var(--primary); text-decoration: none; font-weight:500;">Lihat File</a>
                </div>
            `).join('') : '<div style="font-size:11.5px; color:var(--text-muted);">Belum ada dokumen pembanding yang diunggah.</div>'
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
      (boq.items || []).forEach(it => {
        const eff = p.sphMode === 'item' ? efficiencyPct(it.sphAwal, it.sphFinal) : null;
        const notesHtml = it.notes ? `<div style="font-size:11px; color:var(--text-muted); margin-top:3px;">📝 ${escAttr(it.notes)}</div>` : '';
        const picsHtml = (it.picIds || []).map(x => `<span class="pic-chip">${escAttr(x)}</span>`).join('');
        sowsHtml += `
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
          <thead><tr><th>Anggota</th><th class="num">Lead Count</th><th class="num">Support Load</th><th class="num">Win Rate</th><th class="num">Avg Efficiency</th></tr></thead>
          <tbody>
          ${rows.map(r=>`<tr><td>${escAttr(r.name)}</td><td class="num mono">${r.leadCount}</td><td class="num mono">${r.supportLoad.toFixed(2)}</td><td class="num mono">${fmtPct(r.winRate)}</td><td class="num mono">${fmtPct(r.avgEff)}</td></tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ---------- Event Wirings ----------
function wireEvents(){
  const fp = document.getElementById('f-priority');
  if(fp){ fp.value=filters.priority; fp.onchange=()=>{filters.priority=fp.value; render();}; }
  
  const fs = document.getElementById('f-status');
  if(fs){ fs.value=filters.status; fs.onchange=()=>{filters.status=fs.value; render();}; }
  
  document.querySelectorAll('[data-open]').forEach(el=> el.onclick = ()=>{ const id=el.dataset.open; openProjectId = openProjectId===id?null:id; render(); });
  
  const btnNew = document.getElementById('btn-new-project');
  if(btnNew) btnNew.onclick = ()=> openProjectModal(null);
  
  document.querySelectorAll('[data-edit-project]').forEach(el=> el.onclick=(e)=>{ e.stopPropagation(); openProjectModal(el.dataset.editProject); });
  document.querySelectorAll('[data-delete-project]').forEach(el=> el.onclick=(e)=>{ e.stopPropagation(); if(confirm('Hapus project ini?')){ projects = projects.filter(p=>p.id!==el.dataset.deleteProject); saveAll(); render(); } });
  
  const btnTeam = document.getElementById('btn-manage-team');
  if(btnTeam) btnTeam.onclick = ()=> openTeamModal();
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

// ---------- Modals ----------
function blankProject(){
  return {
    id: uid('proj'), name:'', requestorName:'', requestorDept:'', priority:'Medium', status:'ongoing', leadId: team[0]||'', sphMode:'item', projectSphAwal:null, projectSphFinal:null,
    createdAt: todayStr(), closedAt:null, targetRfs: '', pipelineStage: '1 - Project Identification', progressPct: 0, comparison_docs: [],
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

  const totalSows =
    (d.sows || []).length;

  const totalBoqs =
    (d.sows || []).reduce(
      (sum, sow) =>
        sum + (sow.boqs || []).length,
      0
    );

  const totalItems =
    (d.sows || []).reduce(
      (sum, sow) =>
        sum +
        (sow.boqs || []).reduce(
          (bSum, boq) =>
            bSum + (boq.items || []).length,
          0
        ),
      0
    );

  return `
  <div
    class="overlay"
    id="ov"
    style="z-index:100;">

    <div
      class="modal project-modal">

      <!-- HEADER -->

      <div class="modal-hd">

        <div>

          <h3>
            ${isNew ? 'Project baru' : 'Edit project'}
          </h3>

          <div
            style="
              margin-top:3px;
              font-size:9px;
              color:#94A3B8;">

            ${isNew
              ? 'Tambahkan project baru ke portfolio presourcing'
              : 'Perbarui informasi dan detail project'}

          </div>

        </div>

        <button
          class="mini-btn"
          id="m-close"
          type="button">

          Tutup

        </button>

      </div>


      <!-- BODY -->

      <div class="modal-body">


        <!-- ==========================================
             01 PROJECT INFORMATION
        =========================================== -->

        <div class="form-section">

          <div class="form-section-head">

            <div class="form-section-title">
              01 · Project Information
            </div>

            <div class="form-section-note">
              Basic project information
            </div>

          </div>


          <div
            class="field project-name-field">

            <label class="required-mark">
              Nama project
            </label>

            <input
              id="m-name"
              value="${escAttr(d.name)}"
              placeholder="Masukkan nama project">

          </div>


          <div class="grid2">

            <div class="field">

              <label>
                Nama pemohon (SA)
              </label>

              <input
                id="m-req-name"
                value="${escAttr(d.requestorName)}"
                placeholder="Nama requester">

            </div>


            <div class="field">

              <label>
                Departemen
              </label>

              <input
                id="m-req-dept"
                value="${escAttr(d.requestorDept)}"
                placeholder="Departemen">

            </div>

          </div>

        </div>


        <!-- ==========================================
             02 EXECUTION
        =========================================== -->

        <div class="form-section">

          <div class="form-section-head">

            <div class="form-section-title">
              02 · Execution
            </div>

            <div class="form-section-note">
              Schedule, pipeline &amp; ownership
            </div>

          </div>


          <div class="execution-box">

            <div class="grid3">

              <div class="field">

                <label class="required-mark">
                  Target RFS
                </label>

                <input
                  type="date"
                  id="m-target-rfs"
                  value="${escAttr(d.targetRfs)}">

              </div>


              <div class="field">

                <label>
                  Tahap Pipeline
                </label>

                <select id="m-pipeline-stage">

                  <option value="1 - Project Identification"
                    ${d.pipelineStage==='1 - Project Identification'?'selected':''}>
                    1 - Identification
                  </option>

                  <option value="2 - SPH Preparation"
                    ${d.pipelineStage==='2 - SPH Preparation'?'selected':''}>
                    2 - SPH Preparation
                  </option>

                  <option value="3 - Vendor Selection"
                    ${d.pipelineStage==='3 - Vendor Selection'?'selected':''}>
                    3 - Vendor Selection
                  </option>

                  <option value="4 - Negotiation"
                    ${d.pipelineStage==='4 - Negotiation'?'selected':''}>
                    4 - Negotiation
                  </option>

                  <option value="5 - Finalization"
                    ${d.pipelineStage==='5 - Finalization'?'selected':''}>
                    5 - Finalization
                  </option>

                  <option value="6 - RFS"
                    ${d.pipelineStage==='6 - RFS'?'selected':''}>
                    6 - RFS
                  </option>

                </select>

              </div>


              <div class="field">

                <label>
                  Progress (%)
                </label>

                <input
                  type="number"
                  id="m-progress"
                  min="0"
                  max="100"
                  value="${d.progressPct || 0}">

              </div>

            </div>


            <div class="grid3">

              <div class="field">

                <label>
                  Prioritas
                </label>

                <select id="m-priority">

                  ${['Medium','High','Urgent']
                    .map(x => `
                      <option
                        ${d.priority === x ? 'selected' : ''}>
                        ${x}
                      </option>
                    `)
                    .join('')}

                </select>

              </div>


              <div class="field">

                <label>
                  Status
                </label>

                <select id="m-status">

                  <option
                    value="ongoing"
                    ${d.status==='ongoing'?'selected':''}>
                    Berjalan
                  </option>

                  <option
                    value="win"
                    ${d.status==='win'?'selected':''}>
                    Menang (Win)
                  </option>

                  <option
                    value="lose"
                    ${d.status==='lose'?'selected':''}>
                    Kalah (Lose)
                  </option>

                </select>

              </div>


              <div class="field">

                <label>
                  Lead Presource
                </label>

                <select id="m-lead">

                  ${team
                    .map(t => `
                      <option
                        ${d.leadId===t?'selected':''}>
                        ${escAttr(t)}
                      </option>
                    `)
                    .join('')}

                </select>

              </div>

            </div>

          </div>

        </div>


        <!-- ==========================================
             03 SPH
        =========================================== -->

        <div class="form-section">

          <div class="form-section-head">

            <div class="form-section-title">
              03 · SPH
            </div>

            <div class="form-section-note">
              Pricing calculation mode
            </div>

          </div>


          <div class="field">

            <label>
              Mode SPH
            </label>

            <select id="m-sphmode">

              <option
                value="item"
                ${d.sphMode==='item'?'selected':''}>
                Per item / produk
              </option>

              <option
                value="project"
                ${d.sphMode==='project'?'selected':''}>
                Total project saja
              </option>

            </select>

          </div>


          <div
            id="m-project-sph"
            style="
              ${d.sphMode==='project'
                ? ''
                : 'display:none'}">

            <div class="sph-summary-box">

              <div class="field">

                <label>
                  SPH Awal (total)
                </label>

                <input
                  type="number"
                  id="m-proj-awal"
                  value="${d.projectSphAwal ?? ''}">

              </div>


              <div class="field">

                <label>
                  SPH Final (total)
                </label>

                <input
                  type="number"
                  id="m-proj-final"
                  value="${d.projectSphFinal ?? ''}">

              </div>

            </div>

          </div>

        </div>


        <!-- ==========================================
             04 SCOPE & BOQ
        =========================================== -->

        <div class="form-section">

          <div class="form-section-head">

            <div class="form-section-title">
              04 · Scope &amp; BoQ
            </div>

            <div class="form-section-note">
              ${totalSows} SoW · ${totalBoqs} BoQ · ${totalItems} Items
            </div>

          </div>


          <div id="sows-container">

            ${(d.sows || [])
              .map(
                (sow, si) =>
                  sowBlockHtml(sow, si)
              )
              .join('')}

          </div>


          <div class="add-row">

            <button
              class="mini-btn form-add-btn"
              id="m-add-sow"
              type="button">

              + Tambah Scope of Work

            </button>

          </div>

        </div>

      </div>


      <!-- FOOTER -->

      <div class="modal-ft">

        <div class="modal-summary">

          <div class="modal-summary-item">

            <span class="modal-summary-label">
              Scope
            </span>

            <span class="modal-summary-value">
              ${totalSows}
            </span>

          </div>


          <div class="modal-summary-divider"></div>


          <div class="modal-summary-item">

            <span class="modal-summary-label">
              BoQ
            </span>

            <span class="modal-summary-value">
              ${totalBoqs}
            </span>

          </div>


          <div class="modal-summary-divider"></div>


          <div class="modal-summary-item">

            <span class="modal-summary-label">
              Items
            </span>

            <span class="modal-summary-value">
              ${totalItems}
            </span>

          </div>

        </div>


        <button
          class="btn-ghost"
          id="m-cancel"
          type="button">

          Batal

        </button>


        <button
          class="btn-primary"
          id="m-save"
          type="button">

          ${isNew ? 'Simpan Project' : 'Simpan Perubahan'}

        </button>

      </div>

    </div>

  </div>
  `;
}

function sowBlockHtml(sow, si){

  return `
    <div
      class="sow-block"
      data-sow-idx="${si}">

      <div class="sow-head">

        <div class="sow-heading">

          <div class="sow-index">
            ${si + 1}
          </div>

          <div class="sow-heading-text">
            Scope of Work
          </div>

        </div>


        <div class="sow-actions">

          <button
            class="mini-btn danger form-danger-btn"
            data-del-sow="${si}"
            type="button">

            Hapus

          </button>

        </div>

      </div>


      <div class="field">

        <label class="required-mark">
          Nama Scope of Work
        </label>

        <input
          class="sow-name"
          data-si="${si}"
          value="${escAttr(sow.name)}"
          placeholder="Contoh: Network Deployment">

      </div>


      <div>

        ${(sow.boqs || [])
          .map(
            (boq, bi) =>
              boqBlockHtml(
                boq,
                si,
                bi
              )
          )
          .join('')}

      </div>


      <div class="add-row">

        <button
          class="mini-btn form-add-btn"
          data-add-boq="${si}"
          type="button">

          + Tambah BoQ

        </button>

      </div>

    </div>
  `;
}
function boqBlockHtml(boq, si, bi){

  return `
    <div
      class="boq-block"
      data-boq-idx="${bi}">

      <div class="boq-head">

        <div class="boq-heading">

          <div class="boq-number">
            ${bi + 1}
          </div>

          <div class="boq-title-text">
            Bill of Quantity
          </div>

        </div>


        <button
          class="mini-btn danger form-danger-btn"
          data-del-boq="${si}:${bi}"
          type="button">

          Hapus

        </button>

      </div>


      <div class="field">

        <label>
          Nama BoQ
        </label>

        <input
          class="boq-name"
          data-si="${si}"
          data-bi="${bi}"
          value="${escAttr(boq.name)}"
          placeholder="Nama paket / BoQ">

      </div>


      <div>

        ${(boq.items || [])
          .map(
            (it, ii) =>
              itemBlockHtml(
                it,
                si,
                bi,
                ii
              )
          )
          .join('')}

      </div>


      <div class="add-row">

        <button
          class="mini-btn form-add-btn"
          data-add-item="${si}:${bi}"
          type="button">

          + Tambah Item

        </button>

      </div>

    </div>
  `;
}

function itemBlockHtml(it, si, bi, ii){

  return `
    <div
      class="item-block"
      data-item-idx="${ii}">

      <div class="item-head">

        <div class="item-label">
          Item ${ii + 1}
        </div>

        <button
          class="mini-btn danger form-danger-btn"
          data-del-item="${si}:${bi}:${ii}"
          type="button">

          Hapus

        </button>

      </div>


      <!-- BASIC ITEM -->

      <div class="item-grid-main">

        <div class="field">

          <label>
            Produk
          </label>

          <input
            class="it-product"
            data-path="${si}:${bi}:${ii}"
            value="${escAttr(it.product)}"
            placeholder="Nama produk / service">

        </div>


        <div class="field">

          <label>
            Qty
          </label>

          <input
            type="number"
            class="it-qty"
            data-path="${si}:${bi}:${ii}"
            value="${it.qty ?? 1}"
            min="0">

        </div>


        <div class="field">

          <label>
            UoM
          </label>

          <input
            class="it-uom"
            data-path="${si}:${bi}:${ii}"
            value="${escAttr(it.uom)}"
            placeholder="Unit">

        </div>


        <div class="field">

          <label>
            Vendor
          </label>

          <input
            class="it-vendor"
            data-path="${si}:${bi}:${ii}"
            value="${escAttr(it.vendor)}"
            placeholder="Vendor">

        </div>

      </div>


      <!-- FINANCIAL + PIC -->

      <div class="item-grid-finance">

        <div class="field">

          <label>
            SPH Awal
          </label>

          <input
            type="number"
            class="it-awal"
            data-path="${si}:${bi}:${ii}"
            value="${it.sphAwal ?? ''}"
            placeholder="0">

        </div>


        <div class="field">

          <label>
            SPH Final
          </label>

          <input
            type="number"
            class="it-final"
            data-path="${si}:${bi}:${ii}"
            value="${it.sphFinal ?? ''}"
            placeholder="0">

        </div>


        <div class="field">

          <label>
            PIC
          </label>

          <div class="pic-select">

            ${team
              .map(t => `
                <div
                  class="
                    pic-opt
                    ${it.picIds.includes(t) ? 'on' : ''}
                  "
                  data-pic="${si}:${bi}:${ii}:${escAttr(t)}">

                  ${escAttr(t)}

                </div>
              `)
              .join('')}

          </div>

        </div>

      </div>

    </div>
  `;
}

function teamModalHtml(d){ return `<div class="overlay" id="ov" style="z-index: 100;"><div class="modal" style="max-width:480px;"><div class="modal-hd"><h3>Kelola tim</h3><button class="mini-btn" id="m-close">Tutup</button></div><div class="modal-body"><textarea id="m-team-names" rows="4">${escAttr(d.names)}</textarea></div><div class="modal-ft"><button class="btn-ghost" id="m-cancel">Batal</button><button class="btn-primary" id="m-save-team">Simpan</button></div></div></div>`; }

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

  document.getElementById('m-add-sow').onclick = ()=>{ syncModalData(); modal.data.sows.push({id:uid('sow'), name:'', boqs:[{id:uid('boq'), name:'', items:[{id:uid('item'), product:'', qty:1, vendor:'', picIds:[], sphAwal:null, sphFinal:null}]}]}); render(); };
  document.querySelectorAll('[data-add-boq]').forEach(el=> el.onclick=()=>{ syncModalData(); modal.data.sows[+el.dataset.addBoq].boqs.push({id:uid('boq'), name:'', items:[{id:uid('item'), product:'', qty:1, vendor:'', picIds:[], sphAwal:null, sphFinal:null}]}); render(); });
  document.querySelectorAll('[data-add-item]').forEach(el=>{ const [si,bi] = el.dataset.addItem.split(':').map(Number); el.onclick = ()=>{ syncModalData(); modal.data.sows[si].boqs[bi].items.push({id:uid('item'), product:'', qty:1, vendor:'', picIds:[], sphAwal:null, sphFinal:null}); render(); }; });
  document.querySelectorAll('[data-del-sow]').forEach(el=> el.onclick=()=>{ syncModalData(); modal.data.sows.splice(+el.dataset.delSow,1); render(); });
  document.querySelectorAll('[data-del-boq]').forEach(el=>{ const [si,bi] = el.dataset.delBoq.split(':').map(Number); el.onclick=()=>{ syncModalData(); modal.data.sows[si].boqs.splice(bi,1); render(); }; });
  document.querySelectorAll('[data-del-item]').forEach(el=>{ const [si,bi,ii] = el.dataset.delItem.split(':').map(Number); el.onclick=()=>{ syncModalData(); modal.data.sows[si].boqs[bi].items.splice(ii,1); render(); }; });
  document.querySelectorAll('[data-pic]').forEach(el=>{ const [si,bi,ii,name] = el.dataset.pic.split(':'); el.onclick = ()=>{ syncModalData(); const arr = modal.data.sows[+si].boqs[+bi].items[+ii].picIds; const idx = arr.indexOf(name); if(idx>=0) arr.splice(idx,1); else arr.push(name); render(); }; });

  document.getElementById('m-save').onclick = ()=>{ syncModalData(); const d = modal.data; const idx = projects.findIndex(p=>p.id===d.id); if(idx>=0) projects[idx]=d; else projects.push(d); document.getElementById('modal-root').innerHTML = ''; modal = null; render(); saveAll(); };
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
    const formData = new FormData(); formData.append('ticket_id', projectId); formData.append('vendor_name', name); formData.append('offered_price', price); formData.append('file', file);
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