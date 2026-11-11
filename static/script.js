// ============================================================================
// STATE & CONFIGURATION
// ============================================================================
const API_URL = '/api/presourcing';

let projects = [];
let team = [];
let activeTab = 'overview';
let openProjectId = null;
let modal = null; 
let filters = { priority: 'all', status: 'all' };
let storageOk = false;
let isSaving = false;
let presourcingVersion = null;
let presourcingLegacyMode = false;
let presourcingConflict = false;
let confirmedProjectDeletions = new Set();
let knownServerProjectIds = new Set();
let inFlightProjectIds = new Set();
let selectedTeamMember = null;
let saveInFlight = null;
let saveRequested = false;
let queuedAllowEmptyProjects = false;
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
async function loadAll() {
  // Wait for a pending save to settle before replacing local state with a fresh GET.
  if (saveInFlight) {
    const saveSucceeded = await saveInFlight;
    if (!saveSucceeded) return false;
  }
  // A conflict requires a deliberate full page reload; do not silently discard
  // unsaved local edits through an incidental loadAll() call.
  if (presourcingConflict) return false;
  try {
    const response = await fetch(`${API_URL}?t=${Date.now()}`, { cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.message || data.error || `Backend returned HTTP ${response.status}`);
    }
    // The dashboard data contract is independent of the concurrency token. During
    // a rolling deployment, Phase 2 frontend may temporarily meet a Phase 1 backend.
    // It must still render valid project/team data rather than showing an empty page.
    if (!Array.isArray(data.projects) || !Array.isArray(data.team)) {
      throw new Error('Respons backend tidak memiliki projects dan team yang valid.');
    }

    projects = data.projects;
    team = data.team.length ? data.team : [
      'Decki Okmal Pratama', 'Ahmad Fauzi', 'Siti Rahma', 'Budi Santoso'
    ];
    presourcingVersion = (typeof data.version === 'string' && data.version.trim())
      ? data.version.trim()
      : null;
    presourcingLegacyMode = !presourcingVersion;
    presourcingConflict = false;
    confirmedProjectDeletions.clear();
    knownServerProjectIds = new Set(projects.map(project => String(project.id)));
    inFlightProjectIds.clear();
    storageOk = true;
  } catch (error) {
    console.error('Backend error/offline:', error);
    storageOk = false;
    // Never replace unavailable server data with demo data. Keep current in-memory
    // state visible, but saveAll() will refuse writes until a successful reload.
  }
  render();
  return storageOk;
}

function confirmExistingProjectDeletion(projectId) {
  const id = String(projectId);
  // A just-created project that has never been sent to the server is not a DB deletion.
  // Include in-flight IDs because that request may commit before the queued delete save.
  if (knownServerProjectIds.has(id) || inFlightProjectIds.has(id)) {
    confirmedProjectDeletions.add(id);
  }
}

