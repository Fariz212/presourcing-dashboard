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
function uid(p) { return p + '_' + Math.random().toString(36).slice(2, 9); }
function todayStr() { return new Date().toISOString().slice(0, 10); }

function escAttr(s) { 
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function val(id) { 
  const el = document.getElementById(id); 
  return el ? el.value : ''; 
}

function numOrNull(v) { 
  return (v === '' || v == null) ? null : Number(v); 
}

function fmtIdr(n) { 
  return n == null ? '—' : 'Rp ' + Math.round(n).toLocaleString('id-ID'); 
}

function fmtPct(n) { 
  return n == null ? '—' : n.toFixed(1) + '%'; 
}

function valToM(val) {
  return ((val || 0) / 1000000000).toFixed(1);
}

function calculateUiSphTotal(qty, unitPrice) {
  const q = numOrNull(qty);
  const unit = numOrNull(unitPrice);
  return (q != null && unit != null) ? q * unit : null;
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
      sows: [{ id: uid('sow'), name: 'SoW Core', boqs: [{ id: uid('boq'), name: 'BoQ Utama', items: [{ id: uid('item'), product: 'Router', qty: 1, picIds: ['Andi'], sphAwalUnit: 25000000000, sphAwal: 25000000000, sphFinalUnit: null, sphFinal: null }] }] }]
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
    const timestamp = new Date().getTime();
    const response = await fetch(`${API_URL}?t=${timestamp}`, { cache: 'no-store' });
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
    if (projects.length === 0) seedData();
  }
  render();
}

async function saveAll() {
  if (isSaving) return;
  isSaving = true;
  document.body.style.cursor = 'wait';

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projects, team })
    });
    if (!response.ok) throw new Error("Gagal menyimpan ke Backend");
    storageOk = true;
  } catch(e) {
    console.error("Gagal menyimpan data:", e);
    storageOk = false; 
  } finally {
    isSaving = false; 
    document.body.style.cursor = 'default';
  }
  render(); 
}

// ============================================================================
// COMPUTATIONS
// ============================================================================
function allItems(proj) {
  const out = []; 
  (proj.sows || []).forEach(s => (s.boqs || []).forEach(b => (b.items || []).forEach(it => out.push(it)))); 
  return out;
}

function projectSph(proj) {
  if (proj.sphMode === 'project') return { awal: proj.projectSphAwal, final: proj.projectSphFinal };
  
  const items = allItems(proj);
  let awal = 0, final = 0, hasAwal = false, hasFinal = true;
  
  items.forEach(it => {
    if (it.sphAwal != null) { awal += Number(it.sphAwal); hasAwal = true; }
    if (it.sphFinal == null) { hasFinal = false; } else { final += Number(it.sphFinal); }
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
  
  const today = new Date(todayStr());
  const rfs = new Date(proj.targetRfs);
  const diffDays = Math.ceil((rfs - today) / (1000 * 60 * 60 * 24));
  
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
// ... (Karena renderOverview(), renderDashboardCharts(), dan renderTeam() dari kode AI 
// Anda sudah terstruktur dengan baik dan fungsional, saya tetap menahannya persis seperti versi Anda untuk menghemat karakter output) ...

// **PENTING**: Masukkan ulang fungsi renderOverview(), renderDashboardCharts(), dan renderTeam() 
// persis sama seperti dari script_4.js Anda ke dalam area ini.

// ============================================================================
// PROJECTS LIST & DETAIL
// ============================================================================
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
            <div class="num mono">${p.sphMode === 'item' ? fmtIdr(it.sphAwal) : '—'}</div>
            <div class="num mono">${p.sphMode === 'item' ? fmtIdr(it.sphFinal) : '—'}</div>
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
        <div style="font-size:12px; color:var(--text-muted);">Lead Presource: <strong style="color:var(--text);">${p.leadId||'—'}</strong> · PIC terlibat: ${uniq.join(', ')||'—'}</div>
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
    el.onclick = () => { const id = el.dataset.open; openProjectId = openProjectId === id ? null : id; render(); };
  });
  
  const btnNew = document.getElementById('btn-new-project');
  if (btnNew) btnNew.onclick = () => openProjectModal(null);
  
  document.querySelectorAll('[data-edit-project]').forEach(el => {
    el.onclick = (e) => { e.stopPropagation(); openProjectModal(el.dataset.editProject); };
  });

  document.querySelectorAll('[data-delete-project]').forEach(el => {
    el.onclick = async (e) => { 
      e.stopPropagation(); 
      if (confirm('Hapus project ini?')) { 
        projects = projects.filter(p => p.id !== el.dataset.deleteProject); 
        await saveAll(); 
        render(); 
      } 
    };
  });
  
  const btnTeam = document.getElementById('btn-manage-team');
  if (btnTeam) btnTeam.onclick = () => openTeamModal();
}

