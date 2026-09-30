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
    return ((val || 0) / 1000000000).toFixed(1); // Konversi ke Rp Miliar
}

// --- FUNGSI STATUS DINAMIS EWS ---
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

// ---------- render ----------
function render(){
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="hdr">
      <div>
        <h1>Presourcing Project Dashboard</h1>
        <div class="sub">Pipeline, Progress, and Target RFS${storageOk?' · <span style="color:var(--green)">Online</span>':' · <span style="color:var(--red)">Offline</span>'}</div>
      </div>
      <div class="tabs">
        ${tabBtn('overview','Executive Dashboard')}
        ${tabBtn('projects','Detail BoQ & SPH')}
        ${tabBtn('team','Tim &amp; Beban Kerja')}
      </div>
    </div>
    <div id="tabcontent"></div>
  `;
  const content = document.getElementById('tabcontent');
  if(activeTab==='overview') content.innerHTML = renderOverview();
  if(activeTab==='projects') content.innerHTML = renderProjects();
  if(activeTab==='team') content.innerHTML = renderTeam();
  
  wireEvents();
  if(modal) renderModal();
}

function tabBtn(id,label){
  return `<div class="tab ${activeTab===id?'active':''}" data-tab="${id}">${label}</div>`;
}

// --------------------------------------------------------
// RENDER OVERVIEW: EXECUTIVE DASHBOARD (RESPONSIF & SCROLLABLE OVERVIEW)
// --------------------------------------------------------
function renderOverview(){
  const totalProj = projects.length;
  let totalVal = 0;
  const sCount = { 'On Track':0, 'At Risk':0, 'Overdue':0, 'Completed':0, 'Planned':0 };
  const pCount = { 1:0, 2:0, 3:0, 4:0, 5:0, 6:0 };
  
  projects.forEach(p => {
      totalVal += (projectSph(p).awal || 0);
      sCount[getDynamicStatus(p)]++;
      if(p.status === 'ongoing') {
          const stage = parseInt((p.pipelineStage || '1').charAt(0));
          if(!isNaN(stage) && stage >= 1 && stage <= 6) pCount[stage]++;
      }
  });

  const getPct = (val) => totalProj ? Math.round((val/totalProj)*100) : 0;
  
  if (!window.Chart && !document.getElementById('chartjs-script')) {
      const script = document.createElement('script');
      script.id = 'chartjs-script';
      script.src = "https://cdn.jsdelivr.net/npm/chart.js";
      script.onload = () => setTimeout(renderDashboardCharts, 100);
      document.head.appendChild(script);
  } else {
      setTimeout(renderDashboardCharts, 100);
  }

  // CSS Responsif & Tabel dengan Scroll Terbatas (Max 5 baris / ~320px)
  const dashStyles = `
    <style>
        /* KPI Cards responsif menggunakan auto-fit */
        .kpi-row-new { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 20px; }
        .kpi-card { background: #fff; padding: 14px 16px; border-radius: 6px; border: 1px solid #e2e8f0; display:flex; align-items:center; gap: 12px; position: relative; box-shadow: 0 1px 2px rgba(0,0,0,0.02);}
        .kpi-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 4px; border-radius: 6px 6px 0 0; }
        .kpi-card:nth-child(1)::before { background: #0ea5e9; }
        .kpi-card:nth-child(2)::before { background: #3b82f6; }
        .kpi-card:nth-child(3)::before { background: #22c55e; }
        .kpi-card:nth-child(4)::before { background: #f59e0b; }
        .kpi-card:nth-child(5)::before { background: #ef4444; }
        .kpi-card:nth-child(6)::before { background: #1e293b; }

        .kpi-icon { width: 38px; height: 38px; border-radius: 50%; display:flex; align-items:center; justify-content:center; font-size: 18px; }
        
        /* Grid 3 Kolom yang responsif (otomatis turun ke bawah jika layar sempit) */
        .dash-grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 16px; }
        
        .dash-panel { background: #fff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.04); display:flex; flex-direction:column; }
        .dash-panel-hd { background: #1E63C8; color: white; padding: 12px 16px; font-weight: 600; font-size: 13.5px; display: flex; align-items: center; gap: 8px; }
        .dash-panel-hd.danger-hd { background: #DC3545; }
        .dash-panel-body { padding: 16px; flex: 1; }
        
        /* TABEL DENGAN SCROLL VERTIKAL (Maksimal menampilkan ~5 baris agar tidak redundant) */
        .scrollable-table-container {
            max-height: 310px; 
            overflow-y: auto; 
            overflow-x: auto;
            border-bottom: 1px solid #f1f5f9;
        }
        /* Sticky header tabel agar tetap terlihat saat di-scroll */
        .dash-table thead th {
            position: sticky;
            top: 0;
            background: #F8FAFC;
            z-index: 2;
        }

        .badge { padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; }
        .badge-on-track { background: #22C55E; color: white; }
        .badge-at-risk { background: #F59E0B; color: white; }
        .badge-overdue { background: #EF4444; color: white; }
        .badge-completed { background: #3B82F6; color: white; }
        .badge-planned { background: #e2e8f0; color: #475569; }

        .prog-bar-bg { background: #e5e7eb; border-radius: 4px; height: 8px; width: 100%; margin-top: 4px; }
        .prog-bar-fill { height: 100%; background: #3B82F6; border-radius: 4px; }

        .pipeline-container { display: flex; gap: 2px; margin-top: 5px; }
        .pipe-stage { flex: 1; color: white; padding: 12px 5px; text-align: center; font-size: 11px; clip-path: polygon(0% 0%, 92% 0%, 100% 50%, 92% 100%, 0% 100%, 8% 50%); margin-right: -8px; }
        .pipe-stage:first-child { clip-path: polygon(0% 0%, 92% 0%, 100% 50%, 92% 100%, 0% 100%); }
        .pipe-stage:last-child { clip-path: polygon(0% 0%, 100% 0%, 100% 100%, 0% 100%, 8% 50%); margin-right: 0; }
        
        table.dash-table { width: 100%; border-collapse: collapse; font-size: 12px; }
        table.dash-table th { padding: 10px 8px; border-bottom: 2px solid #e2e8f0; text-align: left; color: #64748b; font-weight: 600; font-size: 11px; text-transform: uppercase;}
        table.dash-table td { padding: 10px 8px; border-bottom: 1px solid #f1f5f9; }
    </style>
  `;

  const sortedProjects = [...projects].sort((a,b) => new Date(a.targetRfs||'2099') - new Date(b.targetRfs||'2099'));
  
  let overviewRows = '';
  sortedProjects.forEach((p, idx) => {
      overviewRows += `
      <tr>
          <td>${idx+1}</td>
          <td style="font-weight:500;">${escAttr(p.name)}</td>
          <td>${valToM(projectSph(p).awal)}</td>
          <td>${escAttr(p.leadId)}</td>
          <td>${p.targetRfs ? new Date(p.targetRfs).toLocaleDateString('id-ID', {day:'numeric', month:'short', year:'numeric'}) : '-'}</td>
          <td>${badgeStatus(getDynamicStatus(p))}</td>
          <td>
            <div style="display:flex; align-items:center; gap:8px;">
                <div style="width:35px; text-align:right;">${p.progressPct||0}%</div>
                <div class="prog-bar-bg"><div class="prog-bar-fill" style="width:${p.progressPct||0}%;"></div></div>
            </div>
          </td>
      </tr>`;
  });

  let ewsRows = '';
  sortedProjects.filter(p => ['Overdue', 'At Risk'].includes(getDynamicStatus(p))).forEach(p => {
      ewsRows += `
      <tr>
          <td style="font-weight:500;">${escAttr(p.name)}</td>
          <td>${p.targetRfs ? new Date(p.targetRfs).toLocaleDateString('id-ID', {day:'numeric', month:'short', year:'numeric'}) : '-'}</td>
          <td>${p.progressPct||0}%</td>
          <td>${badgeStatus(getDynamicStatus(p))}</td>
      </tr>`;
  });
  if(!ewsRows) ewsRows = `<tr><td colspan="4" style="text-align:center; color:var(--green); padding:20px;">Semua project aman! 🎉</td></tr>`;

  const pNames = ['Identification', 'SPH Prep', 'Vendor Select', 'Negotiation', 'Finalization', 'RFS'];
  let pipelineHtml = '<div class="pipeline-container">';
  pNames.forEach((name, i) => {
      const n = i+1;
      pipelineHtml += `
          <div class="pipe-stage" style="z-index: ${6-i}; background: ${n<=3 ? '#3B82F6' : (n<=5 ? '#0EA5E9' : '#22C55E')};">
              <div style="font-size:14px; font-weight:bold; margin-bottom:2px;">${n}</div>
              <div style="line-height:1.1;">${name}</div>
              <div style="margin-top:6px; font-weight:bold;">${pCount[n]} Proj</div>
          </div>
      `;
  });
  pipelineHtml += '</div>';

  return dashStyles + `
    <!-- ROW 1: KPI CARDS -->
    <div class="kpi-row-new">
        <div class="kpi-card"><div class="kpi-icon" style="background:#e0f2fe; color:#0284c7;">📊</div><div><div style="font-size:11px; color:#64748b;">Total Project</div><div style="font-size:18px; font-weight:bold;">${totalProj}</div></div></div>
        <div class="kpi-card"><div class="kpi-icon" style="background:#e0e7ff; color:#4f46e5;">💰</div><div><div style="font-size:11px; color:#64748b;">Total Value</div><div style="font-size:16px; font-weight:bold; color:#0f172a;">Rp ${valToM(totalVal)} M</div></div></div>
        <div class="kpi-card"><div class="kpi-icon" style="background:#dcfce7; color:#16a34a;">✅</div><div style="width:100%;"><div style="font-size:11px; color:#64748b;">On Track</div><div style="display:flex; justify-content:space-between; align-items:flex-end;"><div style="font-size:18px; font-weight:bold;">${sCount['On Track']}</div><div style="font-size:11px; font-weight:bold; color:#16a34a;">${getPct(sCount['On Track'])}%</div></div></div></div>
        <div class="kpi-card"><div class="kpi-icon" style="background:#fef9c3; color:#ca8a04;">⚠️</div><div style="width:100%;"><div style="font-size:11px; color:#64748b;">At Risk</div><div style="display:flex; justify-content:space-between; align-items:flex-end;"><div style="font-size:18px; font-weight:bold;">${sCount['At Risk']}</div><div style="font-size:11px; font-weight:bold; color:#ca8a04;">${getPct(sCount['At Risk'])}%</div></div></div></div>
        <div class="kpi-card"><div class="kpi-icon" style="background:#fee2e2; color:#dc2626;">⏳</div><div style="width:100%;"><div style="font-size:11px; color:#64748b;">Overdue</div><div style="display:flex; justify-content:space-between; align-items:flex-end;"><div style="font-size:18px; font-weight:bold;">${sCount['Overdue']}</div><div style="font-size:11px; font-weight:bold; color:#dc2626;">${getPct(sCount['Overdue'])}%</div></div></div></div>
        <div class="kpi-card"><div class="kpi-icon" style="background:#f1f5f9; color:#475569;">🏁</div><div style="width:100%;"><div style="font-size:11px; color:#64748b;">Completed</div><div style="display:flex; justify-content:space-between; align-items:flex-end;"><div style="font-size:18px; font-weight:bold;">${sCount['Completed']}</div><div style="font-size:11px; font-weight:bold; color:#475569;">${getPct(sCount['Completed'])}%</div></div></div></div>
    </div>

    <!-- ROW 2: OVERVIEW TABLE (SCROLLABLE), STATUS CHART, LINE CHART -->
    <div class="dash-grid-3">
        <div class="dash-panel">
            <div class="dash-panel-hd">📋 Project Presourcing Overview</div>
            <!-- Dibungkus container dengan tinggi maksimal dan scroll vertikal -->
            <div class="scrollable-table-container">
                <table class="dash-table">
                    <thead><tr><th>No</th><th>Project Name</th><th>Nilai (Rp M)</th><th>PIC</th><th>Target RFS</th><th>Status</th><th>Progress</th></tr></thead>
                    <tbody>${overviewRows}</tbody>
                </table>
            </div>
        </div>
        <div class="dash-panel">
            <div class="dash-panel-hd">🎯 Project Status</div>
            <div class="dash-panel-body" style="display:flex; align-items:center; justify-content:center;">
                <canvas id="chartStatus" style="max-height:220px;"></canvas>
            </div>
        </div>
        <div class="dash-panel">
            <div class="dash-panel-hd">📈 Target RFS by Month</div>
            <div class="dash-panel-body" style="display:flex; align-items:center; justify-content:center; padding:10px;">
                <canvas id="chartRfsMonth" style="max-height:220px;"></canvas>
            </div>
        </div>
    </div>

    <!-- ROW 3: PIPELINE, BAR CHART, EWS TABLE -->
    <div class="dash-grid-3">
        <div class="dash-panel">
            <div class="dash-panel-hd">🔄 Presourcing Progress Pipeline</div>
            <div class="dash-panel-body">
                ${pipelineHtml}
            </div>
        </div>
        <div class="dash-panel">
            <div class="dash-panel-hd">🏆 Top 5 Project Value</div>
            <div class="dash-panel-body" style="display:flex; align-items:center; justify-content:center; padding:10px;">
                <canvas id="chartTop5" style="max-height:220px;"></canvas>
            </div>
        </div>
        <div class="dash-panel">
            <div class="dash-panel-hd danger-hd">⚠ Early Warning (Need Attention)</div>
            <div class="scrollable-table-container">
                <table class="dash-table">
                    <thead><tr><th>Project Name</th><th>Target RFS</th><th>Progress</th><th>Status</th></tr></thead>
                    <tbody>${ewsRows}</tbody>
                </table>
            </div>
        </div>
    </div>
  `;
}

// Global variable untuk menyimpan instance grafik agar bisa di-destroy saat re-render
let dCharts = {}; 

function renderDashboardCharts() {
    if (typeof Chart === 'undefined') return;

    // 1. Persiapan Data Chart Status
    let sCount = { 'On Track':0, 'At Risk':0, 'Overdue':0, 'Completed':0, 'Planned':0 };
    projects.forEach(p => sCount[getDynamicStatus(p)]++);

    const ctxStatus = document.getElementById('chartStatus');
    if (ctxStatus) {
        if(dCharts.status) dCharts.status.destroy();
        dCharts.status = new Chart(ctxStatus, {
            type: 'doughnut',
            data: {
                labels: ['On Track', 'At Risk', 'Overdue', 'Completed', 'Planned'],
                datasets: [{
                    data: [sCount['On Track'], sCount['At Risk'], sCount['Overdue'], sCount['Completed'], sCount['Planned']],
                    backgroundColor: ['#22C55E', '#F59E0B', '#EF4444', '#3B82F6', '#e2e8f0']
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: {size: 11} } } }
            }
        });
    }

    // 2. Persiapan Data RFS by Month (Mixed Line & Bar Chart)
    const rfsData = {};
    projects.forEach(p => {
        if(!p.targetRfs) return;
        const d = new Date(p.targetRfs);
        const months = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Ags","Sep","Okt","Nov","Des"];
        const key = months[d.getMonth()] + " " + d.getFullYear();
        const sortK = d.getFullYear() * 100 + d.getMonth();
        
        if(!rfsData[key]) rfsData[key] = { count: 0, val: 0, sortK: sortK };
        rfsData[key].count += 1;
        rfsData[key].val += (projectSph(p).awal || 0);
    });
    const rfsKeys = Object.keys(rfsData).sort((a,b) => rfsData[a].sortK - rfsData[b].sortK);

    const ctxRfs = document.getElementById('chartRfsMonth');
    if (ctxRfs) {
        if(dCharts.rfsMonth) dCharts.rfsMonth.destroy();
        dCharts.rfsMonth = new Chart(ctxRfs, {
            type: 'bar',
            data: {
                labels: rfsKeys,
                datasets: [
                    { type: 'line', label: 'Nilai Project (Rp M)', data: rfsKeys.map(k=>(rfsData[k].val/1000000000).toFixed(1)), borderColor: '#0f172a', backgroundColor: '#0f172a', yAxisID: 'y1', tension: 0.3, borderWidth: 2 },
                    { type: 'bar', label: 'Jumlah Project', data: rfsKeys.map(k=>rfsData[k].count), backgroundColor: '#93c5fd', yAxisID: 'y', borderRadius: 4 }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    y: { type: 'linear', position: 'left', ticks: { stepSize: 1, font: {size: 10} }, grid: {color: '#f1f5f9'} },
                    y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, ticks: { font: {size: 10} } },
                    x: { ticks: { font: {size: 10} }, grid: {display: false} }
                },
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: {size: 10} } } }
            }
        });
    }

    // 3. Persiapan Data Top 5 Project (Horizontal Bar Chart)
    const top5 = [...projects]
        .filter(p => p.status !== 'lose')
        .map(p => ({ 
            name: p.name.replace('Project ', '').substring(0, 18) + (p.name.length > 25 ? '...' : ''), 
            val: ((projectSph(p).awal || 0) / 1000000000).toFixed(1) 
        }))
        .sort((a,b) => b.val - a.val)
        .slice(0, 5);

    const ctxTop5 = document.getElementById('chartTop5');
    if (ctxTop5) {
        if(dCharts.top5) dCharts.top5.destroy();
        dCharts.top5 = new Chart(ctxTop5, {
            type: 'bar',
            data: {
                labels: top5.map(t=>t.name),
                datasets: [{ label: 'Nilai (Rp M)', data: top5.map(t=>t.val), backgroundColor: '#3B82F6', borderRadius: 4 }]
            },
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { ticks: { font: {size: 10} }, grid: {color: '#f1f5f9'} },
                    y: { ticks: { font: {size: 10} }, grid: {display: false} }
                },
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => 'Rp ' + ctx.raw + ' M' } } }
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
          <td class="num mono">${durationDays(p)}h</td>
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

// ---------- events & wire ----------
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

// ---------- modal functions ----------
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

// ---------- FUNGSI MODAL UPLOAD SPH PEMBANDING ----------
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