async function saveAll(options = {}) {
  if (!storageOk || presourcingConflict || (!presourcingLegacyMode && !presourcingVersion)) {
    const message = 'Data belum tersinkron atau terjadi konflik versi. Muat ulang dashboard dan periksa data server sebelum menyimpan kembali.';
    console.error(message);
    alert(message);
    return false;
  }

  saveRequested = true;
  if (options.allowEmptyProjects === true) queuedAllowEmptyProjects = true;
  if (saveInFlight) return saveInFlight;

  saveInFlight = (async () => {
    let allSaved = true;
    isSaving = true;
    document.body.style.cursor = 'wait';

    try {
      while (saveRequested) {
        saveRequested = false;
        const allowEmptyProjects = queuedAllowEmptyProjects;
        queuedAllowEmptyProjects = false;
        const confirmedDeleteIds = [...confirmedProjectDeletions];
        // Phase 1 backend ignores the extra deletion field. Phase 2 backend validates
        // it against the exact set of project IDs omitted from the submitted snapshot.
        const payload = {
          projects,
          team,
          confirmed_delete_project_ids: confirmedDeleteIds
        };
        if (!presourcingLegacyMode) {
          payload.base_version = presourcingVersion;
          payload.allow_empty_projects = allowEmptyProjects;
        }

        inFlightProjectIds = new Set(payload.projects.map(project => String(project.id)));
        const response = await fetch(API_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await response.json().catch(() => ({}));

        if (response.status === 409 || response.status === 428 ||
            result.code === 'PRESOURCING_VERSION_CONFLICT' ||
            result.code === 'PRESOURCING_VERSION_REQUIRED' ||
            result.code === 'EMPTY_PROJECT_SET_CONFIRMATION_REQUIRED' ||
            result.code === 'PROJECT_DELETION_CONFIRMATION_REQUIRED') {
          presourcingConflict = true;
          allSaved = false;
          saveRequested = false;
          inFlightProjectIds.clear();
          const message = result.message || 'Data server berubah. Muat ulang dashboard sebelum melanjutkan.';
          alert(`${message}\n\nPerubahan lokal belum dikirim ulang agar tidak menimpa data terbaru.`);
          break;
        }

        if (!response.ok || result.success !== true) {
          throw new Error(result.message || result.error || `Gagal menyimpan (HTTP ${response.status}).`);
        }

        if (presourcingLegacyMode) {
          // Legacy Phase 1 API returns { success: true } without a version token.
          // Keep the queued save behavior, but concurrency protection is unavailable.
          storageOk = true;
        } else {
          if (typeof result.version !== 'string' || !result.version) {
            throw new Error('Backend Phase 2 tidak mengembalikan version token setelah save. Status penyimpanan perlu diverifikasi.');
          }
          presourcingVersion = result.version;
          storageOk = true;
        }

        knownServerProjectIds = new Set(payload.projects.map(project => String(project.id)));
        confirmedDeleteIds.forEach(id => confirmedProjectDeletions.delete(id));
        inFlightProjectIds.clear();
      }
    } catch (error) {
      console.error('Gagal menyimpan data:', error);
      storageOk = false;
      presourcingConflict = true;
      saveRequested = false;
      queuedAllowEmptyProjects = false;
      inFlightProjectIds.clear();
      allSaved = false;
      alert('Penyimpanan gagal atau status respons tidak pasti. Jangan ulangi perubahan sebelum memuat ulang dan memeriksa data server.');
    } finally {
      isSaving = false;
      document.body.style.cursor = 'default';
      saveInFlight = null;
      render();
    }
    return allSaved;
  })();

  return saveInFlight;
}

// ============================================================================
// COMPUTATIONS
// ============================================================================
function allItems(proj) {
  const out = []; 
  (proj.sows || []).forEach(s => (s.boqs || []).forEach(b => (b.items || []).forEach(it => out.push(it)))); 
  return out;
}

// UPDATE LOGIKA 1: Perhitungan Efisiensi Parsial
function projectSph(proj) {
  if (proj.sphMode === 'project') return { awal: proj.projectSphAwal, final: proj.projectSphFinal };
  
  const items = allItems(proj);
  let awal = 0, final = 0, hasAwal = false;
  
  items.forEach(it => {
    let itemAwal = 0;
    
    // Tambahkan SPH Awal jika ada
    if (it.sphAwal != null) { 
      itemAwal = Number(it.sphAwal);
      awal += itemAwal; 
      hasAwal = true; 
    }
    
    // Evaluasi SPH Final parsial
    if (it.sphFinal != null) { 
      final += Number(it.sphFinal); 
    } else { 
      // Jika SPH Final kosong, anggap harganya sama dengan SPH Awal (Efisiensi 0%)
      final += itemAwal; 
    }
  });
  
  // Jika ada SPH awal, kita bisa mereturn SPH Awal dan perhitungan kumulatif Final
  return { 
    awal: hasAwal ? awal : null, 
    final: hasAwal ? final : null 
  };
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

function normalizeTeamKey(name) {
  return String(name || '').trim().toLocaleLowerCase('id-ID');
}

function collectKnownTeamNames() {
  const names = new Map();
  (team || []).forEach(name => {
    const clean = String(name || '').trim();
    if (clean && !names.has(normalizeTeamKey(clean))) names.set(normalizeTeamKey(clean), clean);
  });
  // Keep workload visible even when a stale assignment references a name
  // that is missing from the Team master list.
  projects.forEach(project => {
    const lead = String(project.leadId || '').trim();
    if (lead && !names.has(normalizeTeamKey(lead))) names.set(normalizeTeamKey(lead), lead);
    allItems(project).forEach(item => (Array.isArray(item.picIds) ? item.picIds : []).forEach(pic => {
      const clean = String(pic || '').trim();
      if (clean && !names.has(normalizeTeamKey(clean))) names.set(normalizeTeamKey(clean), clean);
    }));
  });
  return [...names.values()];
}

function buildTeamMemberUpdate(rows) {
  if (!Array.isArray(rows)) throw new Error('Daftar anggota tim tidak valid.');
  const cleanRows = rows.map(row => ({ oldName: String(row.oldName || '').trim(), name: String(row.name || '').trim() }));
  if (cleanRows.some(row => !row.name)) throw new Error('Nama anggota tidak boleh kosong.');
  const normalizedNames = cleanRows.map(row => normalizeTeamKey(row.name));
  if (new Set(normalizedNames).size !== normalizedNames.length) throw new Error('Nama anggota duplikat. Periksa kembali daftar tim.');

  const retainedOld = new Set(cleanRows.map(row => normalizeTeamKey(row.oldName)).filter(Boolean));
  const removed = collectKnownTeamNames().filter(name => !retainedOld.has(normalizeTeamKey(name)));
  const referenced = [];
  removed.forEach(name => {
    const key = normalizeTeamKey(name);
    projects.forEach(project => {
      const isLead = normalizeTeamKey(project.leadId) === key;
      const assignedItems = allItems(project).filter(item => (Array.isArray(item.picIds) ? item.picIds : []).some(pic => normalizeTeamKey(pic) === key));
      if (isLead || assignedItems.length) referenced.push(`${project.name || project.id} (${isLead ? 'Lead' : ''}${isLead && assignedItems.length ? ', ' : ''}${assignedItems.length ? `${assignedItems.length} item PIC` : ''})`);
    });
  });
  if (referenced.length) throw new Error('Anggota yang masih memiliki assignment tidak dapat dihapus: ' + [...new Set(removed)].join(', ') + '. Project terkait: ' + [...new Set(referenced)].join('; '));

  const nextProjects = JSON.parse(JSON.stringify(projects));
  const renameMap = new Map(cleanRows.filter(row => row.oldName && row.oldName !== row.name)
    .map(row => [normalizeTeamKey(row.oldName), row.name]));
  nextProjects.forEach(project => {
    const leadKey = normalizeTeamKey(project.leadId);
    if (renameMap.has(leadKey)) project.leadId = renameMap.get(leadKey);
    allItems(project).forEach(item => {
      item.picIds = [...new Set((Array.isArray(item.picIds) ? item.picIds : []).map(pic => renameMap.get(normalizeTeamKey(pic)) || String(pic || '').trim()).filter(Boolean))];
    });
  });
  return { team: cleanRows.map(row => row.name), projects: nextProjects };
}

function projectIsActiveForTeam(project) {
  // Match the dashboard's existing active-project definition.
  return project && project.status === 'ongoing';
}

function computeTeamWorkload() {
  const members = new Map();
  const ensureMember = (name) => {
    const clean = String(name || '').trim();
    if (!clean) return null;
    const key = normalizeTeamKey(clean);
    if (!members.has(key)) {
      members.set(key, {
        key,
        name: clean,
        inTeam: (team || []).some(member => normalizeTeamKey(member) === key),
        leadProjects: new Map(),
        involvedProjects: new Map(),
        itemAssignments: 0,
        completedProjects: new Map(),
        wonProjects: 0,
        lostProjects: 0
      });
    }
    return members.get(key);
  };

  (team || []).forEach(ensureMember);

  projects.forEach(project => {
    const projectId = String(project.id || '');
    const isCompleted = project.status === 'win' || project.status === 'lose';
    const lead = ensureMember(project.leadId);
    if (lead) lead.leadProjects.set(projectId, project);

    const itemAssignmentsByMember = new Map();
    allItems(project).forEach((item, itemIndex) => {
      const itemId = String(item.id || `${projectId}:item:${itemIndex}`);
      const picNames = [...new Map((Array.isArray(item.picIds) ? item.picIds : [])
        .map(value => String(value || '').trim())
        .filter(Boolean)
        .map(value => [normalizeTeamKey(value), value])).values()];
      picNames.forEach(picName => {
        const member = ensureMember(picName);
        if (!member) return;
        const key = member.key;
        member.itemAssignments += 1;
        if (!itemAssignmentsByMember.has(key)) itemAssignmentsByMember.set(key, []);
        itemAssignmentsByMember.get(key).push({
          id: itemId,
          itemNo: item.itemNo || '',
          product: item.product || 'Item tanpa deskripsi',
          qty: item.qty,
          uom: item.uom || '',
          sowName: '',
          boqName: ''
        });
      });
    });

    itemAssignmentsByMember.forEach((assignedItems, key) => {
      const member = members.get(key);
      if (!member) return;
      member.involvedProjects.set(projectId, { project, items: assignedItems });
    });

    if (isCompleted) {
      const participants = new Set();
      if (lead) participants.add(lead.key);
      itemAssignmentsByMember.forEach((_, key) => participants.add(key));
      participants.forEach(key => {
        const member = members.get(key);
        if (!member) return;
        member.completedProjects.set(projectId, project);
        if (project.status === 'win') member.wonProjects += 1;
        if (project.status === 'lose') member.lostProjects += 1;
      });
    }
  });

  const rows = [...members.values()].map(member => {
    const leadProjects = [...member.leadProjects.values()];
    const involvedEntries = [...member.involvedProjects.values()];
    const leadActive = leadProjects.filter(projectIsActiveForTeam).length;
    const involvedActive = involvedEntries.filter(entry => projectIsActiveForTeam(entry.project)).length;
    const leadIds = new Set(leadProjects.filter(projectIsActiveForTeam).map(project => String(project.id)));
    const involvedIds = new Set(involvedEntries.filter(entry => projectIsActiveForTeam(entry.project)).map(entry => String(entry.project.id)));
    const both = [...leadIds].filter(id => involvedIds.has(id)).length;
    const uniqueActive = new Set([...leadIds, ...involvedIds]).size;
    const completedCount = member.completedProjects.size;
    const winRate = completedCount ? (member.wonProjects / completedCount) * 100 : null;
    return {
      ...member,
      leadCount: leadProjects.length,
      involvedCount: involvedEntries.length,
      leadActive,
      involvedActive,
      bothActive: both,
      leadOnlyActive: leadActive - both,
      involvedOnlyActive: involvedActive - both,
      uniqueActive,
      completedCount,
      winRate,
      leadProjectList: leadProjects.sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''))),
      involvedProjectList: involvedEntries.sort((a, b) => String(a.project.name || '').localeCompare(String(b.project.name || '')))
    };
  }).sort((a, b) => b.uniqueActive - a.uniqueActive || b.itemAssignments - a.itemAssignments || a.name.localeCompare(b.name));

  const activeProjects = projects.filter(projectIsActiveForTeam);
  const unassignedActive = activeProjects.filter(project => {
    const hasLead = Boolean(String(project.leadId || '').trim());
    const hasPic = allItems(project).some(item => Array.isArray(item.picIds) && item.picIds.some(pic => String(pic || '').trim()));
    return !hasLead && !hasPic;
  }).length;

  return {
    members: rows,
    totalMembers: rows.length,
    activeProjects: activeProjects.length,
    leadAssignments: rows.reduce((sum, row) => sum + row.leadActive, 0),
    involvementAssignments: rows.reduce((sum, row) => sum + row.involvedActive, 0),
    uniqueMemberProjectAssignments: rows.reduce((sum, row) => sum + row.uniqueActive, 0),
    unassignedActive
  };
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
  const currentWindowScroll = window.scrollY;
  const modalContainer = document.querySelector('.modal-body') || document.querySelector('.modal') || document.querySelector('.overlay');
  const currentModalScroll = modalContainer ? modalContainer.scrollTop : 0;

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
          <div class="data-date"><span>Data per: </span><strong>${dateText}</strong></div>
        </div>
      </div>
    `;
  } else if (activeTab === 'projects') {
    headerHtml = `<div class="page-hero"><div class="page-hero-main"><div class="page-hero-title">Project &amp; BoQ Management</div><div class="page-hero-sub">Detail project, BoQ, SPH, dan progress</div></div></div>`;
  } else if (activeTab === 'team') {
    headerHtml = `<div class="page-hero"><div class="page-hero-main"><div class="page-hero-title">Team &amp; Workload</div><div class="page-hero-sub">Distribusi project dan beban kerja tim</div></div></div>`;
  }

  const persistenceNotice = !storageOk
    ? `<div class="persistence-notice error">Koneksi atau respons backend belum valid. Data server belum berhasil dimuat; jangan melakukan perubahan sampai koneksi pulih.</div>`
    : presourcingConflict
      ? `<div class="persistence-notice error">Penyimpanan ditahan karena konflik atau respons tidak pasti. Muat ulang dashboard setelah memeriksa data server.</div>`
      : presourcingLegacyMode
        ? `<div class="persistence-notice warning">Mode kompatibilitas Phase 1: data tetap ditampilkan dan dapat disimpan, tetapi perlindungan konflik antar-user Phase 2 belum aktif pada backend.</div>`
        : '';
  app.innerHTML = `<div class="page-shell"><style>.persistence-notice{padding:10px 14px;margin:0 0 12px;border-radius:8px;font-size:12px;line-height:1.45}.persistence-notice.warning{background:#FFF7ED;color:#9A3412;border:1px solid #FED7AA}.persistence-notice.error{background:#FEF2F2;color:#991B1B;border:1px solid #FECACA}</style>${persistenceNotice}${headerHtml}<div id="tabcontent"></div></div>`;
  const content = document.getElementById('tabcontent');
  
  if (activeTab === 'overview') content.innerHTML = renderOverview();
  else if (activeTab === 'projects') content.innerHTML = renderProjects();
  else if (activeTab === 'team') content.innerHTML = renderTeam();

  wireEvents();
  if (modal) renderModal();
  document.querySelectorAll('.app-nav-item').forEach(el => el.classList.toggle('active', el.dataset.tab === activeTab));

  setTimeout(() => {
    window.scrollTo(0, currentWindowScroll);
    const newModalContainer = document.querySelector('.modal-body') || document.querySelector('.modal') || document.querySelector('.overlay');
    if (newModalContainer) {
      newModalContainer.scrollTop = currentModalScroll;
    }
  }, 0);
}