function downloadProjectReport(projectId) {
  window.location.href = `/api/download_report?project_id=${encodeURIComponent(projectId)}`;
}

function downloadBoqTemplate() {
  window.location.href = '/api/download_template_boq';
}

function downloadRevisionTemplate(projectId) {
  window.location.href = `/api/projects/${encodeURIComponent(projectId)}/download_boq_template`;
}

async function triggerRevisiBoq(projectId) {
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.xlsx, .xls';
  fileInput.style.display = 'none';
  document.body.appendChild(fileInput);

  fileInput.onchange = async () => {
    const file = fileInput.files[0];
    document.body.removeChild(fileInput);
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('ticket_id', projectId);
    document.body.style.cursor = 'wait';

    try {
      const previewRes = await fetch('/api/revisi_boq/preview', { method: 'POST', body: formData });
      const preview = await previewRes.json();

      if (!previewRes.ok || !preview.success) {
        alert(`Gagal membaca Excel: ${preview.message || ''}`);
        return;
      }
      showRevisionPreview(projectId, file, preview.data);
    } catch (error) {
      console.error(error);
      alert('Terjadi kesalahan saat membaca file Excel.');
    } finally {
      document.body.style.cursor = 'default';
    }
  };
  fileInput.click();
}

function revisionSummaryCard(icon, count, label, color, bg) {
  return `
    <div style="padding:9px; border:1px solid #E2E8F0; border-radius:7px; background:${bg};">
      <div style="display:flex; align-items:center; gap:7px;">
        <span style="width:22px; height:22px; display:inline-flex; align-items:center; justify-content:center; border-radius:6px; background:${color}; color:#fff; font-weight:800; font-size:13px;">${escAttr(icon)}</span>
        <strong style="font-size:16px; color:#0F172A;">${Number(count) || 0}</strong>
      </div>
      <div style="margin-top:4px; font-size:8.5px; color:#64748B;">${escAttr(label)}</div>
    </div>
  `;
}

