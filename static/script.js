// ---------- storage keys & setup ----------
const API_URL = 'http://3.107.94.65:5000/api/presourcing';

let projects = [];
let team = [];
let activeTab = 'overview';
let openProjectId = null;
let modal = null; 
let modalScroll = 0;
let filters = { priority:'all', status:'all' };
let storageOk = true;

function uid(p){ return p + '_' + Math.random().toString(36).slice(2,9); }
function todayStr(){ return new Date().toISOString().slice(0,10); }

// ---------- seed data (Fallback jika server mati) ----------
function seedData(){
  team = ['Budi','Sari','Andi','Rahma','Fajar'];
  projects = [
    {
      id: uid('proj'), name:'Project Pertamina — Security & Monitoring',
      requestorName:'Marcel', requestorDept:'SA G&P',
      priority:'High', status:'win', leadId:'Budi',
      sphMode:'item', projectSphAwal:null, projectSphFinal:null,
      createdAt:'2026-07-02', closedAt:'2026-07-22',
      sows:[{
        id:uid('sow'), name:'SoW Security & Monitoring',
        boqs:[{
          id:uid('boq'), name:'BoQ Utama',
          items:[
            {id:uid('item'), product:'CCTV', picIds:['Budi','Sari'], sphAwal:520000000, sphFinal:452000000},
            {id:uid('item'), product:'SDWAN', picIds:['Andi'], sphAwal:310000000, sphFinal:298000000},
            {id:uid('item'), product:'License Security', picIds:['Rahma'], sphAwal:145000000, sphFinal:145000000},
            {id:uid('item'), product:'Monitoring System', picIds:['Budi','Fajar'], sphAwal:210000000, sphFinal:187000000}
          ]
        }]
      }]
    },
    {
      id: uid('proj'), name:'Project Jakarta Commerce — Network Upgrade',
      requestorName:'Megati', requestorDept:'SA Jakarta Commerce',
      priority:'Urgent', status:'ongoing', leadId:'Andi',
      sphMode:'project', projectSphAwal:680000000, projectSphFinal:null,
      createdAt:'2026-08-15', closedAt:null,
      sows:[{
        id:uid('sow'), name:'SoW Network Upgrade',
        boqs:[{
          id:uid('boq'), name:'BoQ Core',
          items:[
            {id:uid('item'), product:'Router & Switching', picIds:['Andi'], sphAwal:null, sphFinal:null},
            {id:uid('item'), product:'Wifi Access Point', picIds:['Sari','Fajar'], sphAwal:null, sphFinal:null}
          ]
        }]
      }]
    }
  ];
}