// ============================================================================
// RENDER OVERVIEW: EXECUTIVE DASHBOARD
// ============================================================================
function renderOverview() {
  const totalProj = projects.length;
  let totalVal = 0;

  const sCount = {
    'On Track': 0,
    'At Risk': 0,
    'Overdue': 0,
    'Completed': 0,
    'Planned': 0
  };

  const pCount = {
    1: 0,
    2: 0,
    3: 0,
    4: 0,
    5: 0,
    6: 0
  };

  projects.forEach(p => {
    totalVal += (projectSph(p).awal || 0);

    const status = getDynamicStatus(p);
    if (sCount[status] !== undefined) {
      sCount[status]++;
    }
  });

  const activeProjectsData = projects.filter(
    p => p.status === 'ongoing'
  );

  const activeProjects = activeProjectsData.length;

  activeProjectsData.forEach(p => {
    let stage = parseInt(
      String(p.pipelineStage || '').charAt(0)
    );

    if (isNaN(stage) || stage < 1 || stage > 6) {
      stage = 1;
    }

    pCount[stage]++;
  });

  const efficiencies = projects
    .map(p =>
      efficiencyPct(
        projectSph(p).awal,
        projectSph(p).final
      )
    )
    .filter(v => v != null && isFinite(v));

  const avgEfficiency = efficiencies.length
    ? efficiencies.reduce((a, b) => a + b, 0) / efficiencies.length
    : null;

  const getPct = val =>
    totalProj
      ? Math.round((val / totalProj) * 100)
      : 0;

  const atRisk = sCount['At Risk'];
  const overdue = sCount['Overdue'];

  if (
    !window.Chart &&
    !document.getElementById('chartjs-script')
  ) {
    const script = document.createElement('script');

    script.id = 'chartjs-script';
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js';

    script.onload = () => {
      setTimeout(renderDashboardCharts, 100);
    };

    document.head.appendChild(script);
  } else {
    setTimeout(renderDashboardCharts, 80);
  }

  const dashStyles = `
    <style>
      .page-shell { width: 100%; max-width: 1420px; margin: 0 auto; padding-top: 24px; }
      .page-hero { min-height: 76px; display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 12px 18px; margin-bottom: 12px; border-radius: 10px; color: #fff; background: linear-gradient(115deg, #0B4F91 0%, #1769C2 58%, #2583DA 100%); box-shadow: 0 4px 12px rgba(15,23,42,.12); position: relative; overflow: hidden; }
      .page-hero::after { content: ''; position: absolute; width: 260px; height: 160px; right: -70px; top: -90px; background: rgba(255,255,255,.07); transform: rotate(28deg); pointer-events: none; }
      .page-hero-main { position: relative; z-index: 1; min-width: 0; }
      .page-hero-title { font-size: 22px; line-height: 1.1; font-weight: 700; letter-spacing: .01em; }
      .page-hero-sub { margin-top: 5px; font-size: 11px; color: rgba(255,255,255,.78); }
      .page-hero-side { display: flex; align-items: center; gap: 10px; position: relative; z-index: 1; }
      .objective-box { display: flex; align-items: center; gap: 8px; padding: 7px 11px; min-width: 230px; border: 1px solid rgba(255,255,255,.25); border-radius: 7px; background: rgba(255,255,255,.08); }
      .objective-icon { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: 50%; border: 2px solid rgba(255,255,255,.85); font-size: 15px; font-weight: 700; }
      .objective-label { font-size: 9px; font-weight: 700; color: rgba(255,255,255,.92); text-transform: uppercase; letter-spacing: .05em; }
      .objective-text { margin-top: 2px; font-size: 9.5px; line-height: 1.25; color: rgba(255,255,255,.78); max-width: 210px; }
      .data-date { display: flex; flex-direction: column; gap: 2px; padding: 7px 11px; border: 1px solid rgba(255,255,255,.20); border-radius: 7px; min-width: 110px; }
      .data-date span { font-size: 8.5px; color: rgba(255,255,255,.65); }
      .data-date strong { font-size: 9.5px; color: #fff; }
      .exec-kpis { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 9px; margin-bottom: 12px; }
      .exec-kpi { min-height: 72px; padding: 10px 11px; display: flex; align-items: center; gap: 9px; border: 1px solid #dbe3ec; border-radius: 8px; background: #fff; position: relative; overflow: hidden; box-shadow: 0 1px 3px rgba(15,23,42,.04); }
      .exec-kpi::after { content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: #3B82F6; }
      .exec-kpi:nth-child(2)::after { background: #6366F1; }
      .exec-kpi.green::after { background: #16A34A; }
      .exec-kpi.yellow::after { background: #F59E0B; }
      .exec-kpi.red::after { background: #DC2626; }
      .exec-kpi.gray::after { background: #94A3B8; }
      .exec-kpi-icon { width: 32px; height: 32px; flex: 0 0 32px; display: flex; align-items: center; justify-content: center; border-radius: 7px; background: #F1F5F9; color: #64748B; font-size: 15px; }
      .exec-kpi-label { font-size: 9.5px; color: #64748B; margin-bottom: 3px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; }
      .exec-kpi-value { font-size: 18px; font-weight: 700; color: #0F172A; line-height: 1.1; }
      .exec-kpi-value small { font-size: 9.5px; color: #16A34A; font-weight: 600; }
      .exec-kpi-meta { font-size: 8.5px; color: #94A3B8; margin-top: 4px; }
      .exec-kpi-progress { height: 4px; background: #E2E8F0; border-radius: 2px; margin-top: 6px; overflow: hidden; width: 100%; }
      .exec-kpi-progress span { display: block; height: 100%; border-radius: 2px; }
      /* =====================================================
         PANELS DIBUAT FLEXBOX
         ===================================================== */
      .exec-panel { 
        min-width: 0; background: #FFFFFF; border: 1px solid #DCE4EE; border-radius: 8px; 
        overflow: hidden; box-shadow: 0 2px 4px rgba(15,23,42,.04); 
        display: flex; flex-direction: column; 
      }
      .exec-panel-head { 
        min-height: 42px; padding: 11px 14px; display: flex; align-items: center; gap: 5px; 
        background: linear-gradient(90deg, #0F5CA8 0%, #1672C8 100%); color: #FFFFFF; 
        font-size: 12px; font-weight: 700; flex-shrink: 0; 
      }
      .exec-panel.warning .exec-panel-head { background: linear-gradient(90deg, #DC2626 0%, #EF4444 100%); }
      .exec-panel.warning .exec-panel-sub { color: #FFFFFF; opacity: .9; }
      .exec-panel.warning { border-color: #FECACA; }
      .exec-panel.warning .warning-summary { background: #FEF2F2; border-bottom-color: #FECACA; flex-shrink: 0; }
      .exec-panel.warning .warning-box { border-color: #FECACA; background: #FFFFFF; }
      .exec-panel.warning .warning-label { color: #B91C1C; }
      .exec-panel.warning .warning-value { color: #991B1B; }
      .exec-panel-sub { margin-left: auto; font-size: 9px; font-weight: 500; opacity: .8; }
      
      .exec-panel-body { padding: 10px; flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: center; }

      /* =====================================================
         KUNCI TINGGI BARIS (230px) AGAR SEJAJAR SEMPURNA
         ===================================================== */
      .exec-panel.overview { grid-area: overview; height: 230px; }
      .exec-panel.status { grid-area: status; height: 230px; }
      .exec-panel.pic { grid-area: pic; height: 230px; }
      .exec-panel.pipeline { grid-area: pipeline; height: 215px; }
      .exec-panel.rfs { grid-area: rfs; height: 215px; }
      .exec-panel.top5 { grid-area: top5; height: 230px; }
      .exec-panel.warning { grid-area: warning; height: 230px; }

      /* =====================================================
         TABEL MENGISI SISA RUANG & BISA DI-SCROLL
         ===================================================== */
      .exec-table-wrap { 
        width: 100%; 
        flex: 1; min-height: 0; 
        overflow-y: auto; overflow-x: auto; 
      }
      .exec-table-wrap::-webkit-scrollbar { width: 6px; height: 6px; }
      .exec-table-wrap::-webkit-scrollbar-track { background: transparent; }
      .exec-table-wrap::-webkit-scrollbar-thumb { background-color: #cbd5e1; border-radius: 10px; }
      
      .exec-table { width: 100%; border-collapse: separate; border-spacing: 0; table-layout: auto; }
      .exec-table th { position: sticky; top: 0; z-index: 10; padding: 8px 7px; background: #F4F7FB; color: #64748B; font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; white-space: nowrap; text-align: left; box-shadow: inset 0 -1px 0 #DCE4EE; }
      .exec-table td { padding: 8px 7px; border-bottom: 1px solid #EEF2F6; color: #334155; font-size: 9.5px; line-height: 1.3; vertical-align: middle; }
      .exec-table tbody tr:last-child td { border-bottom: 0; }
      .exec-table .mono { font-size: 9px; white-space: nowrap; }
      
      .exec-project-name { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; color: #0F172A; }
      .exec-project-pic { margin-top: 2px; color: #94A3B8; font-size: 8px; }
      .exec-progress { display: flex; align-items: center; gap: 4px; }
      .exec-progress-value { width: 25px; text-align: right; font-size: 8.5px; font-weight: 600; }
      .exec-progress-bg { width: 38px; height: 4px; border-radius: 8px; overflow: hidden; background: #E2E8F0; }
      .exec-progress-fill { height: 100%; background: #2583DA; border-radius: 8px; }
      .exec-chart { height: 150px; position: relative; width: 100%; }
      .exec-chart canvas { width: 100% !important; height: 100% !important; }
      .exec-donut { height: 150px; position: relative; }
      .exec-donut canvas { width: 100% !important; height: 100% !important; }
      .exec-donut-center { position: absolute; left: 37%; top: 50%; transform: translate(-50%, -50%); text-align: center; pointer-events: none; }
      .exec-donut-number { font-size: 22px; line-height: 1; font-weight: 700; color: #0F172A; }
      .exec-donut-label { margin-top: 2px; font-size: 8px; color: #64748B; }
      .warning-summary { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; padding: 7px; background: #FFFBEB; border-bottom: 1px solid #FDE68A; }
      .warning-box { padding: 5px 7px; background: #fff; border: 1px solid #FDE68A; border-radius: 5px; }
      .warning-label { font-size: 7.5px; color: #92400E; font-weight: 700; text-transform: uppercase; }
      .warning-value { margin-top: 1px; font-size: 15px; line-height: 1; font-weight: 700; color: #78350F; }
      .pipeline-flow { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 2px; margin-top: 1px; }
      .pipeline-step { position: relative; min-width: 0; min-height: 100px; padding: 9px 7px 8px; background: #F2F7FD; border: 1px solid #BFD7F3; text-align: center; clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 50%, calc(100% - 10px) 100%, 0 100%, 10px 50%); }
      .pipeline-step:first-child { clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 50%, calc(100% - 10px) 100%, 0 100%); }
      .pipeline-step:last-child { clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%, 10px 50%); }
      .pipeline-step.active { background: #E8F2FE; border-color: #93C5FD; }
      .pipeline-step.final { background: #F0FDF4; border-color: #86EFAC; }
      .pipeline-number { width: 22px; height: 22px; margin: 0 auto 6px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: #2563EB; color: #fff; font-size: 9px; font-weight: 700; }
      .pipeline-step.final .pipeline-number { background: #16A34A; }
      .pipeline-name { min-height: 25px; font-size: 8px; line-height: 1.2; font-weight: 600; color: #334155; }
      .pipeline-count { margin-top: 5px; font-size: 15px; line-height: 1; font-weight: 700; color: #0F172A; }
      .pipeline-count-label { margin-top: 2px; font-size: 7.5px; color: #94A3B8; }
      .pipeline-progress { margin-top: 6px; height: 4px; background: #DCE5EF; border-radius: 8px; overflow: hidden; }
      .pipeline-progress span { display: block; height: 100%; background: #2681D8; border-radius: 8px; }
      .pipeline-step.final .pipeline-progress span { background: #16A34A; }
      @media(max-width:1100px) {
        .page-shell { padding-top: 16px; }
        .page-hero-side { display: none; }
        .exec-kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .exec-grid { grid-template-columns: 1fr 1fr; grid-template-areas: "overview overview" "status pic" "pipeline pipeline" "rfs rfs" "top5 warning"; }
      }
      @media(max-width:700px) {
        .page-hero { min-height: auto; }
        .page-hero-title { font-size: 18px; }
        .exec-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .pipeline-flow { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .exec-grid { grid-template-columns: 1fr 1fr; grid-template-areas: "overview overview" "status pic" "pipeline pipeline" "rfs rfs" "top5 warning"; }
      }
      .exec-grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); grid-template-areas: "overview overview overview overview overview overview status status status pic pic pic" "pipeline pipeline pipeline pipeline pipeline pipeline rfs rfs rfs rfs rfs rfs" "top5 top5 top5 top5 top5 top5 top5 top5 top5 warning warning warning"; gap: 12px; align-items: start; }
    </style>
  `;

  const sortedProjects = [...projects].sort((a, b) => new Date(a.targetRfs || '2099-12-31') - new Date(b.targetRfs || '2099-12-31'));
  let overviewRows = '';
  
  sortedProjects.forEach((p, idx) => {
    const sph = projectSph(p);
    const progress = Math.max(0, Math.min(100, Number(p.progressPct) || 0));
    const rfs = p.targetRfs ? new Date(p.targetRfs).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
    overviewRows += `<tr><td>${idx + 1}</td><td><div class="exec-project-name" title="${escAttr(p.name)}">${escAttr(p.name)}</div><div class="exec-project-pic">${escAttr(p.requestorDept || '—')}</div></td><td class="mono">${valToM(sph.awal)} M</td><td>${escAttr(p.leadId || '—')}</td><td style="white-space:nowrap">${rfs}</td><td>${badgeStatus(getDynamicStatus(p))}</td><td><div class="exec-progress"><span class="exec-progress-value">${progress}%</span><div class="exec-progress-bg"><div class="exec-progress-fill" style="width:${progress}%"></div></div></div></td></tr>`;
  });

  if (!overviewRows) overviewRows = `<tr><td colspan="7" style="text-align:center; padding:25px; color:#94A3B8;">Belum ada project.</td></tr>`;

  const warningProjects = sortedProjects.filter(p => ['Overdue', 'At Risk'].includes(getDynamicStatus(p)));
  let warningRows = '';

  warningProjects.slice(0, 5).forEach(p => {
    const progress = Number(p.progressPct) || 0;
    const rfs = p.targetRfs ? new Date(p.targetRfs).toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }) : '—';
    warningRows += `<tr><td><div class="exec-project-name">${escAttr(p.name)}</div><div class="exec-project-pic">PIC: ${escAttr(p.leadId || '—')}</div></td><td style="white-space:nowrap">${rfs}</td><td><strong>${progress}%</strong></td><td>${badgeStatus(getDynamicStatus(p))}</td></tr>`;
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
    pipelineHtml += `<div class="pipeline-step ${activeClass} ${finalClass}"><div class="pipeline-number">${n}</div><div class="pipeline-name">${name}</div><div class="pipeline-count">${count}</div><div class="pipeline-count-label">${count === 1 ? 'Project' : 'Projects'}</div><div class="pipeline-progress"><span style="width:${pct}%"></span></div></div>`;
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
      <div class="exec-panel overview"><div class="exec-panel-head">▣<span>Project Presourcing Overview</span><span class="exec-panel-sub">${totalProj} Projects</span></div><div class="exec-table-wrap"><table class="exec-table"><thead><tr><th>No</th><th>Project Name</th><th>Value</th><th>PIC</th><th>Target RFS</th><th>Status</th><th>Progress</th></tr></thead><tbody>${overviewRows}</tbody></table></div></div>
      <div class="exec-panel status"><div class="exec-panel-head">◉<span>Project Status</span></div><div class="exec-panel-body"><div class="exec-donut"><canvas id="chartStatus"></canvas><div class="exec-donut-center"><div class="exec-donut-number">${totalProj}</div><div class="exec-donut-label">Projects</div></div></div></div></div>
      <div class="exec-panel pic"><div class="exec-panel-head">▥<span>Project Value by Project Lead</span></div><div class="exec-panel-body"><div class="exec-chart"><canvas id="chartPicValue"></canvas></div></div></div>
      <div class="exec-panel pipeline"><div class="exec-panel-head">⇢<span>Presourcing Progress Pipeline</span><span class="exec-panel-sub">${activeProjects} active</span></div><div class="exec-panel-body"><div class="pipeline-flow">${pipelineHtml}</div></div></div>
      <div class="exec-panel rfs"><div class="exec-panel-head">▥<span>Target RFS by Month</span></div><div class="exec-panel-body"><div class="exec-chart"><canvas id="chartRfsMonth"></canvas></div></div></div>
      <div class="exec-panel top5"><div class="exec-panel-head">≡<span>Top 5 Project Value</span></div><div class="exec-panel-body"><div class="exec-chart"><canvas id="chartTop5"></canvas></div></div></div>
      <div class="exec-panel warning"><div class="exec-panel-head"><span>!</span><span>Early Warning</span><span class="exec-panel-sub">Need Attention</span></div><div class="warning-summary"><div class="warning-box"><div class="warning-label">Overdue</div><div class="warning-value">${overdue}</div></div><div class="warning-box"><div class="warning-label">At Risk</div><div class="warning-value">${atRisk}</div></div></div><div class="exec-table-wrap"><table class="exec-table"><thead><tr><th>Project</th><th>RFS</th><th>Progress</th><th>Status</th></tr></thead><tbody>${warningRows}</tbody></table></div></div>
    </div>
  `;
}

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

function renderTeam() {
  const workload = computeTeamWorkload();
  const rows = workload.members;
  if (!selectedTeamMember || !rows.some(row => row.key === selectedTeamMember)) {
    selectedTeamMember = rows[0]?.key || null;
  }
  const selected = rows.find(row => row.key === selectedTeamMember) || null;
  const maxLoad = Math.max(1, ...rows.map(row => row.uniqueActive));

  const portfolioProjectRow = (project, role, itemLines = []) => {
    const status = badgeStatus(getDynamicStatus(project));
    const items = itemLines.length
      ? `<div style="margin-top:5px;color:#64748B;font-size:11px;">${itemLines.map(item => `<div>• ${escAttr(item.itemNo ? `${item.itemNo} — ` : '')}${escAttr(item.product)}${item.qty != null ? ` (${escAttr(item.qty)} ${escAttr(item.uom)})` : ''}</div>`).join('')}</div>`
      : '';
    return `<tr><td><button class="mini-btn" data-team-open-project="${escAttr(project.id)}" type="button" style="text-align:left;white-space:normal;">${escAttr(project.name || 'Unnamed Project')}</button>${items}</td><td>${role}</td><td>${escAttr(project.pipelineStage || '—')}</td><td>${Number(project.progressPct || 0)}%</td><td>${status}</td></tr>`;
  };

  const memberRows = rows.length ? rows.map(row => {
    const leadWidth = (row.leadOnlyActive / maxLoad) * 100;
    const bothWidth = (row.bothActive / maxLoad) * 100;
    const involvedWidth = (row.involvedOnlyActive / maxLoad) * 100;
    const activeBar = `<div title="Lead only: ${row.leadOnlyActive}; Lead & PIC: ${row.bothActive}; PIC only: ${row.involvedOnlyActive}" style="display:flex;height:9px;min-width:80px;background:#E2E8F0;border-radius:6px;overflow:hidden;"><span style="width:${leadWidth}%;background:#2563EB;"></span><span style="width:${bothWidth}%;background:#7C3AED;"></span><span style="width:${involvedWidth}%;background:#0D9488;"></span></div>`;
    return `<tr data-team-member="${escAttr(row.key)}" tabindex="0" style="cursor:pointer;${selected && selected.key === row.key ? 'background:#EFF6FF;' : ''}">
      <td><strong>${escAttr(row.name)}</strong>${row.inTeam ? '' : '<div style="font-size:10px;color:#B45309;">Assignment not in Team list</div>'}</td>
      <td class="num mono">${row.leadActive}</td>
      <td class="num mono">${row.involvedActive}</td>
      <td class="num mono"><strong>${row.uniqueActive}</strong></td>
      <td class="num mono">${row.itemAssignments}</td>
      <td class="num mono">${fmtPct(row.winRate)}</td>
      <td style="min-width:110px;">${activeBar}</td>
    </tr>`;
  }).join('') : '<tr><td colspan="7"><div class="empty">Belum ada anggota atau assignment tim.</div></td></tr>';

  let portfolioHtml = '<div class="empty">Pilih anggota tim untuk melihat portofolionya.</div>';
  if (selected) {
    const leadRows = selected.leadProjectList.length
      ? selected.leadProjectList.map(project => portfolioProjectRow(project, '<span style="color:#1D4ED8;font-weight:700;">Project Lead</span>')).join('')
      : '<tr><td colspan="5" class="empty">Belum memimpin project.</td></tr>';
    const involvedRows = selected.involvedProjectList.length
      ? selected.involvedProjectList.map(entry => portfolioProjectRow(entry.project, '<span style="color:#0F766E;font-weight:700;">Project Involvement</span>', entry.items)).join('')
      : '<tr><td colspan="5" class="empty">Belum terlibat sebagai PIC item.</td></tr>';
    portfolioHtml = `
      <div class="team-portfolio-kpis">
        <div><span>Project dipimpin</span><strong>${selected.leadCount}</strong><small>${selected.leadActive} aktif</small></div>
        <div><span>Project involvement</span><strong>${selected.involvedCount}</strong><small>${selected.involvedActive} aktif</small></div>
        <div><span>Active workload unik</span><strong>${selected.uniqueActive}</strong><small>${selected.bothActive} project dengan dua peran</small></div>
        <div><span>Item assignment</span><strong>${selected.itemAssignments}</strong><small>${selected.completedCount} project selesai diikuti</small></div>
      </div>
      <div class="team-portfolio-section"><h3>Project yang dipimpin (${selected.leadProjectList.length})</h3><div class="team-table-scroll"><table><thead><tr><th>Project</th><th>Peran</th><th>Pipeline</th><th>Progress</th><th>Status</th></tr></thead><tbody>${leadRows}</tbody></table></div></div>
      <div class="team-portfolio-section"><h3>Project yang melibatkan anggota ini (${selected.involvedProjectList.length})</h3><div class="team-table-scroll"><table><thead><tr><th>Project &amp; Item PIC</th><th>Peran</th><th>Pipeline</th><th>Progress</th><th>Status</th></tr></thead><tbody>${involvedRows}</tbody></table></div></div>
    `;
  }

  return `
    <style>
      .team-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px}
      .team-kpi{background:#fff;border:1px solid #DCE4EE;border-radius:8px;padding:13px 15px;min-width:0}
      .team-kpi span{display:block;color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.03em}
      .team-kpi strong{display:block;margin-top:5px;font-size:24px;color:#0F172A;line-height:1.1}
      .team-kpi small{display:block;margin-top:4px;color:#94A3B8;font-size:10px}
      .team-legend{display:flex;gap:14px;flex-wrap:wrap;padding:10px 14px;color:#64748B;font-size:11px}
      .team-legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}
      .team-portfolio{margin-top:12px;border:1px solid #DCE4EE;border-radius:8px;background:#fff;overflow:hidden}
      .team-portfolio-head{padding:13px 16px;background:#F8FAFC;border-bottom:1px solid #E2E8F0;display:flex;justify-content:space-between;align-items:center;gap:10px}
      .team-portfolio-head h2{font-size:14px;margin:0;color:#0F172A}
      .team-portfolio-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding:12px 14px}
      .team-portfolio-kpis>div{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px;padding:10px}
      .team-portfolio-kpis span,.team-portfolio-kpis small{display:block;font-size:10px;color:#64748B}
      .team-portfolio-kpis strong{display:block;font-size:20px;color:#0F172A;margin:4px 0}
      .team-portfolio-section{padding:5px 14px 14px}
      .team-portfolio-section h3{font-size:12px;color:#334155;margin:9px 0}
      .team-table-scroll{overflow-x:auto}
      .team-table-scroll table{width:100%;border-collapse:collapse}
      .team-table-scroll th,.team-table-scroll td{padding:9px 10px;border-bottom:1px solid #EEF2F6;text-align:left;font-size:11px;vertical-align:top}
      .team-table-scroll th{background:#F8FAFC;color:#64748B;font-size:10px;text-transform:uppercase}
      @media(max-width:850px){.team-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.team-portfolio-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:560px){.team-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.team-portfolio-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
    </style>
    <div class="team-kpis">
      <div class="team-kpi"><span>Anggota tim terdeteksi</span><strong>${workload.totalMembers}</strong><small>Termasuk assignment yang belum terdaftar</small></div>
      <div class="team-kpi"><span>Active projects</span><strong>${workload.activeProjects}</strong><small>Status project ongoing</small></div>
      <div class="team-kpi"><span>Lead assignments</span><strong>${workload.leadAssignments}</strong><small>Project aktif yang dipimpin</small></div>
      <div class="team-kpi"><span>Involvement assignments</span><strong>${workload.involvementAssignments}</strong><small>Project aktif dengan PIC item</small></div>
    </div>
    <div class="panel">
      <div class="panel-hd"><h2>Team Workload &amp; Project Responsibility</h2><button class="btn-ghost" id="btn-manage-team">Kelola anggota tim</button></div>
      <div class="team-legend"><span><i style="background:#2563EB"></i>Lead only</span><span><i style="background:#7C3AED"></i>Lead + PIC</span><span><i style="background:#0D9488"></i>PIC only</span><span>Angka total menghitung project unik, bukan penjumlahan role.</span></div>
      <div class="panel-body"><div class="team-table-scroll"><table><thead><tr><th>Anggota</th><th class="num">Lead aktif</th><th class="num">Involved aktif</th><th class="num">Active total unik</th><th class="num">Item PIC</th><th class="num">Win rate selesai</th><th>Distribusi workload</th></tr></thead><tbody>${memberRows}</tbody></table></div></div>
    </div>
    <div class="team-portfolio">
      <div class="team-portfolio-head"><h2>${selected ? `Portofolio: ${escAttr(selected.name)}` : 'Portofolio Anggota'}</h2><span style="font-size:10px;color:#64748B;">Klik baris anggota untuk melihat detail</span></div>
      ${portfolioHtml}
    </div>
    ${workload.unassignedActive ? `<div style="margin-top:10px;padding:10px 13px;border:1px solid #FDE68A;background:#FFFBEB;color:#92400E;border-radius:7px;font-size:11px;">${workload.unassignedActive} active project belum memiliki Lead maupun PIC item. Assignment perlu dilengkapi.</div>` : ''}
  `;
}

// ============================================================================
// MODAL & FORM RENDERER (PROJECT FORM)
// ============================================================================
function projectModalHtml(p, isNew) {
  const sowsHtml = (p.sows || []).map((sow, si) => {
    const boqsHtml = (sow.boqs || []).map((boq, bi) => {
      const itemsHtml = (boq.items || []).map((it, ii) => itemBlockHtml(it, si, bi, ii)).join('');
      return `
        <div class="boq-block">
          <div class="boq-head">
            <div class="boq-heading">
              <div class="boq-number">B${bi + 1}</div>
              <input class="boq-name" data-si="${si}" data-bi="${bi}" value="${escAttr(boq.name)}" placeholder="Nama BoQ" style="max-width:200px;">
            </div>
            <button class="mini-btn danger form-danger-btn" data-del-boq="${si}:${bi}" type="button">Hapus BoQ</button>
          </div>
          ${itemsHtml}
          <div class="add-row">
            <button class="mini-btn form-add-btn" data-add-item="${si}:${bi}" type="button">+ Tambah Item</button>
          </div>
        </div>
      `;
    }).join('');

    return `
      <div class="sow-block">
        <div class="sow-head">
          <div class="sow-heading">
            <div class="sow-index">S${si + 1}</div>
            <input class="sow-name" data-si="${si}" value="${escAttr(sow.name)}" placeholder="Nama Scope of Work (SoW)" style="max-width:240px;">
          </div>
          <div class="sow-actions">
            <button class="mini-btn form-add-btn" data-add-boq="${si}" type="button">+ BoQ</button>
            <button class="mini-btn danger form-danger-btn" data-del-sow="${si}" type="button">Hapus SoW</button>
          </div>
        </div>
        ${boqsHtml}
      </div>
    `;
  }).join('');

  return `
    <div class="overlay" id="ov">
      <div class="modal project-modal">
        <div class="modal-hd">
          <h3>${isNew ? 'Buat Project Baru' : 'Edit Project'}</h3>
          <button class="mini-btn" id="m-close" type="button">Tutup</button>
        </div>
        <div class="modal-body">
          <div class="form-section">
            <div class="form-section-head"><div class="form-section-title">Informasi Utama</div></div>
            <div class="field project-name-field">
              <label class="required-mark">Nama Project</label>
              <input id="m-name" value="${escAttr(p.name)}" placeholder="Contoh: Project Backbone Expansion">
            </div>
            <div class="grid3">
              <div class="field"><label class="required-mark">Pemohon</label><input id="m-req-name" value="${escAttr(p.requestorName)}" placeholder="Nama pemohon"></div>
              <div class="field"><label class="required-mark">Departemen</label><input id="m-req-dept" value="${escAttr(p.requestorDept)}" placeholder="Divisi/Dept"></div>
              <div class="field"><label>Lead Presource</label><select id="m-lead">${team.map(t => `<option value="${escAttr(t)}" ${p.leadId === t ? 'selected' : ''}>${escAttr(t)}</option>`).join('')}</select></div>
            </div>
          </div>

          <div class="form-section">
            <div class="form-section-head"><div class="form-section-title">Status &amp; Timeline EWS</div></div>
            <div class="grid3">
              <div class="field">
                <label>Prioritas</label>
                <select id="m-priority">
                  <option value="Urgent" ${p.priority === 'Urgent' ? 'selected' : ''}>Urgent</option>
                  <option value="High" ${p.priority === 'High' ? 'selected' : ''}>High</option>
                  <option value="Medium" ${p.priority === 'Medium' ? 'selected' : ''}>Medium</option>
                </select>
              </div>
              <div class="field">
                <label>Status</label>
                <select id="m-status">
                  <option value="ongoing" ${p.status === 'ongoing' ? 'selected' : ''}>Berjalan</option>
                  <option value="win" ${p.status === 'win' ? 'selected' : ''}>Menang</option>
                  <option value="lose" ${p.status === 'lose' ? 'selected' : ''}>Kalah</option>
                </select>
              </div>
              <div class="field"><label>Target RFS</label><input type="date" id="m-target-rfs" value="${escAttr(p.targetRfs)}"></div>
            </div>
            <div class="grid2" style="margin-top:10px;">
              <div class="field">
                <label>Tahap Pipeline</label>
                <select id="m-pipeline-stage">
                  <option value="1 - Project Identification" ${p.pipelineStage === '1 - Project Identification' ? 'selected' : ''}>1 - Project Identification</option>
                  <option value="2 - SPH Preparation" ${p.pipelineStage === '2 - SPH Preparation' ? 'selected' : ''}>2 - SPH Preparation</option>
                  <option value="3 - Vendor Selection" ${p.pipelineStage === '3 - Vendor Selection' ? 'selected' : ''}>3 - Vendor Selection</option>
                  <option value="4 - Negotiation" ${p.pipelineStage === '4 - Negotiation' ? 'selected' : ''}>4 - Negotiation</option>
                  <option value="5 - Finalization" ${p.pipelineStage === '5 - Finalization' ? 'selected' : ''}>5 - Finalization</option>
                  <option value="6 - RFS" ${p.pipelineStage === '6 - RFS' ? 'selected' : ''}>6 - RFS</option>
                </select>
              </div>
              <div class="field"><label>Progress (%)</label><input type="number" id="m-progress" min="0" max="100" value="${p.progressPct ?? 0}"></div>
            </div>
          </div>

          <div class="form-section">
            <div class="form-section-head">
              <div class="form-section-title">Scope of Work &amp; BoQ</div>
              <button class="mini-btn form-add-btn" id="m-add-sow" type="button" style="display: ${p.sphMode === 'item' ? 'inline-block' : 'none'};">+ Tambah SoW</button>
            </div>
            <div class="field">
              <label>Mode SPH</label>
              <select id="m-sphmode">
                <option value="item" ${p.sphMode === 'item' ? 'selected' : ''}>Dari Item BoQ (Rinci)</option>
                <option value="project" ${p.sphMode === 'project' ? 'selected' : ''}>Manual Total Project</option>
              </select>
            </div>
            
            <div id="m-sph-project-container" style="display: ${p.sphMode === 'project' ? 'block' : 'none'};">
              <div class="sph-summary-box">
                <div class="field"><label>Total SPH Awal (Project)</label><input type="number" id="m-proj-awal" value="${p.projectSphAwal ?? ''}"></div>
                <div class="field"><label>Total SPH Final (Project)</label><input type="number" id="m-proj-final" value="${p.projectSphFinal ?? ''}"></div>
              </div>
            </div>

            <div id="m-sph-item-container" style="display: ${p.sphMode === 'item' ? 'block' : 'none'};">
              ${sowsHtml}
            </div>
          </div>
        </div>
        <div class="modal-ft">
          <button class="btn-ghost" id="m-cancel" type="button">Batal</button>
          <button class="btn-primary" id="m-save" type="button">Simpan Project</button>
        </div>
      </div>
    </div>
  `;
}

function teamModalHtml(d) {
  const rows = (d.members || []).map(member => `
    <div class="team-member-edit-row" style="display:flex;gap:7px;align-items:center;margin-bottom:8px;">
      <input class="team-member-name" data-team-old="${escAttr(member.oldName)}" value="${escAttr(member.name)}" style="flex:1;min-width:0;">
      <button class="mini-btn danger" type="button" data-team-remove>Hapus</button>
    </div>
  `).join('');
  return `
    <div class="overlay" id="ov">
      <div class="modal" style="max-width:520px;">
        <div class="modal-hd"><h3>Kelola Anggota Tim</h3><button class="mini-btn" id="m-close" type="button">Tutup</button></div>
        <div class="modal-body">
          <div class="note" style="margin-bottom:12px;">Mengganti nama anggota akan memperbarui Lead dan seluruh PIC item yang terkait. Anggota yang masih memiliki assignment tidak dapat dihapus.</div>
          <div id="team-member-edit-list">${rows}</div>
          <div style="display:flex;gap:7px;margin-top:12px;">
            <input id="m-team-new-member" placeholder="Nama anggota baru" style="flex:1;min-width:0;">
            <button class="btn-ghost" id="m-team-add" type="button">+ Tambah</button>
          </div>
        </div>
        <div class="modal-ft"><button class="btn-ghost" id="m-cancel" type="button">Batal</button><button class="btn-primary" id="m-save-team" type="button">Simpan Tim</button></div>
      </div>
    </div>
  `;
}

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
    tbodyHtml = '<tr><td colspan="8"><div class="empty">Tidak ada project yang cocok.</div></td></tr>';
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
          <td class="num mono">${fmtIdr(s.final)}</td>
          <td class="num mono">${fmtPct(eff)}</td>
          <td class="num mono">${durationDays(p)} hari</td>
        </tr>
      `;
      if (openProjectId === p.id) tbodyHtml += `<tr><td colspan="8">${renderProjectDetail(p)}</td></tr>`;
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
          <thead><tr><th>Project</th><th>Pemohon</th><th>Status EWS</th><th>Tahap Pipeline</th><th class="num">SPH Awal</th><th class="num">SPH Final</th><th class="num">Efficiency</th><th class="num">Durasi</th></tr></thead>
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
        // Tampilkan kalkulasi item parsial di Detail View
        let finalItemValue = null;
        let eff = null;
        
        if (p.sphMode === 'item') {
          if (it.sphAwal != null) {
            finalItemValue = it.sphFinal != null ? it.sphFinal : it.sphAwal; // Efisiensi parsial
            eff = efficiencyPct(it.sphAwal, finalItemValue);
          }
        }
        
        const notesHtml = it.notes ? `<div style="font-size:11px; color:var(--text-muted); margin-top:3px;">📝 ${escAttr(it.notes)}</div>` : '';
        const picsHtml = (it.picIds || []).map(x => `<span class="pic-chip">${escAttr(x)}</span>`).join('');
        
        sowsHtml += `
          <div style="display:grid; grid-template-columns: 2fr 0.4fr 0.5fr 1fr 1fr 1fr 0.8fr 1.5fr; gap:8px; padding:7px 0; font-size:12.5px; border-bottom:1px solid var(--border-soft); align-items:start;">
            <div><div style="font-weight:500;">${escAttr(it.product) || '—'}</div>${notesHtml}</div>
            <div style="color:var(--text-muted);">${it.qty || '-'}</div>
            <div style="color:var(--text-muted);">${escAttr(it.uom) || '-'}</div>
            <div style="color:var(--text-muted);">${escAttr(it.vendor) || '-'}</div>
            <div class="num mono">${p.sphMode === 'item' ? fmtIdr(it.sphAwal) : '—'}</div>
            <div class="num mono">${p.sphMode === 'item' ? fmtIdr(finalItemValue) : '—'}</div>
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
        confirmExistingProjectDeletion(el.dataset.deleteProject);
        projects = projects.filter(p => p.id !== el.dataset.deleteProject); 
        await saveAll({ allowEmptyProjects: projects.length === 0 });
        render(); 
      } 
    };
  });
  
  document.querySelectorAll('[data-team-member]').forEach(el => {
    const selectMember = () => { selectedTeamMember = el.dataset.teamMember; render(); };
    el.onclick = selectMember;
    el.onkeydown = (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectMember(); } };
  });
  document.querySelectorAll('[data-team-open-project]').forEach(el => {
    el.onclick = () => {
      const projectId = el.dataset.teamOpenProject;
      if (!projects.some(project => String(project.id) === String(projectId))) return;
      activeTab = 'projects';
      openProjectId = projectId;
      render();
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
  fileInput.accept = '.xlsx';
  fileInput.style.display = 'none';
  document.body.appendChild(fileInput);

  fileInput.onchange = async () => {
    const file = fileInput.files[0];
    document.body.removeChild(fileInput);
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      alert('File revisi harus berformat .xlsx. Download ulang template dari project.');
      return;
    }

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

  const deletionNotice = removed.length ? `
    <div style="margin-bottom:12px; padding:10px 12px; border:1px solid #FCA5A5; border-radius:6px; background:#FEF2F2; color:#991B1B; font-size:9.5px;">
      <strong>Perhatian: ${removed.length} item existing akan dihapus.</strong>
      <div style="margin-top:3px;">Penghapusan hanya akan dilakukan setelah dikonfirmasi secara eksplisit.</div>
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
        ${deletionNotice}
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
          ${canApply ? (removed.length ? `Confirm & Apply (${removed.length} deletions)` : 'Confirm & Apply Revision') : 'Perbaiki Error Terlebih Dahulu'}
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);
  window.pendingRevisionFile = file;
  window.pendingRevisionRemovedCount = removed.length;
  window.pendingRevisionSnapshotToken = data.snapshot_token || '';
  window.pendingRevisionWorkbookToken = data.workbook_token || '';
}

function closeRevisionPreview() {
  const modal = document.getElementById('revision-preview-modal');
  if (modal) modal.remove();
  window.pendingRevisionFile = null;
  window.pendingRevisionRemovedCount = 0;
  window.pendingRevisionSnapshotToken = '';
  window.pendingRevisionWorkbookToken = '';
}

async function confirmRevisionBoq(projectId) {
  const file = window.pendingRevisionFile;
  if (!file) { alert('File revision tidak ditemukan.'); return; }

  const removedCount = Number(window.pendingRevisionRemovedCount || 0);
  let confirmDeletions = false;
  if (removedCount > 0) {
    confirmDeletions = window.confirm(
      `Revisi ini akan menghapus ${removedCount} item existing dari project.\n\n` +
      'Pastikan daftar Removed pada preview sudah benar. Lanjutkan penghapusan?'
    );
    if (!confirmDeletions) return;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('ticket_id', projectId);
  formData.append('confirm_deletions', confirmDeletions ? '1' : '0');
  formData.append('snapshot_token', window.pendingRevisionSnapshotToken || '');
  formData.append('workbook_token', window.pendingRevisionWorkbookToken || '');

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
    if (btn) {
      btn.disabled = false;
      btn.innerText = removedCount > 0 ? `Confirm & Apply (${removedCount} deletions)` : 'Confirm & Apply Revision';
    }
  }
}

// ============================================================================
// MODALS LOGIC & FORM RENDERER
// ============================================================================
function blankProject() {
  return {
    id: uid('proj'), name: '', requestorName: '', requestorDept: '', priority: 'Medium', status: 'ongoing', leadId: team[0] || '', sphMode: 'item', projectSphAwal: null, projectSphFinal: null,
    createdAt: todayStr(), closedAt: null, targetRfs: '', pipelineStage: '1 - Project Identification', progressPct: 0, comparison_docs: [],
    sows: [{ id: uid('sow'), name: '', boqs: [{ id: uid('boq'), name: '', items: [{ id: uid('item'), product: '', qty: 1, vendor: '', notes: '', picIds: [], sphAwalUnit: null, sphFinalUnit: null, sphAwal: null, sphFinal: null }] }] }]
  };
}

function openProjectModal(id) {
  const existing = id ? JSON.parse(JSON.stringify(projects.find(p => p.id === id))) : blankProject();
  modal = { type: 'project', data: existing, isNew: !id };
  render();
}

function openTeamModal() {
  modal = { type: 'team', data: { members: collectKnownTeamNames().map(name => ({ oldName: name, name })) } };
  render();
}

function renderModal() {
  let root = document.getElementById('modal-root');
  if (!root) { root = document.createElement('div'); root.id = 'modal-root'; document.body.appendChild(root); }
  
  if (modal.type === 'project') root.innerHTML = projectModalHtml(modal.data, modal.isNew);
  if (modal.type === 'team') root.innerHTML = teamModalHtml(modal.data);
  
  wireModalEvents();
}

function itemBlockHtml(it, si, bi, ii) {
  const path = `${si}:${bi}:${ii}`;
  const awalTotal = calculateUiSphTotal(it.qty, it.sphAwalUnit) ?? it.sphAwal;
  const finalTotal = calculateUiSphTotal(it.qty, it.sphFinalUnit) ?? it.sphFinal;

  let initEff = '';
  let initEffColor = '#2563EB';
  if (awalTotal > 0 && finalTotal != null) {
    const e = ((awalTotal - finalTotal) / awalTotal) * 100;
    initEff = `Eff: ${e.toFixed(1)}%`;
    initEffColor = e >= 0 ? '#16A34A' : '#DC2626';
  }

  // UPDATE LOGIKA 2: Penambahan baris "Catatan" (it-notes)
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
      <div class="field" style="margin-bottom: 10px;">
        <label>Catatan</label>
        <input class="it-notes" data-path="${path}" value="${escAttr(it.notes)}" placeholder="Tambahkan catatan spesifikasi atau info tambahan (opsional)">
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
          <div style="margin-top:4px; font-size:9.5px; color:#64748B; display:flex; justify-content:space-between;">
            <span>Total: <strong data-total-final="${path}" style="color:#0F172A;">${fmtIdr(finalTotal)}</strong></span>
            <span data-eff-preview="${path}" style="font-weight:700; color:${initEffColor};">${initEff}</span>
          </div>
        </div>
        <div class="field">
          <label>PIC</label>
          <div class="pic-select">
            ${team.map(t => `<div class="pic-opt ${(it.picIds || []).includes(t) ? 'on' : ''}" data-pic="${path}:${escAttr(t)}">${escAttr(t)}</div>`).join('')}
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
  const effPreview = document.querySelector('[data-eff-preview="' + path + '"]');

  const totalAwal = calculateUiSphTotal(qtyInput?.value, awalInput?.value);
  const totalFinal = calculateUiSphTotal(qtyInput?.value, finalInput?.value);

  if (awalTotal) awalTotal.textContent = totalAwal == null ? '—' : fmtIdr(totalAwal);
  if (finalTotal) finalTotal.textContent = totalFinal == null ? '—' : fmtIdr(totalFinal);

  if (effPreview) {
    if (totalAwal > 0 && totalFinal != null) {
      const eff = ((totalAwal - totalFinal) / totalAwal) * 100;
      effPreview.textContent = `Eff: ${eff.toFixed(1)}%`;
      effPreview.style.color = eff >= 0 ? '#16A34A' : '#DC2626';
    } else {
      effPreview.textContent = '';
    }
  }
}

function syncModalData() {
  if (!modal || modal.type !== 'project') return;
  
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
  syncPathField('.it-notes', (item, value) => { item.notes = value; }); // Sinkronisasi nilai catatan ke data

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
    const list = document.getElementById('team-member-edit-list');
    document.querySelectorAll('[data-team-remove]').forEach(button => {
      button.onclick = () => button.closest('.team-member-edit-row')?.remove();
    });
    const addButton = document.getElementById('m-team-add');
    if (addButton) addButton.onclick = () => {
      const name = val('m-team-new-member').trim();
      if (!name) return alert('Nama anggota wajib diisi.');
      const existing = [...document.querySelectorAll('.team-member-name')].map(input => normalizeTeamKey(input.value));
      if (existing.includes(normalizeTeamKey(name))) return alert('Nama anggota sudah ada.');
      list.insertAdjacentHTML('beforeend', `<div class="team-member-edit-row" style="display:flex;gap:7px;align-items:center;margin-bottom:8px;"><input class="team-member-name" data-team-old="" value="${escAttr(name)}" style="flex:1;min-width:0;"><button class="mini-btn danger" type="button" data-team-remove>Hapus</button></div>`);
      list.querySelector('.team-member-edit-row:last-child [data-team-remove]').onclick = (event) => event.currentTarget.closest('.team-member-edit-row')?.remove();
      document.getElementById('m-team-new-member').value = '';
    };
    const saveButton = document.getElementById('m-save-team');
    if (saveButton) saveButton.onclick = async () => {
      const inputs = [...document.querySelectorAll('.team-member-name')];
      const rows = inputs.map(input => ({ oldName: String(input.dataset.teamOld || '').trim(), name: String(input.value || '').trim() }));
      let nextState;
      try {
        nextState = buildTeamMemberUpdate(rows);
      } catch (error) {
        return alert(error.message || 'Perubahan anggota tim tidak valid.');
      }
      team = nextState.team;
      projects = nextState.projects;
      modal = null;
      render();
      await saveAll();
    };
    return;
  }
  
  const sphmode = document.getElementById('m-sphmode');
  if (sphmode) {
    sphmode.onchange = () => { 
      syncModalData(); 
      modal.data.sphMode = sphmode.value; 
      
      const projContainer = document.getElementById('m-sph-project-container');
      const itemContainer = document.getElementById('m-sph-item-container');
      const btnAddSow = document.getElementById('m-add-sow');

      if (projContainer) projContainer.style.display = sphmode.value === 'project' ? 'block' : 'none';
      if (itemContainer) itemContainer.style.display = sphmode.value === 'item' ? 'block' : 'none';
      if (btnAddSow) btnAddSow.style.display = sphmode.value === 'item' ? 'inline-block' : 'none';
    };
  }

  document.querySelectorAll('.it-qty, .it-awal-unit, .it-final-unit').forEach(el => {
    el.addEventListener('input', () => updateItemFinancialPreview(el));
  });

  const btnAddSow = document.getElementById('m-add-sow');
  if (btnAddSow) {
    btnAddSow.onclick = (e) => { 
      e.preventDefault(); 
      syncModalData(); 
      modal.data.sows.push({id:uid('sow'), name:'', boqs:[{id:uid('boq'), name:'', items:[{id:uid('item'), product:'', qty:1, vendor:'', notes:'', picIds:[], sphAwalUnit:null, sphFinalUnit:null, sphAwal:null, sphFinal:null}]}]}); 
      render(); 
    };
  }

  document.querySelectorAll('[data-add-boq]').forEach(el => {
    el.onclick = (e) => { 
      e.preventDefault(); 
      syncModalData(); 
      modal.data.sows[+el.dataset.addBoq].boqs.push({id:uid('boq'), name:'', items:[{id:uid('item'), product:'', qty:1, vendor:'', notes:'', picIds:[], sphAwalUnit:null, sphFinalUnit:null, sphAwal:null, sphFinal:null}]}); 
      render(); 
    };
  });

  document.querySelectorAll('[data-add-item]').forEach(el => { 
    const [si, bi] = el.dataset.addItem.split(':').map(Number); 
    el.onclick = (e) => { 
      e.preventDefault(); 
      syncModalData(); 
      modal.data.sows[si].boqs[bi].items.push({id:uid('item'), product:'', qty:1, vendor:'', notes:'', picIds:[], sphAwalUnit:null, sphFinalUnit:null, sphAwal:null, sphFinal:null}); 
      render(); 
    }; 
  });

  document.querySelectorAll('[data-del-sow]').forEach(el => {
    el.onclick = (e) => {
      e.preventDefault();
      syncModalData();
      modal.data.sows.splice(+el.dataset.delSow, 1);
      render();
    };
  });

  document.querySelectorAll('[data-del-boq]').forEach(el => { 
    const [si, bi] = el.dataset.delBoq.split(':').map(Number); 
    el.onclick = (e) => { 
      e.preventDefault(); 
      syncModalData(); 
      modal.data.sows[si].boqs.splice(bi, 1); 
      render(); 
    }; 
  });

  document.querySelectorAll('[data-del-item]').forEach(el => { 
    const [si, bi, ii] = el.dataset.delItem.split(':').map(Number); 
    el.onclick = (e) => { 
      e.preventDefault(); 
      syncModalData(); 
      modal.data.sows[si].boqs[bi].items.splice(ii, 1); 
      render(); 
    }; 
  });

  document.querySelectorAll('[data-pic]').forEach(el => { 
    const parts = el.dataset.pic.split(':');
    const si = parseInt(parts[0]);
    const bi = parseInt(parts[1]);
    const ii = parseInt(parts[2]);
    const name = parts.slice(3).join(':');

    el.onclick = (e) => { 
      e.preventDefault();
      syncModalData(); 
      
      let arr = modal.data.sows[si].boqs[bi].items[ii].picIds;
      if (!Array.isArray(arr)) {
        arr = [];
        modal.data.sows[si].boqs[bi].items[ii].picIds = arr;
      }

      const idx = arr.indexOf(name); 
      if (idx >= 0) arr.splice(idx, 1); 
      else arr.push(name); 
      
      render(); 
    }; 
  });

  const saveBtn = document.getElementById('m-save');
  if (saveBtn) {
    saveBtn.onclick = (e) => { 
      e.preventDefault();
      syncModalData(); 
      const d = modal.data; 
      const idx = projects.findIndex(p => p.id === d.id); 
      if (idx >= 0) projects[idx] = d; 
      else projects.push(d); 
      
      document.getElementById('modal-root').innerHTML = ''; 
      modal = null; 
      render(); 
      saveAll(); 
    };
  }
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