function showRevisionPreview(projectId, file, data) {
  const s = data.summary || {};
  const issues = Array.isArray(data.issues) ? data.issues : [];
  const added = Array.isArray(data.added) ? data.added : [];
  const updated = Array.isArray(data.updated) ? data.updated : [];
  const removed = Array.isArray(data.removed) ? data.removed : [];
  const canApply = !data.has_errors;

  const issueHtml = issues.length ? `
    <div style="margin-bottom:12px; padding:9px 10px; border:1px solid ${data.has_errors ? '#FECACA' : '#FDE68A'}; border-radius:6px; background:${data.has_errors ? '#FEF2F2' : '#FFFBEB'}; color:${data.has_errors ? '#B91C1C' : '#92400E'}; font-size:9px;">
      <strong>${data.has_errors ? 'Excel memiliki error.' : 'Catatan validasi:'}</strong>
      ${issues.slice(0, 8).map(issue => `<div style="margin-top:3px;">Row ${escAttr(issue.row)} ·${escAttr(issue.message)}</div>`).join('')}
      ${issues.length > 8 ? `<div style="margin-top:4px; color:#A16207;">+ ${issues.length - 8} issue lainnya</div>` : ''}
    </div>` : '';

  const addedHtml = added.length ? added.map(item => `
    <div class="revision-row added">
      <div class="revision-mark">+</div>
      <div>
        <strong>${escAttr(item.description || '')}</strong>
        <div class="revision-meta">${escAttr(String(item.qty ?? 0))} ${escAttr(item.uom || '')}${item.vendor ? ` · ${escAttr(item.vendor)}` : ''}</div>
      </div>
    </div>`).join('') : `<div class="revision-empty">Tidak ada item baru.</div>`;

  const updatedHtml = updated.length ? updated.map(item => {
    const changeText = Object.entries(item.changes || {}).map(([key, values]) => `<span><b>${escAttr(key)}</b>: ${escAttr(String(values[0] ?? ''))} → ${escAttr(String(values[1] ?? ''))}</span>`).join('<br>');
    return `
      <div class="revision-row updated">
        <div class="revision-mark">~</div>
        <div>
          <strong>${escAttr(item.description || '')}</strong>
          <div class="revision-meta">${changeText}</div>
        </div>
      </div>`;
  }).join('') : `<div class="revision-empty">Tidak ada item yang berubah.</div>`;

  const removedHtml = removed.length ? removed.map(item => `
    <div class="revision-row removed">
      <div class="revision-mark">−</div>
      <div>
        <strong>${escAttr(item.description || '')}</strong>
        <div class="revision-meta">${item.itemNo ? `Item No: ${escAttr(item.itemNo)} · ` : ''}Item ini akan dihapus dari BoQ.</div>
      </div>
    </div>`).join('') : `<div class="revision-empty">Tidak ada item yang dihapus.</div>`;

  const overlay = document.createElement('div');
  overlay.id = 'revision-preview-modal';
  overlay.className = 'overlay';
  overlay.style.zIndex = '110';

  overlay.innerHTML = `
    <div class="modal" style="max-width:780px; max-height:90vh;">
      <div class="modal-hd">
        <div>
          <h3>Review Revisi BoQ</h3>
          <div style="margin-top:3px; font-size:10px; color:#94A3B8;">${escAttr(file.name)}</div>
        </div>
        <button class="mini-btn" type="button" onclick="closeRevisionPreview()">Tutup</button>
      </div>
      <div class="modal-body">
        ${issueHtml}
        <div style="padding:12px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:7px; margin-bottom:14px;">
          <div style="font-size:10px; color:#64748B; margin-bottom:8px;">Perubahan yang akan diterapkan</div>
          <div style="display:grid; grid-template-columns: repeat(4,1fr); gap:7px;">
            ${revisionSummaryCard('+', s.added, 'Added', '#15803D', '#F0FDF4')}
            ${revisionSummaryCard('~', s.updated, 'Updated', '#2563EB', '#EFF6FF')}
            ${revisionSummaryCard('−', s.removed, 'Removed', '#DC2626', '#FEF2F2')}
            ${revisionSummaryCard('=', s.unchanged, 'Unchanged', '#64748B', '#F8FAFC')}
          </div>
        </div>
        <div class="revision-section"><div class="revision-section-title added-title">+ Added (${s.added || 0})</div>${addedHtml}</div>
        <div class="revision-section"><div class="revision-section-title updated-title">~ Updated (${s.updated || 0})</div>${updatedHtml}</div>
        <div class="revision-section"><div class="revision-section-title removed-title">− Removed (${s.removed || 0})</div>${removedHtml}</div>
      </div>
      <div class="modal-ft">
        <button class="btn-ghost" type="button" onclick="closeRevisionPreview()">Batal</button>
        <button class="btn-primary" id="btn-confirm-revision" type="button" ${canApply ? '' : 'disabled'} onclick="confirmRevisionBoq('${escAttr(projectId)}')">
          ${canApply ? 'Confirm & Apply Revision' : 'Perbaiki Error Terlebih Dahulu'}
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);
  window.pendingRevisionFile = file;
}

function closeRevisionPreview() {
  const modal = document.getElementById('revision-preview-modal');
  if (modal) modal.remove();
  window.pendingRevisionFile = null;
}

async function confirmRevisionBoq(projectId) {
  const file = window.pendingRevisionFile;
  if (!file) { alert('File revision tidak ditemukan.'); return; }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('ticket_id', projectId);

  const btn = document.getElementById('btn-confirm-revision');
  if (btn) { btn.disabled = true; btn.innerText = 'Applying revision...'; }

  try {
    const res = await fetch('/api/revisi_boq', { method: 'POST', body: formData });
    const result = await res.json();

    if (res.ok && result.success) {
      closeRevisionPreview();
      alert('BoQ berhasil direvisi.');
      await loadAll();
      return;
    }

    const details = Array.isArray(result.issues) ? '\n' + result.issues.slice(0, 5).map(x => `Row ${x.row}: ${x.message}`).join('\n') : '';
    alert(`Gagal menerapkan revisi: ${result.message || 'Error'}${details}`);
  } catch (error) {
    console.error('Apply revision error:', error);
    alert('Terjadi kesalahan saat menerapkan revisi.');
  } finally {
    if (btn) { btn.disabled = false; btn.innerText = 'Confirm & Apply Revision'; }
  }
}

// ============================================================================
// MODALS LOGIC (RESTORED SPH PER UNIT)
// ============================================================================
function blankProject() {
  return {
    id: uid('proj'), name: '', requestorName: '', requestorDept: '', priority: 'Medium', status: 'ongoing', leadId: team[0] || '', sphMode: 'item', projectSphAwal: null, projectSphFinal: null,
    createdAt: todayStr(), closedAt: null, targetRfs: '', pipelineStage: '1 - Project Identification', progressPct: 0, comparison_docs: [],
    sows: [{ id: uid('sow'), name: '', boqs: [{ id: uid('boq'), name: '', items: [{ id: uid('item'), product: '', qty: 1, vendor: '', notes: '', picIds: [], sphAwalUnit: null, sphFinalUnit: null, sphAwal: null, sphFinal: null }] }] }]
  };
}

function openProjectModal(id) {
  modalScroll = 0; 
  const existing = id ? JSON.parse(JSON.stringify(projects.find(p => p.id === id))) : blankProject();
  modal = { type: 'project', data: existing, isNew: !id };
  render();
}

function openTeamModal() { 
  modalScroll = 0; 
  modal = { type: 'team', data: { names: team.join(', ') } }; 
  render(); 
}

function renderModal() {
  let root = document.getElementById('modal-root');
  if (!root) { root = document.createElement('div'); root.id = 'modal-root'; document.body.appendChild(root); }
  
  if (modal.type === 'project') root.innerHTML = projectModalHtml(modal.data, modal.isNew);
  if (modal.type === 'team') root.innerHTML = teamModalHtml(modal.data);
  
  wireModalEvents();
  const m = document.querySelector('.modal');
  if (m) m.scrollTop = modalScroll;
}

// ... (Gunakan fungsi projectModalHtml() persis dari kode Anda, namun fungsi itemBlockHtml di bawah INI 
// telah diperbaiki agar kembali mendukung SPH per Unit & auto-calculate) ...

function itemBlockHtml(it, si, bi, ii) {
  const path = `${si}:${bi}:${ii}`;
  const awalTotal = calculateUiSphTotal(it.qty, it.sphAwalUnit) ?? it.sphAwal;
  const finalTotal = calculateUiSphTotal(it.qty, it.sphFinalUnit) ?? it.sphFinal;

  return `
    <div class="item-block" data-item-idx="${ii}">
      <div class="item-head">
        <div class="item-label">Item ${ii + 1}</div>
        <button class="mini-btn danger form-danger-btn" data-del-item="${path}" type="button">Hapus</button>
      </div>
      <div class="item-grid-main">
        <div class="field"><label>Produk</label><input class="it-product" data-path="${path}" value="${escAttr(it.product)}" placeholder="Nama produk / service"></div>
        <div class="field"><label>Qty</label><input type="number" class="it-qty" data-path="${path}" value="${it.qty ?? 1}" min="0"></div>
        <div class="field"><label>UoM</label><input class="it-uom" data-path="${path}" value="${escAttr(it.uom)}" placeholder="Unit"></div>
        <div class="field"><label>Vendor</label><input class="it-vendor" data-path="${path}" value="${escAttr(it.vendor)}" placeholder="Vendor"></div>
      </div>
      <div class="item-grid-finance">
        <div class="field">
          <label>SPH Awal / Unit</label>
          <input type="number" class="it-awal-unit" data-path="${path}" value="${it.sphAwalUnit ?? ''}" placeholder="Harga per unit">
          <div style="margin-top:4px; font-size:9.5px; color:#64748B;">Total: <strong data-total-awal="${path}" style="color:#0F172A;">${fmtIdr(awalTotal)}</strong></div>
        </div>
        <div class="field">
          <label>SPH Final / Unit</label>
          <input type="number" class="it-final-unit" data-path="${path}" value="${it.sphFinalUnit ?? ''}" placeholder="Harga per unit">
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

function updateItemFinancialPreview(input) {
  const path = input.dataset.path;
  if (!path) return;

  const qtyInput = document.querySelector('.it-qty[data-path="' + path + '"]');
  const awalInput = document.querySelector('.it-awal-unit[data-path="' + path + '"]');
  const finalInput = document.querySelector('.it-final-unit[data-path="' + path + '"]');
  const awalTotal = document.querySelector('[data-total-awal="' + path + '"]');
  const finalTotal = document.querySelector('[data-total-final="' + path + '"]');

  const totalAwal = calculateUiSphTotal(qtyInput?.value, awalInput?.value);
  const totalFinal = calculateUiSphTotal(qtyInput?.value, finalInput?.value);

  if (awalTotal) awalTotal.textContent = totalAwal == null ? '—' : fmtIdr(totalAwal);
  if (finalTotal) finalTotal.textContent = totalFinal == null ? '—' : fmtIdr(totalFinal);
}

function syncModalData() {
  if (!modal || modal.type !== 'project') return;
  const m = document.querySelector('.modal');
  if (m) modalScroll = m.scrollTop;
  
  const d = modal.data;
  d.name = val('m-name'); d.requestorName = val('m-req-name'); d.requestorDept = val('m-req-dept');
  d.priority = val('m-priority'); d.status = val('m-status'); d.leadId = val('m-lead');
  d.targetRfs = val('m-target-rfs'); d.pipelineStage = val('m-pipeline-stage'); d.progressPct = numOrNull(val('m-progress')) || 0;
  d.sphMode = val('m-sphmode');
  
  if (d.sphMode === 'project') {
    d.projectSphAwal = numOrNull(document.getElementById('m-proj-awal').value);
    d.projectSphFinal = numOrNull(document.getElementById('m-proj-final').value);
  }

  document.querySelectorAll('.sow-name').forEach(el => d.sows[+el.dataset.si].name = el.value);
  document.querySelectorAll('.boq-name').forEach(el => d.sows[+el.dataset.si].boqs[+el.dataset.bi].name = el.value);
  
  const syncPathField = (selector, setter) => {
    document.querySelectorAll(selector).forEach(el => {
      const [si, bi, ii] = el.dataset.path.split(':').map(Number);
      setter(d.sows[si].boqs[bi].items[ii], el.value);
    });
  };

  syncPathField('.it-product', (item, value) => { item.product = value; });
  syncPathField('.it-qty', (item, value) => { item.qty = numOrNull(value); });
  syncPathField('.it-uom', (item, value) => { item.uom = value; });
  syncPathField('.it-vendor', (item, value) => { item.vendor = value; });

  // PENGEMBALIAN LOGIKA UNIT PRICE YANG BENAR
  syncPathField('.it-awal-unit', (item, value) => {
    item.sphAwalUnit = numOrNull(value);
    item.sphAwal = calculateUiSphTotal(item.qty, item.sphAwalUnit);
  });
  syncPathField('.it-final-unit', (item, value) => {
    item.sphFinalUnit = numOrNull(value);
    item.sphFinal = calculateUiSphTotal(item.qty, item.sphFinalUnit);
  });
}

function wireModalEvents() {
  if (!modal) return;
  const close = () => { modal = null; document.getElementById('modal-root').innerHTML = ''; render(); };
  
  const c1 = document.getElementById('m-close'); if (c1) c1.onclick = close;
  const c2 = document.getElementById('m-cancel'); if (c2) c2.onclick = close;
  const ov = document.getElementById('ov'); if (ov) ov.onclick = (e) => { if (e.target === ov) close(); };

  if (modal.type === 'team') {
    const sBtn = document.getElementById('m-save-team');
    if (sBtn) sBtn.onclick = () => { team = val('m-team-names').split(',').map(s => s.trim()).filter(Boolean); modal = null; render(); saveAll(); };
    return;
  }
  
  const sphmode = document.getElementById('m-sphmode');
  if (sphmode) sphmode.onchange = () => { syncModalData(); modal.data.sphMode = sphmode.value; render(); };

  // Trigger update real-time preview (Harga * Qty) saat mengetik
  document.querySelectorAll('.it-qty, .it-awal-unit, .it-final-unit').forEach(el => {
    el.addEventListener('input', () => updateItemFinancialPreview(el));
  });

  // (Kode Import BoQ di dalam wireModalEvents dari file Anda tetap berlaku di sini, jangan dihapus)

  document.getElementById('m-add-sow').onclick = () => { syncModalData(); modal.data.sows.push({id:uid('sow'), name:'', boqs:[{id:uid('boq'), name:'', items:[{id:uid('item'), product:'', qty:1, vendor:'', picIds:[], sphAwalUnit:null, sphFinalUnit:null, sphAwal:null, sphFinal:null}]}]}); render(); };
  document.querySelectorAll('[data-add-boq]').forEach(el => el.onclick = () => { syncModalData(); modal.data.sows[+el.dataset.addBoq].boqs.push({id:uid('boq'), name:'', items:[{id:uid('item'), product:'', qty:1, vendor:'', picIds:[], sphAwalUnit:null, sphFinalUnit:null, sphAwal:null, sphFinal:null}]}); render(); });
  document.querySelectorAll('[data-add-item]').forEach(el => { const [si,bi] = el.dataset.addItem.split(':').map(Number); el.onclick = () => { syncModalData(); modal.data.sows[si].boqs[bi].items.push({id:uid('item'), product:'', qty:1, vendor:'', picIds:[], sphAwalUnit:null, sphFinalUnit:null, sphAwal:null, sphFinal:null}); render(); }; });
  document.querySelectorAll('[data-del-sow]').forEach(el => el.onclick = () => { syncModalData(); modal.data.sows.splice(+el.dataset.delSow,1); render(); });
  document.querySelectorAll('[data-del-boq]').forEach(el => { const [si,bi] = el.dataset.delBoq.split(':').map(Number); el.onclick = () => { syncModalData(); modal.data.sows[si].boqs.splice(bi,1); render(); }; });
  document.querySelectorAll('[data-del-item]').forEach(el => { const [si,bi,ii] = el.dataset.delItem.split(':').map(Number); el.onclick = () => { syncModalData(); modal.data.sows[si].boqs[bi].items.splice(ii,1); render(); }; });
  document.querySelectorAll('[data-pic]').forEach(el => { const [si,bi,ii,name] = el.dataset.pic.split(':'); el.onclick = () => { syncModalData(); const arr = modal.data.sows[+si].boqs[+bi].items[+ii].picIds; const idx = arr.indexOf(name); if(idx>=0) arr.splice(idx,1); else arr.push(name); render(); }; });

  document.getElementById('m-save').onclick = () => { syncModalData(); const d = modal.data; const idx = projects.findIndex(p => p.id === d.id); if (idx >= 0) projects[idx] = d; else projects.push(d); document.getElementById('modal-root').innerHTML = ''; modal = null; render(); saveAll(); };
}

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
  formData.append('ticket_id', projectId); 
  formData.append('vendor_name', name); 
  formData.append('offered_price', price); 
  formData.append('file', file);
  
  document.body.style.cursor = 'wait';
  try {
    const res = await fetch('/api/upload_comparison', { method: 'POST', body: formData });
    const result = await res.json();
    if (res.ok && result.success) { 
      alert("Dokumen berhasil ditambahkan!"); 
      closeUploadPembandingModal(); 
      loadAll(); 
    } else {
      alert(`Gagal: ${result.message}`);
    }
  } catch (err) {
    alert("Terjadi kesalahan sistem."); 
    closeUploadPembandingModal();
  } finally { 
    document.body.style.cursor = 'default'; 
  }
}
loadAll();