// ---------- persistence ----------
async function loadAll(){
  try {
    const response = await fetch(API_URL);
    if (!response.ok) throw new Error("Gagal terhubung ke Backend");
    
    const data = await response.json();
    
    if (!data.projects || !data.team || (data.projects.length === 0 && data.team.length === 0)) {
      seedData();
      await saveAll(); 
    } else {
      projects = data.projects;
      team = data.team;
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
  }
  render(); 
}

// ---------- computations ----------
function allItems(proj){
  const out=[];
  (proj.sows||[]).forEach(s=> (s.boqs||[]).forEach(b=> (b.items||[]).forEach(it=> out.push(it))));
  return out;
}
function projectSph(proj){
  if(proj.sphMode==='project'){
    return { awal: proj.projectSphAwal, final: proj.projectSphFinal };
  }
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
    if(proj.sphMode==='item'){
      allItems(proj).forEach(it=>{
        const pics = it.picIds && it.picIds.length ? it.picIds : [];
        if(!pics.length) return;
        const share = 1/pics.length;
        const eff = efficiencyPct(it.sphAwal, it.sphFinal);
        pics.forEach(p=>{
          if(!stats[p]) return;
          stats[p].supportLoad += share;
          if(eff!=null){ stats[p].effSum += eff*share; stats[p].effWeight += share; }
        });
      });
    } else {
      const eff = efficiencyPct(proj.projectSphAwal, proj.projectSphFinal);
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
    }
  });
  return stats;
}
function overallKpis(){
  const active = projects.filter(p=>p.status==='ongoing').length;
  const closed = projects.filter(p=>p.status!=='ongoing');
  const wins = closed.filter(p=>p.status==='win').length;
  const winRate = closed.length ? (wins/closed.length*100) : null;
  const effs = projects.map(p=>{ const s=projectSph(p); return efficiencyPct(s.awal,s.final); }).filter(e=>e!=null);
  const avgEff = effs.length ? effs.reduce((a,b)=>a+b,0)/effs.length : null;
  const durs = closed.map(p=>durationDays(p));
  const avgDur = durs.length ? Math.round(durs.reduce((a,b)=>a+b,0)/durs.length) : null;
  return { active, winRate, avgEff, avgDur, total: projects.length };
}
function fmtIdr(n){
  if(n==null) return '—';
  return 'Rp ' + Math.round(n).toLocaleString('id-ID');
}
function fmtPct(n){ return n==null ? '—' : n.toFixed(1)+'%'; }
function tagPriority(p){
  const cls = p==='Urgent'?'tag-urgent':p==='High'?'tag-high':'tag-medium';
  return `<span class="tag ${cls}">${p}</span>`;
}
function tagStatus(s){
  const cls = s==='win'?'tag-win':s==='lose'?'tag-lose':'tag-ongoing';
  const label = s==='win'?'Menang':s==='lose'?'Kalah':'Berjalan';
  return `<span class="tag ${cls}">${label}</span>`;
}

// ---------- render ----------
function render(){
  const app = document.getElementById('app');
  const k = overallKpis();
  app.innerHTML = `
    <div class="hdr">
      <div>
        <h1>Presourcing Control</h1>
        <div class="sub">Monitoring beban, efisiensi, dan win rate tim presourcing lintas project${storageOk?' · <span style="color:var(--green)">Online (tersinkronisasi)</span>':' · <span style="color:var(--red)">Offline (koneksi database terputus)</span>'}</div>
      </div>
      <div class="tabs">
        ${tabBtn('overview','Overview')}
        ${tabBtn('projects','Project')}
        ${tabBtn('team','Tim &amp; Load')}
      </div>
    </div>

    <div class="kpirow">
      <div class="kpi"><div class="label">Project Aktif</div><div class="val">${k.active}</div></div>
      <div class="kpi"><div class="label">Win Rate Project</div><div class="val">${k.winRate==null?'—':k.winRate.toFixed(0)}<span class="unit">${k.winRate==null?'':'%'}</span></div></div>
      <div class="kpi"><div class="label">Rata-rata Efficiency</div><div class="val">${k.avgEff==null?'—':k.avgEff.toFixed(1)}<span class="unit">${k.avgEff==null?'':'%'}</span></div></div>
      <div class="kpi"><div class="label">Rata-rata Durasi (closed)</div><div class="val">${k.avgDur==null?'—':k.avgDur}<span class="unit">${k.avgDur==null?'':'hari'}</span></div></div>
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

function renderOverview(){
  const byPriority = {Urgent:0, High:0, Medium:0};
  projects.forEach(p=> byPriority[p.priority] = (byPriority[p.priority]||0)+1);
  const urgentActive = projects.filter(p=>p.priority==='Urgent' && p.status==='ongoing');
  return `
    <div class="panel">
      <div class="panel-hd"><h2>Distribusi prioritas</h2></div>
      <div class="panel-body">
        <div class="lb-row"><div class="lb-name">Urgent</div><div class="lb-bar-track"><div class="lb-bar-fill" style="width:${pct(byPriority.Urgent,projects.length)}%; background:var(--red)"></div></div><div class="lb-val">${byPriority.Urgent}</div></div>
        <div class="lb-row"><div class="lb-name">High</div><div class="lb-bar-track"><div class="lb-bar-fill" style="width:${pct(byPriority.High,projects.length)}%"></div></div><div class="lb-val">${byPriority.High}</div></div>
        <div class="lb-row"><div class="lb-name">Medium</div><div class="lb-bar-track"><div class="lb-bar-fill" style="width:${pct(byPriority.Medium,projects.length)}%; background:var(--slate)"></div></div><div class="lb-val">${byPriority.Medium}</div></div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-hd"><h2>Perlu perhatian — project urgent yang masih berjalan</h2></div>
      <div class="panel-body">
        ${urgentActive.length===0 ? '<div class="empty">Tidak ada project urgent yang masih berjalan.</div>' :
          urgentActive.map(p=>`<div style="padding:6px 0; border-bottom:1px solid var(--border-soft); font-size:13px;">
            <strong>${p.name}</strong> · ${p.requestorName} (${p.requestorDept}) · berjalan ${durationDays(p)} hari
          </div>`).join('')}
      </div>
    </div>
  `;
}

function pct(n,total){ return total? (n/total*100).toFixed(0) : 0; }

function renderProjects(){
  const filtered = projects.filter(p=>{
    if(filters.priority!=='all' && p.priority!==filters.priority) return false;
    if(filters.status!=='all' && p.status!==filters.status) return false;
    return true;
  });
  return `
    <div class="panel">
      <div class="panel-hd">
        <h2>Daftar Project</h2>
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
            <th>Project</th><th>Pemohon</th><th>Prioritas</th><th>Status</th>
            <th class="num">SPH Awal</th><th class="num">SPH Final</th><th class="num">Efficiency</th><th class="num">Durasi</th>
          </tr></thead>
          <tbody>
          ${filtered.map(p=>{
            const s = projectSph(p); const eff = efficiencyPct(s.awal,s.final);
            return `<tr class="proj-row" data-open="${p.id}">
              <td>${p.name}</td>
              <td>${p.requestorName}<br><span style="color:var(--text-muted); font-size:11.5px;">${p.requestorDept}</span></td>
              <td>${tagPriority(p.priority)}</td>
              <td>${tagStatus(p.status)}</td>
              <td class="num mono">${fmtIdr(s.awal)}</td>
              <td class="num mono">${fmtIdr(s.final)}</td>
              <td class="num mono">${fmtPct(eff)}</td>
              <td class="num mono">${durationDays(p)}h</td>
            </tr>
            ${openProjectId===p.id ? `<tr><td colspan="8">${renderProjectDetail(p)}</td></tr>` : ''}
            `;
          }).join('')}
          </tbody>
        </table>
        ${filtered.length===0?'<div class="empty">Tidak ada project yang cocok dengan filter ini.</div>':''}
      </div>
    </div>
  `;
}

function renderProjectDetail(p){
  const uniq = uniquePicsInProject(p);
  return `
    <div class="detail-block">
      <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
        <div style="font-size:12px; color:var(--text-muted);">Lead Presource: <strong style="color:var(--text);">${p.leadId||'—'}</strong> · PIC terlibat: ${uniq.join(', ')||'—'}</div>
        <div style="display:flex; gap:6px;">
          <button class="mini-btn" data-edit-project="${p.id}">Edit</button>
          <button class="mini-btn danger" data-delete-project="${p.id}">Hapus</button>
        </div>
      </div>
      ${(p.sows||[]).map(sow=>`
        <div class="sow-title">Scope of Work: ${sow.name}</div>
        ${(sow.boqs||[]).map(boq=>`
          <div class="boq-title">Bill of Quantity: ${boq.name}</div>
          <div style="display:grid; grid-template-columns: 2fr 0.4fr 1fr 1fr 1fr 0.8fr 1.5fr; gap:8px; padding:5px 0; font-size:10.5px; color:var(--text-dim); border-bottom:1px solid var(--border);">
            <div>Produk</div><div>Qty</div><div>Vendor</div><div class="num">SPH Awal</div><div class="num">SPH Final</div><div class="num">Efficiency</div><div>PIC</div>
          </div>
          ${(boq.items||[]).map(it=>{
            const eff = p.sphMode==='item' ? efficiencyPct(it.sphAwal,it.sphFinal) : null;
            return `<div style="display:grid; grid-template-columns: 2fr 0.4fr 1fr 1fr 1fr 0.8fr 1.5fr; gap:8px; padding:7px 0; font-size:12.5px; border-bottom:1px solid var(--border-soft); align-items:start;">
              <div>
                <div style="font-weight:500;">${it.product || '—'}</div>
                ${it.notes ? `<div style="font-size:11px; color:var(--text-muted); margin-top:3px;">📝 ${it.notes}</div>` : ''}
              </div>
              <div style="color:var(--text-muted);">${it.qty || '-'}</div>
              <div style="color:var(--text-muted);">${it.vendor || '-'}</div>
              <div class="num mono">${p.sphMode==='item'?fmtIdr(it.sphAwal):'—'}</div>
              <div class="num mono">${p.sphMode==='item'?fmtIdr(it.sphFinal):'—'}</div>
              <div class="num mono">${p.sphMode==='item'?fmtPct(eff):'—'}</div>
              <div>${(it.picIds||[]).map(x=>`<span class="pic-chip">${x}</span>`).join('')}</div>
            </div>`;
          }).join('')}
        `).join('')}
      `).join('')}
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
  const maxLoad = Math.max(1, ...rows.map(r=>r.supportLoad));
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
            <td>${r.name}</td>
            <td class="num mono">${r.leadCount}</td>
            <td class="num mono">${r.supportLoad.toFixed(2)}</td>
            <td class="num mono">${fmtPct(r.winRate)}</td>
            <td class="num mono">${fmtPct(r.avgEff)}</td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-hd"><h2>Support Load per anggota</h2></div>
      <div class="panel-body">
        ${rows.map(r=>`<div class="lb-row">
          <div class="lb-name">${r.name}</div>
          <div class="lb-bar-track"><div class="lb-bar-fill" style="width:${(r.supportLoad/maxLoad*100).toFixed(0)}%"></div></div>
          <div class="lb-val">${r.supportLoad.toFixed(2)}</div>
        </div>`).join('')}
      </div>
      <div class="panel-body" style="padding-top:0;">
        <div class="note">Support Load = jumlah kredit fractional dari item yang ditangani (1 ÷ jumlah PIC per item). Lead Count dihitung terpisah, tidak fractional.</div>
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

// ---------- modal functions ----------
function blankProject(){
  return {
    id: uid('proj'), name:'', requestorName:'', requestorDept:'',
    priority:'Medium', status:'ongoing', leadId: team[0]||'',
    sphMode:'item', projectSphAwal:null, projectSphFinal:null,
    createdAt: todayStr(), closedAt:null,
    sows:[{ id:uid('sow'), name:'', boqs:[{ id:uid('boq'), name:'', items:[{ id:uid('item'), product:'', qty:1, vendor:'', notes:'', picIds:[], sphAwal:null, sphFinal:null }] }] }]
  };
}
function openProjectModal(id){
  modalScroll = 0; // Reset scroll
  const existing = id ? JSON.parse(JSON.stringify(projects.find(p=>p.id===id))) : blankProject();
  modal = { type:'project', data: existing, isNew: !id };
  render();
}
function openTeamModal(){ 
  modalScroll = 0; // Reset scroll
  modal = { type:'team', data:{ names: team.join(', ') } }; render(); 
}

function renderModal(){
  let root = document.getElementById('modal-root');
  if(!root){ root = document.createElement('div'); root.id='modal-root'; document.body.appendChild(root); }
  if(modal.type==='project') root.innerHTML = projectModalHtml(modal.data, modal.isNew);
  if(modal.type==='team') root.innerHTML = teamModalHtml(modal.data);
  wireModalEvents();
  // Kembalikan posisi scroll agar tidak mantul ke atas
  const m = document.querySelector('.modal');
  if(m) m.scrollTop = modalScroll;
}

function projectModalHtml(d, isNew){
  return `
  <div class="overlay" id="ov">
    <div class="modal">
      <div class="modal-hd">
        <h3>${isNew?'Project baru':'Edit project'}</h3>
        <button class="mini-btn" id="m-close" type="button">Tutup</button>
      </div>
      <div class="modal-body">
        <div class="field"><label>Nama project</label><input id="m-name" value="${escAttr(d.name)}" placeholder="Project Pertamina — ..."></div>
        <div class="grid2">
          <div class="field"><label>Nama pemohon (SA)</label><input id="m-req-name" value="${escAttr(d.requestorName)}" placeholder="Marcel"></div>
          <div class="field"><label>Departemen pemohon</label><input id="m-req-dept" value="${escAttr(d.requestorDept)}" placeholder="SA G&P"></div>
        </div>
        <div class="grid3">
          <div class="field"><label>Prioritas</label>
            <select id="m-priority">
              ${['Medium','High','Urgent'].map(x=>`<option ${d.priority===x?'selected':''}>${x}</option>`).join('')}
            </select>
          </div>
          <div class="field"><label>Status</label>
            <select id="m-status">
              <option value="ongoing" ${d.status==='ongoing'?'selected':''}>Berjalan</option>
              <option value="win" ${d.status==='win'?'selected':''}>Menang</option>
              <option value="lose" ${d.status==='lose'?'selected':''}>Kalah</option>
            </select>
          </div>
          <div class="field"><label>Lead Presource</label>
            <select id="m-lead">${team.map(t=>`<option ${d.leadId===t?'selected':''}>${t}</option>`).join('')}</select>
          </div>
        </div>
        <div class="grid2">
          <div class="field"><label>Tanggal request masuk</label><input type="date" id="m-created" value="${d.createdAt||''}"></div>
          <div class="field"><label>Tanggal SPH final / ditutup</label><input type="date" id="m-closed" value="${d.closedAt||''}"></div>
        </div>
        <div class="field"><label>Mode pencatatan SPH</label>
          <select id="m-sphmode">
            <option value="item" ${d.sphMode==='item'?'selected':''}>Per item/produk (di dalam BoQ)</option>
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
    <div class="field"><label>Nama SoW</label><input class="sow-name" data-si="${si}" value="${escAttr(sow.name)}" placeholder="SoW Security & Monitoring"></div>
    ${sow.boqs.map((boq,bi)=>boqBlockHtml(boq,si,bi)).join('')}
    <button class="mini-btn" data-add-boq="${si}" type="button">+ Tambah BoQ</button>
    <button class="mini-btn danger" data-del-sow="${si}" type="button" style="float:right;">Hapus SoW</button>
  </div>`;
}
function boqBlockHtml(boq, si, bi){
  return `<div class="boq-block" data-boq-idx="${bi}">
    <div class="field"><label>Nama BoQ</label><input class="boq-name" data-si="${si}" data-bi="${bi}" value="${escAttr(boq.name)}" placeholder="BoQ Utama"></div>
    ${boq.items.map((it,ii)=>itemBlockHtml(it,si,bi,ii)).join('')}
    <button class="mini-btn" data-add-item="${si}:${bi}" type="button">+ Tambah item/produk</button>
    <button class="mini-btn danger" data-del-boq="${si}:${bi}" type="button" style="float:right;">Hapus BoQ</button>
  </div>`;
}
function itemBlockHtml(it, si, bi, ii){
  return `<div class="item-block" data-item-idx="${ii}">
    <div style="display:grid; grid-template-columns: 2fr 0.5fr 1.5fr; gap:12px; margin-bottom:12px;">
      <div class="field" style="margin:0;"><label>Produk</label><input class="it-product" data-path="${si}:${bi}:${ii}" value="${escAttr(it.product)}" placeholder="CCTV"></div>
      <div class="field" style="margin:0;"><label>Qty</label><input type="number" class="it-qty" data-path="${si}:${bi}:${ii}" value="${it.qty??1}"></div>
      <div class="field" style="margin:0;"><label>Vendor</label><input class="it-vendor" data-path="${si}:${bi}:${ii}" value="${escAttr(it.vendor)}" placeholder="Nama Vendor"></div>
    </div>
    <div class="grid3">
      <div class="field"><label>SPH Awal item</label><input type="number" class="it-awal" data-path="${si}:${bi}:${ii}" value="${it.sphAwal??''}"></div>
      <div class="field"><label>SPH Final item</label><input type="number" class="it-final" data-path="${si}:${bi}:${ii}" value="${it.sphFinal??''}"></div>
      <div class="field"><label>PIC untuk item ini</label>
        <div class="pic-select">${team.map(t=>`<div class="pic-opt ${it.picIds.includes(t)?'on':''}" data-pic="${si}:${bi}:${ii}:${t}">${t}</div>`).join('')}</div>
      </div>
    </div>
    <div class="field"><label>Notes (Opsional)</label><input class="it-notes" data-path="${si}:${bi}:${ii}" value="${escAttr(it.notes)}" placeholder="Catatan tambahan..."></div>
    <button class="mini-btn danger" data-del-item="${si}:${bi}:${ii}" type="button">Hapus item</button>
  </div>`;
}
function escAttr(s){ return (s||'').replace(/"/g,'&quot;'); }

function teamModalHtml(d){
  return `<div class="overlay" id="ov">
    <div class="modal" style="max-width:480px;">
      <div class="modal-hd">
        <h3>Kelola anggota tim presourcing</h3>
        <button class="mini-btn" id="m-close" type="button">Tutup</button>
      </div>
      <div class="modal-body">
        <div class="field"><label>Nama anggota, pisahkan dengan koma</label>
          <textarea id="m-team-names" rows="4">${escAttr(d.names)}</textarea>
        </div>
        <div class="note">Mengubah daftar ini tidak menghapus data project yang sudah ada.</div>
      </div>
      <div class="modal-ft">
        <button class="btn-ghost" id="m-cancel" type="button">Batal</button>
        <button class="btn-primary" id="m-save-team" type="button">Simpan</button>
      </div>
    </div>
  </div>`;
}

// ---------- FUNGSI SIMPAN SEMENTARA ----------
function syncModalData() {
  if(!modal || modal.type !== 'project') return;
  // Tangkap posisi scroll saat ini sebelum form di-refresh
  const m = document.querySelector('.modal');
  if(m) modalScroll = m.scrollTop;
  const d = modal.data;
  d.name = val('m-name'); d.requestorName = val('m-req-name'); d.requestorDept = val('m-req-dept');
  d.priority = val('m-priority'); d.status = val('m-status'); d.leadId = val('m-lead');
  d.createdAt = val('m-created') || todayStr(); d.closedAt = val('m-closed') || null;
  d.sphMode = val('m-sphmode');
  if(d.sphMode==='project'){
    d.projectSphAwal = numOrNull(document.getElementById('m-proj-awal').value);
    d.projectSphFinal = numOrNull(document.getElementById('m-proj-final').value);
  }
  
  document.querySelectorAll('.sow-name').forEach(el=> d.sows[+el.dataset.si].name = el.value);
  document.querySelectorAll('.boq-name').forEach(el=> d.sows[+el.dataset.si].boqs[+el.dataset.bi].name = el.value);
  document.querySelectorAll('.it-qty').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].qty = numOrNull(el.value); });
  document.querySelectorAll('.it-vendor').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].vendor = el.value; });
  document.querySelectorAll('.it-notes').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].notes = el.value; });
  document.querySelectorAll('.it-product').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].product = el.value; });
  document.querySelectorAll('.it-awal').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].sphAwal = numOrNull(el.value); });
  document.querySelectorAll('.it-final').forEach(el=>{ const [si,bi,ii]=el.dataset.path.split(':').map(Number); d.sows[si].boqs[bi].items[ii].sphFinal = numOrNull(el.value); });
}

// ---------- wire modal events with safety checks ----------
function wireModalEvents(){
  if (!modal) return;

  const close = ()=>{ 
    modal = null; 
    let root = document.getElementById('modal-root');
    if(root) root.innerHTML = ''; 
    render(); 
  };
  
  const c1 = document.getElementById('m-close'); if(c1) c1.onclick = close;
  const c2 = document.getElementById('m-cancel'); if(c2) c2.onclick = close;
  
  const ov = document.getElementById('ov');
  if(ov) {
    ov.onclick = (e) => { if(e.target === ov) close(); };
  }

  if(modal.type==='team'){
    const saveTeamBtn = document.getElementById('m-save-team');
    if(saveTeamBtn){
      saveTeamBtn.onclick = ()=>{
        const names = document.getElementById('m-team-names').value.split(',').map(s=>s.trim()).filter(Boolean);
        team = names.length?names:team;
        modal = null;
        render();
        saveAll();
      };
    }
    return;
  }

  // project modal events (Tiap nambah/hapus selalu panggil syncModalData dulu)
  const sphmode = document.getElementById('m-sphmode');
  if(sphmode) sphmode.onchange = ()=>{ syncModalData(); modal.data.sphMode = sphmode.value; render(); };

  const addSowBtn = document.getElementById('m-add-sow');
  if(addSowBtn) addSowBtn.onclick = ()=>{
    syncModalData();
    modal.data.sows.push({
      id:uid('sow'), name:'', 
      boqs:[{
        id:uid('boq'), name:'', 
        items:[{id:uid('item'), product:'', qty:1, vendor:'', notes:'', picIds:[], sphAwal:null, sphFinal:null}]
      }]
    });
    render();
  };

  document.querySelectorAll('[data-add-boq]').forEach(el=> el.onclick=()=>{
    syncModalData();
    const si = +el.dataset.addBoq;
    modal.data.sows[si].boqs.push({
      id:uid('boq'), name:'', 
      items:[{id:uid('item'), product:'', qty:1, vendor:'', notes:'', picIds:[], sphAwal:null, sphFinal:null}]
    });
    render();
  });

  document.querySelectorAll('[data-add-item]').forEach(el=>{
    const [si,bi] = el.dataset.addItem.split(':').map(Number);
    el.onclick = ()=>{ 
      syncModalData();
      modal.data.sows[si].boqs[bi].items.push({
        id:uid('item'), product:'', qty:1, vendor:'', notes:'', picIds:[], sphAwal:null, sphFinal:null
      }); 
      render(); 
    };
  });

  document.querySelectorAll('[data-del-sow]').forEach(el=>{
    const si = +el.dataset.delSow;
    el.onclick = ()=>{ syncModalData(); modal.data.sows.splice(si,1); render(); };
  });

  document.querySelectorAll('[data-del-boq]').forEach(el=>{
    const [si,bi] = el.dataset.delBoq.split(':').map(Number);
    el.onclick = ()=>{ syncModalData(); modal.data.sows[si].boqs.splice(bi,1); render(); };
  });

  document.querySelectorAll('[data-del-item]').forEach(el=>{
    const [si,bi,ii] = el.dataset.delItem.split(':').map(Number);
    el.onclick = ()=>{ syncModalData(); modal.data.sows[si].boqs[bi].items.splice(ii,1); render(); };
  });

  document.querySelectorAll('[data-pic]').forEach(el=>{
    const [si,bi,ii,name] = el.dataset.pic.split(':');
    el.onclick = ()=>{
      syncModalData();
      const arr = modal.data.sows[+si].boqs[+bi].items[+ii].picIds;
      const idx = arr.indexOf(name);
      if(idx>=0) arr.splice(idx,1); else arr.push(name);
      render();
    };
  });

  const saveBtn = document.getElementById('m-save');
  if(saveBtn){
    saveBtn.onclick = ()=>{
      syncModalData(); // Cukup panggil fungsi ini saat save
      const d = modal.data;
      const idx = projects.findIndex(p=>p.id===d.id);
      if(idx>=0) projects[idx]=d; else projects.push(d);
      
      let root = document.getElementById('modal-root');
      if(root) root.innerHTML = '';
      modal = null;
      render();
      saveAll();
    };
  }
}

function val(id){ const el=document.getElementById(id); return el?el.value:''; }
function numOrNull(v){ return (v===''||v==null) ? null : Number(v); }

// Jalankan load data awal saat pertama kali script dimuat
loadAll();