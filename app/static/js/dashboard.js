(() => {
"use strict";

const $ = (id) => document.getElementById(id);

const I18N_ID = Object.freeze({
  "CONTRACT OPERATIONS":"OPERASIONAL KONTRAK",
  "WORKSPACE":"RUANG KERJA",
  "DATA MANAGEMENT":"MANAJEMEN DATA",
  "Contract Monitoring":"Pemantauan Kontrak",
  "Request Management":"Manajemen Permintaan",
  "KHS Register":"Daftar KHS",
  "LP Circulation":"Sirkulasi LP",
  "Contract Lifecycle":"Siklus Kontrak",
  "Workflow Monitoring":"Pemantauan Alur Kerja",
  "Excel Import / Export":"Impor / Ekspor Excel",
  "Activity & Audit Log":"Aktivitas & Log Audit",
  "Contract Creation Workspace":"Ruang Kerja Pembuatan Kontrak",
  "Manage requests, KHS records, and the complete workflow in one place.":"Kelola permintaan, data KHS, dan seluruh alur kerja dalam satu tempat.",
  "Internal operations":"Operasional internal",
  "Operations":"Operasional",
  "Ready":"Siap",
  "Refresh":"Muat ulang",
  "Refresh overview":"Muat ulang ikhtisar",
  "Contract Monitoring & Tracking":"Pemantauan & Pelacakan Kontrak",
  "CONTRACT OPERATIONS / PORTFOLIO OVERVIEW":"OPERASIONAL KONTRAK / IKHTISAR PORTOFOLIO",
  "One place to move each request from intake to LP sign-off, injection, and renewal.":"Satu tempat untuk memantau setiap permintaan sejak diterima, persetujuan LP, injeksi KHS, hingga perpanjangan kontrak.",
  "LAST UPDATED":"PEMBARUAN TERAKHIR",
  "New Request":"Permintaan Baru",
  "Import Excel":"Impor Excel",
  "Total Requests":"Total Permintaan",
  "Parent requests":"Permintaan induk",
  "Total KHS":"Total KHS",
  "Needs Attention":"Perlu Perhatian",
  "Waiting / exception records":"Data yang menunggu / memiliki pengecualian",
  "Fully Injected":"Fully Injected",
  "of active KHS records":"dari KHS aktif",
  "Not Proceeded":"Tidak Dilanjutkan",
  "Closed without full injection":"Ditutup sebelum injeksi penuh",
  "ACTION REQUIRED":"PERLU TINDAKAN",
  "Priority action queue":"Antrean prioritas tindakan",
  "Records awaiting approval, owner follow-up, or prerequisite review.":"Data yang menunggu persetujuan, tindak lanjut PIC, atau pemeriksaan prasyarat.",
  "View attention queue →":"Lihat antrean perhatian →",
  "REQUEST / KHS":"PERMINTAAN / KHS",
  "VENDOR":"VENDOR",
  "CURRENT STAGE":"TAHAP SAAT INI",
  "WAITING FOR / NEXT ACTION":"MENUNGGU / TINDAKAN BERIKUTNYA",
  "STAGE AGE / UPDATED":"DURASI TAHAP / DIPERBARUI",
  "ACTION":"TINDAKAN",
  "Loading…":"Memuat…",
  "Showing the three highest-priority items. Open the full queue to see every outstanding record.":"Menampilkan tiga item dengan prioritas tertinggi. Buka antrean lengkap untuk melihat seluruh data yang masih tertunda.",
  "LIVE WORKFLOW QUEUE":"ANTREAN ALUR KERJA AKTIF",
  "Approval Pipeline":"Tahapan Persetujuan",
  "Next approver is calculated from the recorded milestone dates, not the optional Waiting For field.":"Pihak yang harus menyetujui berikutnya dihitung dari tanggal milestone yang tercatat, bukan dari kolom Waiting For yang bersifat opsional.",
  "Milestone-derived":"Berdasarkan milestone",
  "Memo Internal":"Memo Internal",
  "Pending management approvals":"Menunggu persetujuan manajemen",
  "in queue":"dalam antrean",
  "Junior Manager":"Manajer Junior",
  "Senior Manager":"Manajer Senior",
  "General Manager":"General Manager",
  "Awaiting Head approval":"Menunggu persetujuan Head",
  "Awaiting SM approval":"Menunggu persetujuan SM",
  "Awaiting GM approval":"Menunggu persetujuan GM",
  "LP Circulation":"Sirkulasi LP",
  "Fixed six-step sign-off route":"Alur persetujuan enam tahap",
  "in normal queue":"dalam antrean normal",
  "Tim Kontrak":"Tim Kontrak",
  "Initial review":"Pemeriksaan awal",
  "Vendor Management":"Vendor Management",
  "Strategic Sourcing":"Strategic Sourcing",
  "Management approval":"Persetujuan manajemen",
  "Director":"Direktur",
  "Final sign-off":"Persetujuan akhir",
  "MI GM prerequisite":"Prasyarat persetujuan MI GM",
  "Legacy stage unverified":"Tahap historis belum terverifikasi",
  "Timeline gaps":"Kesenjangan lini masa",
  "Records requiring reconciliation are kept outside the normal approval lanes.":"Data yang memerlukan rekonsiliasi dipisahkan dari antrean persetujuan normal.",
  "Records requiring reconciliation are kept outside normal approval lanes.":"Data yang memerlukan rekonsiliasi dipisahkan dari antrean persetujuan normal.",
  "POST-INJECTION MONITORING":"PEMANTAUAN SETELAH INJEKSI",
  "Contract Lifecycle Watch":"Pemantauan Siklus Kontrak",
  "Renewal visibility starts once a KHS is fully injected.":"Pemantauan perpanjangan dimulai setelah KHS selesai diinjeksikan.",
  "Open contract lifecycle →":"Buka siklus kontrak →",
  "Renewal preparation":"Persiapan perpanjangan",
  "Renewal watch":"Pemantauan perpanjangan",
  "Action required":"Perlu tindakan",
  "Expired":"Kedaluwarsa",
  "Missing dates":"Tanggal belum lengkap",
  "Past contract end date":"Melewati tanggal akhir kontrak",
  "Fully injected · incomplete period":"Sudah diinjeksi penuh · periode belum lengkap",
  "≤ 6 months · cumulative":"≤ 6 bulan · kumulatif",
  "≤ 3 months · cumulative":"≤ 3 bulan · kumulatif",
  "≤ 1 month · cumulative":"≤ 1 bulan · kumulatif",
  "WORKSPACE / INTAKE":"RUANG KERJA / PENERIMAAN",
  "Create and manage parent requests. One request may contain multiple KHS items.":"Buat dan kelola permintaan induk. Satu permintaan dapat berisi beberapa item KHS.",
  "Search requests":"Cari permintaan",
  "Search subject, vendor, owner…":"Cari subjek, vendor, atau PIC…",
  "Reset":"Atur ulang",
  "REQUEST SUBJECT":"SUBJEK PERMINTAAN",
  "VENDOR PORTFOLIO":"PORTOFOLIO VENDOR",
  "REQUEST DATE":"TANGGAL PERMINTAAN",
  "REQUESTER / OWNER":"PEMOHON / PIC",
  "KHS ITEMS":"ITEM KHS",
  "FULLY INJECTED":"INJEKSI PENUH",
  "Loading requests…":"Memuat permintaan…",
  "WORKSPACE / RECORDS":"RUANG KERJA / DATA",
  "Manage each contract record, assign ownership, and update its milestones.":"Kelola setiap data kontrak, tetapkan PIC, dan perbarui milestone.",
  "Add KHS":"Tambah KHS",
  "Filter KHS records":"Filter data KHS",
  "Search KHS records":"Cari data KHS",
  "Search by request, vendor or KHS ID…":"Cari berdasarkan permintaan, vendor, atau ID KHS…",
  "Filter by LP status":"Filter berdasarkan status LP",
  "All LP statuses":"Semua status LP",
  "Completed":"Selesai",
  "In progress":"Sedang Berjalan",
  "Not started":"Belum Dimulai",
  "More filters":"Filter lainnya",
  "Executor":"Pelaksana",
  "All executors":"Semua pelaksana",
  "Contract type":"Jenis kontrak",
  "All subtypes":"Semua jenis",
  "Waiting for":"Menunggu",
  "All waiting parties":"Semua pihak",
  "Workflow stage":"Tahap alur kerja",
  "All workflow stages":"Semua tahap alur kerja",
  "Process status":"Status proses",
  "All process statuses":"Semua status proses",
  "Active":"Aktif",
  "Reset filters":"Atur ulang filter",
  "REQUEST / VENDOR":"PERMINTAAN / VENDOR",
  "CURRENT STAGE & AGE":"TAHAP SAAT INI & DURASI",
  "LP STATUS":"STATUS LP",
  "INJECTION":"INJEKSI",
  "NEXT ACTION":"TINDAKAN BERIKUTNYA",
  "No KHS records match the current filters.":"Tidak ada data KHS yang sesuai dengan filter.",
  "APPROVAL JOURNEY / LP":"ALUR PERSETUJUAN / LP",
  "Track every LP milestone from User submission through Director sign-off, with current stage and stage age.":"Pantau setiap milestone LP mulai dari pengajuan User hingga tanda tangan Direktur, termasuk tahap dan durasinya.",
  "All LP records":"Semua data LP",
  "Started or historically recorded":"Sudah dimulai atau memiliki catatan historis",
  "Next milestone":"Milestone berikutnya",
  "Awaiting approval":"Menunggu persetujuan",
  "LP Completed":"LP Selesai",
  "Director signed":"Ditandatangani Direktur",
  "Historical data quality":"Kualitas data historis",
  "Review these separately from the live approval route.":"Tinjau bagian ini secara terpisah dari alur persetujuan aktif.",
  "MI GM Exceptions":"Pengecualian MI GM",
  "LP gate not met":"Prasyarat LP belum terpenuhi",
  "Legacy Unverified":"Data Lama Belum Terverifikasi",
  "Director sign-off unverified":"Tanda tangan Direktur belum terverifikasi",
  "Missing historical dates":"Tanggal historis belum tersedia",
  "Search LP circulation records":"Cari data sirkulasi LP",
  "Search KHS, request, vendor…":"Cari KHS, permintaan, vendor…",
  "All LP stages":"Semua tahap LP",
  "MI GM prerequisite exception":"Pengecualian prasyarat MI GM",
  "Legacy stage unverified":"Tahap historis belum terverifikasi",
  "Director / Direktur":"Direktur",
  "LP START":"MULAI LP",
  "STAGE AGE":"DURASI TAHAP",
  "WAITING FOR / NEXT ACTION":"MENUNGGU / TINDAKAN BERIKUTNYA",
  "HISTORY":"RIWAYAT",
  "Loading LP records…":"Memuat data LP…",
  "No LP records match the selected stage.":"Tidak ada data LP yang sesuai dengan tahap yang dipilih.",
  "WORKSPACE / PROCESS CONTROL":"RUANG KERJA / KENDALI PROSES",
  "See where records are waiting and open the matching worklist directly.":"Lihat tahapan tempat data tertahan dan buka daftar kerja terkait secara langsung.",
  "Loading workflow stages…":"Memuat tahapan alur kerja…",
  "Show empty stages":"Tampilkan tahap kosong",
  "Hide empty stages":"Sembunyikan tahap kosong",
  "Loading workflow…":"Memuat alur kerja…",
  "LoA Sign-off Route":"Alur Persetujuan LoA",
  "LP circulation is gated by GM SCM MI approval. The route is shown for process visibility; individual sign-off dates remain tracked on each KHS record.":"Sirkulasi LP mensyaratkan persetujuan MI GM SCM. Alur ini ditampilkan untuk visibilitas proses; tanggal persetujuan setiap tahap tetap dicatat pada masing-masing data KHS.",
  "POST-INJECTION / RENEWAL CONTROL":"SETELAH INJEKSI / KENDALI PERPANJANGAN",
  "Monitor contract duration and expiry exposure after KHS is fully injected.":"Pantau durasi kontrak dan risiko kedaluwarsa setelah KHS selesai diinjeksikan.",
  "Eligible contracts":"Kontrak yang memenuhi kriteria",
  "Expiring ≤ 6 months":"Akan berakhir ≤ 6 bulan",
  "Expiring ≤ 3 months":"Akan berakhir ≤ 3 bulan",
  "Expiring ≤ 1 month":"Akan berakhir ≤ 1 bulan",
  "Start renewal preparation":"Mulai persiapan perpanjangan",
  "Renewal action required":"Perlu tindakan perpanjangan",
  "Escalate renewal":"Eskalasi perpanjangan",
  "Requires data completion":"Memerlukan pelengkapan data",
  "Search contract lifecycle records":"Cari data siklus kontrak",
  "All lifecycle statuses":"Semua status siklus kontrak",
  "Upcoming contract":"Kontrak yang akan berlaku",
  "Expiring within 6 months":"Berakhir dalam 6 bulan",
  "Expiring within 3 months":"Berakhir dalam 3 bulan",
  "Expiring within 1 month":"Berakhir dalam 1 bulan",
  "Urgent · 14 days":"Mendesak · 14 hari",
  "Final warning · 7 days":"Peringatan akhir · 7 hari",
  "Missing contract dates":"Tanggal kontrak belum lengkap",
  "Invalid contract dates":"Tanggal kontrak tidak valid",
  "Active · over 6 months":"Aktif · lebih dari 6 bulan",
  "CONTRACT PERIOD":"PERIODE KONTRAK",
  "TERM":"JANGKA WAKTU",
  "TIME REMAINING":"SISA WAKTU",
  "CONTRACT STATUS":"STATUS KONTRAK",
  "RENEWAL ALERT":"PERINGATAN PERPANJANGAN",
  "Loading contracts…":"Memuat kontrak…",
  "No fully injected contracts match this lifecycle filter.":"Tidak ada kontrak yang sudah diinjeksi penuh dan sesuai dengan filter ini.",
  "The 6-, 3-, and 1-month counts are cumulative urgency thresholds, so shorter horizons are included in longer ones. Alert stages use Contract End Date and Jakarta local date. Monitoring is in-app; email and WhatsApp notifications are not enabled.":"Jumlah 6, 3, dan 1 bulan merupakan ambang urgensi kumulatif, sehingga periode yang lebih singkat termasuk dalam periode yang lebih panjang. Tahap peringatan menggunakan tanggal akhir kontrak dan tanggal lokal Jakarta. Pemantauan tersedia di aplikasi; notifikasi email dan WhatsApp belum diaktifkan.",
  "DATA MANAGEMENT / WORKBOOK WORKSPACE":"MANAJEMEN DATA / RUANG KERJA EXCEL",
  "Download the latest database workbook, edit existing records by ID, then preview and confirm the changes. Legacy v2.2 and v2.3 workbooks remain supported.":"Unduh workbook database terbaru, ubah data berdasarkan ID, lalu tinjau dan konfirmasi perubahan. Workbook versi lama v2.2 dan v2.3 tetap didukung.",
  "Download current Excel":"Unduh Excel terbaru",
  "Export KHS CSV":"Ekspor KHS CSV",
  "Download the live workbook":"Unduh workbook terbaru",
  "Start with the latest database snapshot":"Mulai dari salinan database terbaru",
  "Update in Excel":"Perbarui di Excel",
  "Keep record IDs unchanged":"Jangan mengubah ID data",
  "Validate & confirm":"Validasi & konfirmasi",
  "Review changes before they are saved":"Tinjau perubahan sebelum disimpan",
  "Upload edited KHS workbook":"Unggah workbook KHS yang telah diubah",
  "Use the current workbook download for updates. Keep Request ID and KHS ID unchanged. Blank cells preserve existing database values; removed rows do not delete records.":"Gunakan workbook terbaru untuk melakukan pembaruan. Jangan mengubah Request ID dan KHS ID. Sel kosong mempertahankan nilai database; baris yang dihapus tidak menghapus data.",
  "You can also drag and drop an .xlsx file here.":"Anda juga dapat menarik dan meletakkan file .xlsx di sini.",
  "Choose file":"Pilih file",
  "No file selected":"Belum ada file yang dipilih",
  "Validate workbook":"Validasi workbook",
  "VALIDATION RESULT":"HASIL VALIDASI",
  "Workbook preview":"Pratinjau workbook",
  "PREVIEWED":"SUDAH DITINJAU",
  "Total rows":"Total baris",
  "Valid rows":"Baris valid",
  "Warnings":"Peringatan",
  "Errors":"Kesalahan",
  "Changes to be applied":"Perubahan yang akan diterapkan",
  "New records":"Data baru",
  "Updated records":"Data diperbarui",
  "Unchanged records":"Data tidak berubah",
  "Changed fields":"Kolom berubah",
  "RECORD":"DATA",
  "OPERATION":"OPERASI",
  "FIELDS TO CHANGE":"KOLOM YANG DIUBAH",
  "The preview is calculated against the current database values. Blank cells remain no-change; no records are written until Confirm Import.":"Pratinjau dihitung berdasarkan nilai database saat ini. Sel kosong tidak mengubah data; tidak ada perubahan yang disimpan sebelum Konfirmasi Impor.",
  "SEVERITY":"TINGKAT",
  "ENTITY":"ENTITAS",
  "SHEET / ROW":"SHEET / BARIS",
  "DETAIL":"RINCIAN",
  "Additional issues are not displayed.":"Masalah lainnya tidak ditampilkan.",
  "I have reviewed and acknowledge the warnings.":"Saya telah meninjau dan memahami peringatan tersebut.",
  "Review validation result.":"Tinjau hasil validasi.",
  "Confirm import":"Konfirmasi impor",
  "AUDIT TRAIL":"JEJAK AUDIT",
  "Import History":"Riwayat Impor",
  "Refresh history":"Muat ulang riwayat",
  "BATCH":"BATCH",
  "WORKBOOK":"WORKBOOK",
  "STATUS":"STATUS",
  "ROWS":"BARIS",
  "INSERTED":"DITAMBAHKAN",
  "UPDATED":"DIPERBARUI",
  "UNCHANGED":"TIDAK BERUBAH",
  "UPLOADED":"DIUNGGAH",
  "Not loaded.":"Belum dimuat.",
  "No import batches yet.":"Belum ada batch impor.",
  "DATA MANAGEMENT / TRACEABILITY":"MANAJEMEN DATA / KETERLACAKAN",
  "Manual edits and Excel imports are recorded for traceability. Manual edits are labelled manual-entry until sign-in is introduced.":"Perubahan manual dan impor Excel dicatat agar dapat ditelusuri. Perubahan manual diberi label manual-entry hingga fitur login tersedia.",
  "Search activity history":"Cari riwayat aktivitas",
  "Search record ID, actor, action…":"Cari ID data, pelaku, tindakan…",
  "Filter activity entity":"Filter entitas aktivitas",
  "All entities":"Semua entitas",
  "KHS records":"Data KHS",
  "Requests":"Permintaan",
  "WHEN":"WAKTU",
  "ENTITY":"ENTITAS",
  "RECORD ID":"ID DATA",
  "ACTOR":"PELAKU",
  "CHANGES":"PERUBAHAN",
  "No activity matches the current filters.":"Tidak ada aktivitas yang sesuai dengan filter.",
  "KHS Contract Operations":"Operasional Kontrak KHS",
  "Internal workspace":"Ruang kerja internal",
  "NEW RECORD":"DATA BARU",
  "Create record":"Buat data",
  "Save record":"Simpan data",
  "Cancel":"Batal",
  "EDIT RECORD":"UBAH DATA",
  "Edit record":"Ubah data",
  "Edit Request":"Ubah Permintaan",
  "Edit KHS item":"Ubah item KHS",
  "Create Request":"Buat Permintaan",
  "Create KHS item":"Buat item KHS",
  "Request":"Permintaan",
  "KHS item":"Item KHS",
  "Enter milestone dates only when supported by a recorded submission, approval, or completion. MI GM approval and LP chronology are validated when saved.":"Isi tanggal milestone hanya jika didukung bukti pengajuan, persetujuan, atau penyelesaian. Persetujuan MI GM dan urutan tanggal LP akan divalidasi saat disimpan.",
  "Request ID is generated automatically when the record is saved.":"Request ID dibuat otomatis saat data disimpan.",
  "Select request":"Pilih permintaan",
  "Select executor":"Pilih pelaksana",
  "Choose contract type":"Pilih jenis kontrak",
  "current / inactive":"saat ini / tidak aktif",
  "Edit record.":"Ubah data.",
  "REQUEST / VENDOR":"PERMINTAAN / VENDOR",
  "Supplier & request":"Pemasok & permintaan",
  "Commercial & approval history":"Riwayat komersial & persetujuan",
  "Coordination & next action":"Koordinasi & tindakan berikutnya",
  "Request subject":"Subjek permintaan",
  "Request ID":"ID Permintaan",
  "Vendor":"Vendor",
  "Executor":"Pelaksana",
  "Dispatch":"Pengiriman",
  "BOQ confirmation":"Konfirmasi BOQ",
  "Contract start":"Mulai kontrak",
  "Contract end":"Akhir kontrak",
  "Negotiation":"Negosiasi",
  "Final negotiation":"Negosiasi final",
  "MI Head approval":"Persetujuan MI Head",
  "MI SM approval":"Persetujuan MI SM",
  "MI GM approval":"Persetujuan MI GM",
  "Legal submission":"Pengajuan Legal",
  "Waiting reason":"Alasan menunggu",
  "Remarks":"Catatan",
  "Last updated":"Pembaruan terakhir",
  "Recent activity":"Aktivitas terbaru",
  "Download":"Unduh",
  "No evidence documents uploaded yet.":"Belum ada dokumen bukti yang diunggah.",
  "KHS RECORD":"DATA KHS",
  "KHS Details":"Detail KHS",
  "PROCESS CLOSURE":"PENUTUPAN PROSES",
  "Close KHS as Not Proceeded":"Tutup KHS sebagai Tidak Dilanjutkan",
  "Close KHS":"Tutup KHS",
  "Use this only when the process will not continue. Existing milestones and evidence will be preserved.":"Gunakan hanya jika proses tidak akan dilanjutkan. Milestone dan dokumen bukti yang sudah ada akan tetap disimpan.",
  "Closure date":"Tanggal penutupan",
  "Closure reason":"Alasan penutupan",
  "Select a reason":"Pilih alasan",
  "No mutual agreement":"Tidak tercapai kesepakatan",
  "Withdrawn by requester":"Ditarik oleh pemohon",
  "Vendor declined":"Vendor menolak",
  "Internally rejected":"Ditolak secara internal",
  "Duplicate / created in error":"Duplikat / dibuat karena kesalahan",
  "Other":"Lainnya",
  "Closure notes":"Catatan penutupan",
  "Add context or decision reference":"Tambahkan konteks atau referensi keputusan",
  "Confirm closure":"Konfirmasi penutupan",
  "REOPEN PROCESS":"BUKA KEMBALI PROSES",
  "Reopen KHS":"Buka Kembali KHS",
  "Reopening restores this KHS to the active work queue. The previous closure remains in the audit history.":"Membuka kembali KHS akan mengembalikannya ke antrean aktif. Riwayat penutupan sebelumnya tetap tersimpan dalam log audit.",
  "Reason for reopening":"Alasan membuka kembali",
  "Close KHS":"Tutup KHS",
  "END-TO-END PROCESS":"PROSES MENYELURUH",
  "Process Duration History":"Riwayat Durasi Proses",
  "Elapsed time is calculated from recorded milestone dates.":"Durasi dihitung berdasarkan tanggal milestone yang tercatat.",
  "Total processing time":"Total waktu proses",
  "LP circulation time":"Durasi sirkulasi LP",
  "Missing or inconsistent milestone dates are shown as incomplete history; the system does not estimate missing dates.":"Tanggal milestone yang hilang atau tidak konsisten ditampilkan sebagai riwayat tidak lengkap; sistem tidak memperkirakan tanggal yang hilang.",
  "LP CIRCULATION":"SIRKULASI LP",
  "Approval journey":"Alur persetujuan",
  "Evidence-led view of the six LP milestones":"Tampilan enam milestone LP berdasarkan bukti",
  "Current Stage":"Tahap Saat Ini",
  "Stage Age":"Durasi Tahap",
  "Upcoming":"Berikutnya",
  "POST-INJECTION":"SETELAH INJEKSI",
  "Evidence Documents":"Dokumen Bukti",
  "Supporting files attached to this KHS record.":"File pendukung yang dilampirkan pada data KHS ini.",
  "Document type":"Jenis dokumen",
  "KHS Evidence":"Bukti KHS",
  "KHS Inject Evidence":"Bukti Injeksi KHS",
  "LP Evidence":"Bukti LP",
  "Supporting Document":"Dokumen Pendukung",
  "Choose file":"Pilih file",
  "Upload evidence":"Unggah bukti",
  "Loading documents…":"Memuat dokumen…",
  "Close":"Tutup",
  "Details":"Detail",
  "View record":"Lihat data",
  "No records currently require attention.":"Tidak ada data yang memerlukan perhatian saat ini.",
  "No records match the current filters.":"Tidak ada data yang sesuai dengan filter saat ini.",
  "Untitled request":"Permintaan tanpa judul",
  "Unassigned":"Belum ditetapkan",
  "No waiting owner recorded":"Belum ada PIC penanggung jawab yang tercatat",
  "Review data / prerequisite":"Tinjau data / prasyarat",
  "MI GM prerequisite review":"Pemeriksaan prasyarat MI GM",
  "Director sign-off unverified":"Tanda tangan Direktur belum terverifikasi",
  "Historical timeline gaps":"Kesenjangan lini masa historis",
  "Partial history":"Riwayat parsial",
  "Recorded":"Tercatat",
  "Review required":"Perlu Ditinjau",
  "History needs review":"Riwayat perlu ditinjau",
  "Stage age unavailable":"Durasi tahap tidak tersedia",
  "Closed stage":"Tahap ditutup",
  "Not Proceeded":"Tidak Dilanjutkan",
  "Stopped":"Dihentikan",
  "Not reached":"Belum Dicapai",
  "No further LP milestone":"Tidak ada milestone LP berikutnya",
  "LP not reached":"Tahap LP belum dimulai",
  "LP completed":"LP selesai",
  "KHS process stopped":"Proses KHS dihentikan",
  "No fully-injected completion was recorded.":"Tidak ada penyelesaian injeksi penuh yang tercatat.",
  "No LP stage was opened.":"Belum ada tahap LP yang dimulai.",
  "No active LP stage.":"Tidak ada tahap LP yang aktif.",
  "Data needs review":"Data perlu ditinjau",
  "History incomplete":"Riwayat tidak lengkap",
  "Date unavailable":"Tanggal tidak tersedia",
  "Invalid chronology":"Urutan tanggal tidak valid",
  "In progress":"Sedang Berjalan",
  "Stopped":"Dihentikan",
  "Completed":"Selesai",
  "Not started":"Belum Dimulai",
  "Closed":"Ditutup",
  "Stopped on":"Dihentikan pada",
  "Since":"Sejak",
  "Updated":"Diperbarui",
  "No process milestones are recorded.":"Belum ada milestone proses yang tercatat.",
  "Request Received":"Permintaan Diterima",
  "BOQ Confirmation":"Konfirmasi BOQ",
  "Negotiation":"Negosiasi",
  "Final Negotiation":"Negosiasi Final",
  "MI Approval - Head":"Persetujuan MI - Head",
  "MI Approval - SM":"Persetujuan MI - SM",
  "MI Approval - GM":"Persetujuan MI - GM",
  "Legal Submission":"Pengajuan Legal",
  "Legal Processing":"Proses Legal",
  "KHS Inject":"Injeksi KHS",
  "Fully Injected":"Injeksi Penuh",
  "LP Contract Team":"Tim Kontrak LP",
  "LP Junior Manager":"Manajer Junior LP",
  "LP Senior Manager":"Manajer Senior LP",
  "LP GM SCM":"GM SCM LP",
  "LP Director Sign-off":"Tanda Tangan Direktur LP",
  "Injection Preparation":"Persiapan Injeksi",
  "KHS Injection":"Injeksi KHS",
  "User submitted":"Diajukan oleh User",
  "LP circulation started":"Sirkulasi LP dimulai",
  "Contract Team completion":"Penyelesaian Tim Kontrak",
  "Vendor Management approval":"Persetujuan Vendor Management",
  "Strategic Sourcing approval":"Persetujuan Strategic Sourcing",
  "General Management approval":"Persetujuan General Management",
  "Director sign-off":"Tanda tangan Direktur",
  "Director-signed LP completion":"LP selesai ditandatangani Direktur",
  "The next approval or completion milestone is outstanding.":"Persetujuan atau milestone penyelesaian berikutnya masih menunggu.",
  "Next milestone in sequence":"Milestone berikutnya dalam urutan",
  "Final LP milestone":"Milestone LP terakhir",
  "There is no active LP stage.":"Tidak ada tahap LP yang aktif.",
  "The clock starts when LP is submitted.":"Penghitungan dimulai saat LP diajukan.",
  "The available milestone history does not support a reliable active-stage assignment.":"Riwayat milestone yang tersedia belum cukup untuk menentukan tahap aktif secara andal.",
  "No next approval stage has been inferred.":"Tahap persetujuan berikutnya belum dapat ditentukan.",
  "Stage age is withheld until the current stage can be established.":"Durasi tahap belum dihitung karena tahap saat ini belum dapat dipastikan.",
  "The LP route stopped at":"Alur LP dihentikan pada",
  "The KHS process was closed on":"Proses KHS ditutup pada",
  "The approval route stopped when the KHS was closed.":"Alur persetujuan berhenti saat KHS ditutup.",
  "The LP approval route was not started.":"Alur persetujuan LP belum dimulai.",
  "CLOSURE DATE":"TANGGAL PENUTUPAN",
  "Reason:":"Alasan:",
  "No additional notes recorded.":"Tidak ada catatan tambahan.",
  "Closed by":"Ditutup oleh",
  "Reopened":"Dibuka kembali",
  "Workflow:":"Alur kerja:",
  "KHS closed as Not Proceeded.":"KHS ditutup dengan status Tidak Dilanjutkan.",
  "KHS reopened.":"KHS berhasil dibuka kembali.",
  "Record updated.":"Data berhasil diperbarui.",
  "Record created.":"Data berhasil dibuat.",
  "No changes to save.":"Tidak ada perubahan untuk disimpan.",
  "Saving…":"Menyimpan…",
  "Closing…":"Menutup…",
  "Reopening…":"Membuka kembali…",
  "Unable to close KHS.":"KHS tidak dapat ditutup.",
  "Unable to reopen KHS.":"KHS tidak dapat dibuka kembali.",
  "Request failed":"Permintaan gagal",
  "A JSON object is required.":"Diperlukan objek JSON.",
  "KHS not found.":"Data KHS tidak ditemukan.",
  "Request not found.":"Data permintaan tidak ditemukan.",
  "Only a Not Proceeded KHS can be reopened.":"Hanya KHS berstatus Tidak Dilanjutkan yang dapat dibuka kembali.",
  "This KHS is already marked as Not Proceeded.":"KHS ini sudah berstatus Tidak Dilanjutkan.",
  "A fully injected KHS cannot be closed as Not Proceeded.":"KHS yang sudah fully injected tidak dapat ditutup sebagai Tidak Dilanjutkan.",
  "Closure date cannot be in the future.":"Tanggal penutupan tidak boleh di masa depan.",
  "Closure date cannot precede the original request date.":"Tanggal penutupan tidak boleh lebih awal daripada tanggal permintaan awal.",
  "Closure date cannot precede the latest recorded milestone.":"Tanggal penutupan tidak boleh lebih awal daripada milestone terakhir yang tercatat.",
  "Add a note when selecting Other.":"Tambahkan catatan jika memilih Lainnya.",
  "Select a supported closure reason.":"Pilih alasan penutupan yang tersedia.",
  "Reopen this KHS before editing its milestones.":"Buka kembali KHS sebelum mengubah milestone.",
  "This KHS is already marked as Not Proceeded.":"KHS ini sudah berstatus Tidak Dilanjutkan.",
  "No evidence documents uploaded yet.":"Belum ada dokumen bukti yang diunggah.",
  "Upload evidence":"Unggah bukti",
  "Upload complete.":"Unggah selesai.",
  "The file could not be uploaded.":"File tidak dapat diunggah.",
  "No activity matches the current filters.":"Tidak ada aktivitas yang sesuai dengan filter.",
  "No import batches yet.":"Belum ada batch impor.",
  "No file selected":"Belum ada file yang dipilih",
  "Upload edited KHS workbook":"Unggah workbook KHS yang telah diperbarui",
  "Preview and validate":"Pratinjau dan validasi",
  "Review validation result.":"Tinjau hasil validasi.",
  "Confirm Import":"Konfirmasi Impor",
  "Import confirmed.":"Impor dikonfirmasi.",
  "Import preview":"Pratinjau impor",
  "Please choose a workbook first.":"Pilih workbook terlebih dahulu.",
  "The workbook could not be validated.":"Workbook tidak dapat divalidasi.",
  "The import could not be completed.":"Impor tidak dapat diselesaikan.",
  "Request ID is required.":"Request ID wajib diisi.",
  "Vendor name is required.":"Nama vendor wajib diisi.",
  "Select request":"Pilih permintaan",
  "Select executor":"Pilih pelaksana",
  "Search":"Cari",
  "LP status":"Status LP",
  "Contract type":"Jenis kontrak",
  "Waiting for":"Menunggu",
  "Workflow stage":"Tahap alur kerja",
  "Process status":"Status proses",
  "Queue":"Antrean",
  "Needs attention":"Perlu perhatian",
  "Approval role":"Peran pemberi persetujuan",
  "Clear all":"Hapus semua filter",
  "No results":"Tidak ada hasil",
  "Details":"Detail",
  "REQUEST / KHS":"PERMINTAAN / KHS",
  "Request Date":"Tanggal Permintaan",
  "Contract Status":"Status Kontrak",
  "Renewal Alert":"Peringatan Perpanjangan",
  "Contract status":"Status kontrak",
  "Renewal alert":"Peringatan perpanjangan",
  "Contract term":"Jangka waktu kontrak",
  "Time remaining":"Sisa waktu",
  "Injection started":"Injeksi dimulai",
  "Fully injected":"Injeksi penuh",
  "No contract dates":"Tanggal kontrak belum tersedia",
  "Dates required":"Tanggal diperlukan",
  "Upcoming":"Akan Datang",
  "Expired":"Kedaluwarsa",
  "Active":"Aktif",
  "Not fully injected":"Belum fully injected",
  "Renewal action due":"Tindakan perpanjangan diperlukan",
  "Open navigation":"Buka navigasi",
  "Close navigation":"Tutup navigasi",
  "Switch to Bahasa Indonesia":"Ubah ke Bahasa Indonesia",
  "Switch to English":"Ubah ke bahasa Inggris",
  "Search activity history":"Cari riwayat aktivitas",
  "All activities":"Semua aktivitas",
  "Page":"Halaman",
  "records":"data",
  "activities":"aktivitas",
  "batches":"batch",
  "contracts":"kontrak",
  "days":"hari",
  "day":"hari",
  "NOT_PROCEEDED":"Tidak Dilanjutkan",
  "NO_MUTUAL_AGREEMENT":"Tidak tercapai kesepakatan",
  "REQUESTER_WITHDRAWAL":"Ditarik oleh pemohon",
  "VENDOR_DECLINED":"Vendor menolak",
  "INTERNAL_REJECTION":"Ditolak secara internal",
  "DUPLICATE":"Duplikat",
  "OTHER":"Lainnya",
  "MI Senior Manager Approval":"Persetujuan Manajer Senior MI",
  "MI General Manager Approval":"Persetujuan General Manager MI",
  "Invalid dates":"Tanggal tidak valid",
  "Action required · 1 month":"Perlu tindakan · 1 bulan",
  "Renewal watch · 3 months":"Pemantauan perpanjangan · 3 bulan",
  "Renewal preparation · 6 months":"Persiapan perpanjangan · 6 bulan",
  "Closed · duration unavailable":"Ditutup · durasi tidak tersedia",
  "Open records →":"Buka data →",
  "In progress":"Sedang Berjalan",
  "not started":"Belum Dimulai",
  "completed":"Selesai",
  "in progress":"Sedang Berjalan",
  "active":"Aktif",
  "expired":"Kedaluwarsa",
  "upcoming":"Akan datang",
  "missing dates":"Tanggal belum lengkap",
  "invalid dates":"Tanggal tidak valid",
  "Request date":"Tanggal permintaan",
  "Request subject":"Subjek permintaan",
  "Requester / owner":"Pemohon / PIC",
  "Parent request":"Permintaan induk",
  "Vendor name":"Nama vendor",
  "Dispatch date":"Tanggal pengiriman",
  "Contract start date":"Tanggal mulai kontrak",
  "Contract end date":"Tanggal akhir kontrak",
  "BOQ confirmation date":"Tanggal konfirmasi BOQ",
  "Negotiation date":"Tanggal negosiasi",
  "Final negotiation date":"Tanggal negosiasi final",
  "MI Head approval":"Persetujuan MI Head",
  "MI SM approval":"Persetujuan MI SM",
  "MI GM approval":"Persetujuan MI GM",
  "Legal submission date":"Tanggal pengajuan Legal",
  "LP circulation start / User submitted":"Tanggal mulai LP / diajukan User",
  "LP Contract Team completion":"Penyelesaian Tim Kontrak LP",
  "LP Junior Manager approval":"Persetujuan Manajer Junior LP",
  "LP Senior Manager approval":"Persetujuan Manajer Senior LP",
  "LP GM SCM approval":"Persetujuan LP GM SCM",
  "LP Director sign-off / LP completion":"Tanda tangan Direktur LP / penyelesaian LP",
  "KHS injection start":"Mulai injeksi KHS",
  "KHS fully injected date":"Tanggal KHS fully injected",
  "Currently waiting for":"Saat ini menunggu",
  "Waiting reason / next action":"Alasan menunggu / tindakan berikutnya",
  "Supplier & contract":"Pemasok & kontrak",
  "The request, supplier, owner, and contract identity.":"Identitas permintaan, pemasok, PIC, dan kontrak.",
  "Commercial & MI approvals":"Persetujuan Komersial & MI",
  "Commercial checkpoints and approvals required before LP circulation.":"Tahap komersial dan persetujuan yang diperlukan sebelum sirkulasi LP.",
  "Record each submission, completion, and approval date only when supported by evidence.":"Catat tanggal pengajuan, penyelesaian, dan persetujuan hanya jika didukung bukti.",
  "This phase starts only after Director-signed LP completion.":"Tahap ini hanya dimulai setelah LP ditandatangani Direktur.",
  "Who currently holds the action, why it is waiting, and contextual notes.":"Siapa PIC tindakan saat ini, alasan tertunda, dan catatan pendukung.",
  "Request date":"Tanggal permintaan",
  "Request subject":"Subjek permintaan",
  "Requester / owner":"Pemohon / PIC",
  "Parent request":"Permintaan induk",
  "Vendor name":"Nama vendor",
  "Dispatch date":"Tanggal pengiriman",
  "Contract start date":"Tanggal mulai kontrak",
  "Contract end date":"Tanggal akhir kontrak",
  "BOQ confirmation date":"Tanggal konfirmasi BOQ",
  "Negotiation date":"Tanggal negosiasi",
  "Final negotiation date":"Tanggal negosiasi final",
  "Legal submission date":"Tanggal pengajuan Legal",
  "LP circulation start / User submitted":"Tanggal mulai LP / diajukan User",
  "LP Contract Team completion":"Penyelesaian Tim Kontrak LP",
  "LP Junior Manager approval":"Persetujuan Manajer Junior LP",
  "LP Senior Manager approval":"Persetujuan Manajer Senior LP",
  "LP GM SCM approval":"Persetujuan LP GM SCM",
  "LP Director sign-off / LP completion":"Tanda tangan Direktur LP / penyelesaian LP",
  "KHS injection start":"Mulai injeksi KHS",
  "KHS fully injected date":"Tanggal KHS fully injected",
  "Currently waiting for":"Saat ini menunggu",
  "Waiting reason / next action":"Alasan menunggu / tindakan berikutnya",
  "No request records found.":"Tidak ada data permintaan.",
  "Page":"Halaman",
  "Page 1":"Halaman 1",
  "No workflow stages currently contain records.":"Tidak ada tahap alur kerja yang memiliki data saat ini.",
  "Open records →":"Buka data →",
  "Search request":"Cari permintaan",
  "Edit":"Ubah",
  "Current / inactive":"Saat ini / tidak aktif",
  "Expires today":"Berakhir hari ini",
  "days in stage":"hari dalam tahap",
  "Close this dialog":"Tutup dialog ini",
  "Switch to Bahasa Indonesia":"Beralih ke Bahasa Indonesia",
  "Switch to English":"Beralih ke bahasa Inggris",
  "No contract records found.":"Tidak ada data kontrak.",
  "All records":"Semua data",
  "No records were found.":"Data tidak ditemukan.",
  "View attention queue":"Lihat antrean perhatian",
  "LP submission":"Pengajuan LP",
  "Approval pending":"Menunggu persetujuan",
  "The next approval or completion milestone is outstanding.":"Persetujuan atau milestone penyelesaian berikutnya masih tertunda.",
  "A legacy completion label is not proof of a Director-signed LP.":"Label penyelesaian pada data lama bukan bukti bahwa LP telah ditandatangani Direktur.",
  "Missing historical dates prevent a reliable current-stage assignment.":"Tanggal historis yang hilang membuat tahap saat ini belum dapat ditentukan secara andal.",
  "The LP start date does not satisfy the MI GM approval prerequisite.":"Tanggal mulai LP tidak memenuhi prasyarat persetujuan MI GM.",
  "There is no active LP stage.":"Tidak ada tahap LP yang sedang berjalan.",
  "Director sign-off recorded on":"Tanda tangan Direktur tercatat pada",
  "The post-LP contract phase.":"Tahap kontrak setelah LP.",
  "The KHS process closed before LP Circulation began.":"Proses KHS ditutup sebelum sirkulasi LP dimulai.",
  "Date not recorded":"Tanggal belum tercatat",
  "No historical date on record":"Tidak ada tanggal historis yang tercatat",
  "Current Stage":"Tahap Saat Ini",
  "Upcoming":"Berikutnya",
  "Next approval":"Persetujuan berikutnya",
  "Approval":"Persetujuan",
  "No waiting owner recorded":"Belum ada PIC yang tercatat",
  "History needs review":"Riwayat perlu ditinjau",
  "Date unavailable":"Tanggal tidak tersedia",
  "Invalid chronology":"Urutan tanggal tidak valid",
  "history_incomplete":"Riwayat tidak lengkap",
  "WORKFLOW STAGE / BOTTLENECK RANK":"TAHAP ALUR KERJA / PERINGKAT BOTTLENECK",
  "AGE UNAVAILABLE":"UMUR TAHAP TIDAK TERSEDIA",
  "BOTTLENECK RANK":"PERINGKAT BOTTLENECK",
  "No changes to save.":"Tidak ada perubahan untuk disimpan.",
  "Request created.":"Permintaan berhasil dibuat.",
  "Request updated.":"Permintaan berhasil diperbarui.",
  "KHS created.":"KHS berhasil dibuat.",
  "KHS updated.":"KHS berhasil diperbarui.",
  "The workbook was imported successfully.":"Workbook berhasil diimpor.",
  "Import preview generated.":"Pratinjau impor berhasil dibuat.",
  "Confirm import":"Konfirmasi impor",
  "Confirm Import":"Konfirmasi Impor",
  "No changes detected.":"Tidak ada perubahan yang ditemukan.",
  "Please select a file.":"Silakan pilih file.",
  "Select a file first.":"Pilih file terlebih dahulu.",
  "The file is too large.":"Ukuran file terlalu besar.",
  "The file type is not supported.":"Jenis file tidak didukung.",
  "Request ID":"ID Permintaan",
  "KHS ID":"ID KHS",
  "Request date":"Tanggal permintaan",
  "Not Proceeded":"Tidak Dilanjutkan",
  "NO_MUTUAL_AGREEMENT":"Tidak tercapai kesepakatan",
  "REQUESTER_WITHDRAWAL":"Ditarik oleh pemohon",
  "VENDOR_DECLINED":"Vendor menolak",
  "INTERNAL_REJECTION":"Ditolak secara internal",
  "DUPLICATE":"Duplikat",
  "OTHER":"Lainnya",
  "CLOSED_NOT_PROCEEDED":"Ditutup - Tidak Dilanjutkan",
  "REOPENED":"Dibuka kembali",
  "UPDATED":"Diperbarui",
  "CREATED":"Dibuat",
  "IMPORTED":"Diimpor",
  "KHS_ITEM":"Data KHS",
  "REQUEST":"Permintaan",
  "WIP Aging & Bottleneck Analytics":"Analisis Umur WIP & Hambatan Proses",
  "Current active work-in-progress, stage aging, and configured service-level signals.":"Pekerjaan aktif, umur setiap tahap, dan indikator tingkat layanan yang telah dikonfigurasi.",
  "Active WIP":"WIP Aktif",
  "Open workflow records":"Data alur kerja yang masih terbuka",
  "Over 30 days":"Lebih dari 30 hari",
  "Descriptive aging bucket":"Kelompok umur deskriptif",
  "Age unavailable":"Umur tidak tersedia",
  "Missing stage start date":"Tanggal mulai tahap tidak tersedia",
  "SLA overdue":"SLA terlampaui",
  "Only configured policies":"Hanya kebijakan yang dikonfigurasi",
  "Escalation due":"Perlu eskalasi",
  "Follow-ups overdue":"Tindak lanjut terlambat",
  "In-app reminders":"Pengingat di aplikasi",
  "Stage aging profile":"Profil umur per tahap",
  "Median, P90 and oldest age help identify where work accumulates.":"Median, P90, dan umur terlama membantu mengidentifikasi penumpukan pekerjaan.",
  "SLA not configured":"SLA belum dikonfigurasi",
  "stages configured":"tahap dikonfigurasi",
  "WORKFLOW STAGE":"TAHAP ALUR KERJA",
  "WIP":"WIP",
  "MEDIAN":"MEDIAN",
  "P90":"P90",
  "0–7 DAYS":"0–7 HARI",
  "8–14 DAYS":"8–14 HARI",
  "15–30 DAYS":"15–30 HARI",
  "31+ DAYS":"31+ HARI",
  "OLDEST":"TERLAMA",
  "SLA SIGNAL":"INDIKATOR SLA",
  "OVERDUE":"TERLAMBAT",
  "ESCALATION":"ESKALASI",
  "No target configured":"Target belum dikonfigurasi",
  "Target":"Target",
  "warn":"peringatan",
  "escalate":"eskalasi",
  "Aging buckets are descriptive, not SLA targets. Configure stage SLA thresholds only after the responsible business owners approve them. Missing start dates are not assigned an estimated age.":"Kelompok umur hanya bersifat deskriptif, bukan target SLA. Konfigurasikan ambang SLA setelah disetujui pemilik proses. Tanggal mulai yang hilang tidak diberi perkiraan umur.",
  "Follow-up & escalation inbox":"Kotak masuk tindak lanjut & eskalasi",
  "Scheduled follow-ups due today, overdue, or upcoming for active KHS records.":"Tindak lanjut terjadwal yang jatuh tempo hari ini, terlambat, atau akan datang untuk KHS aktif.",
  "DUE DATE":"TANGGAL JATUH TEMPO",
  "KHS / VENDOR":"KHS / VENDOR",
  "STAGE":"TAHAP",
  "FOLLOW UP TO":"DITINDAKLANJUTI OLEH",
  "NOTE":"CATATAN",
  "Complete":"Selesai",
  "Open KHS":"Buka KHS",
  "Due today":"Jatuh tempo hari ini",
  "Upcoming":"Akan datang",
  "On track":"Sesuai target",
  "Due soon":"Segera jatuh tempo",
  "Overdue":"Terlambat",
  "Escalation due":"Perlu eskalasi",
  "Not configured":"Belum dikonfigurasi",
  "No active WIP records.":"Tidak ada WIP aktif.",
  "No open follow-ups are scheduled.":"Belum ada tindak lanjut terjadwal yang terbuka.",
  "No current-stage follow-ups. Stage-moved reminders remain in record history.":"Tidak ada tindak lanjut untuk tahap saat ini. Pengingat dari tahap sebelumnya tetap ada dalam riwayat.",
  "Open follow-ups":"Tindak lanjut terbuka",
  "Update Progress":"Perbarui Progres",
  "Update:":"Perbarui:",
  "No pending milestone":"Tidak ada milestone tertunda",
  "Schedule Follow-up":"Jadwalkan Tindak Lanjut",
  "KHS WORKBENCH":"RUANG KERJA KHS",
  "Process history":"Riwayat proses",
  "LP milestones":"Milestone LP",
  "Record & activity":"Data & aktivitas",
  "Follow-ups":"Tindak lanjut",
  "Evidence":"Dokumen bukti",
  "GUIDED PROGRESS UPDATE":"PEMBARUAN PROGRES TERPANDU",
  "Update current milestone":"Perbarui milestone saat ini",
  "This action updates only the next milestone allowed by the recorded KHS workflow. Existing milestone history is preserved.":"Tindakan ini hanya memperbarui milestone berikutnya sesuai alur kerja KHS yang tercatat. Riwayat milestone sebelumnya tetap tersimpan.",
  "Next milestone":"Milestone berikutnya",
  "Completion / submission date":"Tanggal penyelesaian / pengajuan",
  "Update note (optional)":"Catatan pembaruan (opsional)",
  "Save progress":"Simpan progres",
  "NEXT ACTION CONTROL":"KENDALI TINDAKAN BERIKUTNYA",
  "Follow-up reminders":"Pengingat tindak lanjut",
  "Schedule an in-app reminder for the current KHS stage and assign the person to follow up.":"Jadwalkan pengingat dalam aplikasi untuk tahap KHS saat ini dan tetapkan PIC tindak lanjut.",
  "Due date":"Tanggal jatuh tempo",
  "Follow up to / PIC":"Ditindaklanjuti oleh / PIC",
  "Person responsible for follow-up":"Orang yang bertanggung jawab atas tindak lanjut",
  "Follow-up note":"Catatan tindak lanjut",
  "What needs to be followed up?":"Apa yang perlu ditindaklanjuti?",
  "Schedule follow-up":"Jadwalkan tindak lanjut",
  "No follow-ups have been scheduled for this KHS.":"Belum ada tindak lanjut yang dijadwalkan untuk KHS ini.",
  "Complete":"Selesai",
  "Cancel":"Batal",
  "Update:":"Perbarui:",
  "Dispatch completed":"Dispatch selesai",
  "BOQ confirmed":"BOQ dikonfirmasi",
  "Negotiation completed":"Negosiasi selesai",
  "Final negotiation completed":"Negosiasi final selesai",
  "MI Head approval recorded":"Persetujuan MI Head tercatat",
  "MI Senior Manager approval recorded":"Persetujuan MI Senior Manager tercatat",
  "MI GM approval recorded":"Persetujuan MI GM tercatat",
  "Legal submission recorded":"Pengajuan Legal tercatat",
  "LP submitted by User":"LP diajukan oleh User",
  "Contract Team completed":"Tim Kontrak selesai",
  "Junior Manager approval recorded":"Persetujuan Junior Manager tercatat",
  "Senior Manager approval recorded":"Persetujuan Senior Manager tercatat",
  "GM SCM approval recorded":"Persetujuan GM SCM tercatat",
  "Director sign-off recorded":"Tanda tangan Direktur tercatat",
  "Injection Preparation":"Persiapan Injeksi",
  "KHS injection started":"Injeksi KHS dimulai",
  "KHS fully injected":"KHS selesai diinjeksi penuh",
  "Action owner / PIC":"PIC tindakan",
  "Saving…":"Menyimpan…",
  "Scheduling…":"Menjadwalkan…",
  "Progress updated.":"Progres berhasil diperbarui.",
  "Follow-up scheduled.":"Tindak lanjut berhasil dijadwalkan.",
  "Follow-up completed.":"Tindak lanjut selesai.",
  "Follow-up cancelled.":"Tindak lanjut dibatalkan.",
  "Follow-up stage":"Tahap tindak lanjut",
  "Unassigned":"Belum ditetapkan",
  "Stage moved":"Tahap telah berubah",
  "No active stage":"Tidak ada tahap aktif",
  "Not on track":"Tidak sesuai target",
  "Median age":"Umur median",
  "Oldest age":"Umur terlama",
  "Active workflow":"Alur kerja aktif",
  "Stage age":"Umur tahap",
  "Aging":"Umur proses",
  "Stage moved reminders remain in record history.":"Pengingat dari tahap sebelumnya tetap tersimpan dalam riwayat data."

  "Control Tower":"Pusat Kendali Operasi",
  "Request Intake":"Penerimaan Permintaan",
  "Work Queue":"Antrean Kerja",
  "Operations Analytics":"Analitik Operasional",
  "DATA & GOVERNANCE":"DATA & TATA KELOLA",
  "One operational list for active KHS, waiting approvals, LP circulation, and records that need ownership or data review.":"Satu daftar operasional untuk KHS aktif, persetujuan tertunda, sirkulasi LP, serta data yang memerlukan PIC atau pemeriksaan.",
  "All KHS":"Semua KHS",
  "Active WIP":"WIP Aktif",
  "Waiting / Attention":"Menunggu / Perlu Perhatian",
  "Data Exceptions":"Pengecualian Data",
  "Unassigned PIC":"PIC Belum Ditentukan",
  "ACTION OWNER":"PIC Tindakan",
  "WAITING ON":"Menunggu Pihak",
  "WAITING ON / CONTEXT":"Menunggu Pihak / Konteks",
  "NEXT ACTION / MILESTONE":"Tindakan Berikutnya / Milestone",
  "LP / INJECTION":"LP / Injeksi",
  "Unassigned":"Belum Ditentukan",
  "No waiting party recorded":"Belum ada pihak yang tercatat untuk ditunggu",
  "No next action recorded":"Belum ada tindakan berikutnya yang dicatat",
  "Review milestone history":"Periksa riwayat milestone",
  "Process completed":"Proses selesai",
  "Complete next milestone":"Selesaikan milestone berikutnya",
  "LP stage":"Tahap LP",
  "LP stage filtering is available in the LP Circulation saved view.":"Filter tahap LP tersedia pada tampilan Sirkulasi LP.",
  "No KHS records match the current filters.":"Tidak ada data KHS yang sesuai dengan filter saat ini."
});

const I18N_ID_LOWER = Object.freeze(
  Object.fromEntries(Object.entries(I18N_ID).map(([key, value]) => [key.toLowerCase(), value]))
);

const originalTextNodes = new WeakMap();
const originalAttributes = new WeakMap();
let currentLanguage = "en";
let languageObserver = null;

function translateText(value, language = currentLanguage) {
  if (!value || language !== "id") return value;
  const leading = (value.match(/^\s*/) || [""])[0];
  const trailing = (value.match(/\s*$/) || [""])[0];
  const core = value.slice(leading.length, value.length - trailing.length || value.length);
  if (!core) return value;
  const exactTranslation = I18N_ID[core];
  const matchedTranslation = exactTranslation || I18N_ID_LOWER[core.toLowerCase()];
  if (matchedTranslation) return leading + matchedTranslation + trailing;

  let match = core.match(/^(\d+) days? in stage$/i);
  if (match) return leading + match[1] + (match[1] === "1" ? " hari dalam tahap" : " hari dalam tahap") + trailing;
  match = core.match(/^Stopped after (\d+) days?$/i);
  if (match) return leading + "Dihentikan setelah " + match[1] + " hari" + trailing;
  match = core.match(/^(\d+) days?$/i);
  if (match) return leading + match[1] + " hari" + trailing;
  match = core.match(/^(\d+) year(s)?(?:, )?(\d+)? month(s)?$/i);
  if (match) return leading + match[1] + " tahun" + (match[3] ? " " + match[3] + " bulan" : "") + trailing;
  match = core.match(/^(\d+) days? remaining$/i);
  if (match) return leading + "tersisa " + match[1] + " hari" + trailing;
  match = core.match(/^(\d+) days? overdue$/i);
  if (match) return leading + "terlambat " + match[1] + " hari" + trailing;
  match = core.match(/^([+↻↓]\s*)(.+)$/);
  if (match) {
    const translatedSuffix = translateText(match[2], language);
    if (translatedSuffix !== match[2]) return leading + match[1] + translatedSuffix + trailing;
  }
  match = core.match(/^More filters · (\d+) active$/);
  if (match) return leading + "Filter lainnya · " + match[1] + " aktif" + trailing;
  match = core.match(/^Update: (.+)$/);
  if (match) return leading + "Perbarui: " + translateText(match[1], language) + trailing;
  match = core.match(/^Open KHS (.+)$/);
  if (match) return leading + "Buka KHS " + match[1] + trailing;
  match = core.match(/^Closed (.+)$/);
  if (match) return leading + "Ditutup " + match[1] + trailing;
  match = core.match(/^Since (.+)$/);
  if (match) return leading + "Sejak " + match[1] + trailing;
  match = core.match(/^Updated (.+)$/);
  if (match) return leading + "Diperbarui " + match[1] + trailing;
  match = core.match(/^Oldest in stage: (\d+) days?$/i);
  if (match) return leading + "Paling lama di tahap: " + match[1] + " hari" + trailing;
  match = core.match(/^(\d+) of (\d+) stages have records · (\d+) records assigned to a workflow stage$/);
  if (match) return leading + match[1] + " dari " + match[2] + " tahap memiliki data · " + match[3] + " data berada pada tahap alur kerja" + trailing;
  match = core.match(/^Show (\d+) empty stages$/);
  if (match) return leading + "Tampilkan " + match[1] + " tahap kosong" + trailing;
  match = core.match(/^Page (\d+) of (\d+) · (\d+) records$/);
  if (match) return leading + "Halaman " + match[1] + " dari " + match[2] + " · " + match[3] + " data" + trailing;
  match = core.match(/^Page (\d+) of (\d+) · (\d+) activities$/);
  if (match) return leading + "Halaman " + match[1] + " dari " + match[2] + " · " + match[3] + " aktivitas" + trailing;
  match = core.match(/^Page (\d+) of (\d+) · (\d+) contracts$/);
  if (match) return leading + "Halaman " + match[1] + " dari " + match[2] + " · " + match[3] + " kontrak" + trailing;
  match = core.match(/^Page (\d+) of (\d+) · (\d+) LP records$/);
  if (match) return leading + "Halaman " + match[1] + " dari " + match[2] + " · " + match[3] + " data LP" + trailing;
  match = core.match(/^Page (\d+) · (\d+) requests$/);
  if (match) return leading + "Halaman " + match[1] + " · " + match[2] + " permintaan" + trailing;
  match = core.match(/^Page (\d+) · (\d+) batches$/);
  if (match) return leading + "Halaman " + match[1] + " · " + match[2] + " batch" + trailing;
  match = core.match(/^Page (\d+) of (\d+)$/);
  if (match) return leading + "Halaman " + match[1] + " dari " + match[2] + trailing;
  match = core.match(/^(\d+) fully injected$/);
  if (match) return leading + match[1] + " sudah fully injected" + trailing;
  match = core.match(/^(\d+) record(s)? at this stage$/);
  if (match) return leading + match[1] + " data pada tahap ini" + trailing;
  match = core.match(/^(\d+) without a start date$/);
  if (match) return leading + match[1] + " tanpa tanggal mulai" + trailing;
  match = core.match(/^Workflow: (.+)$/);
  if (match) return leading + "Alur kerja: " + translateText(match[1], language) + trailing;
  match = core.match(/^Request failed \((\d+)\)$/);
  if (match) return leading + "Permintaan gagal (" + match[1] + ")" + trailing;
  return value;
}

function translateNode(node, language) {
  if (!originalTextNodes.has(node)) originalTextNodes.set(node, node.nodeValue);
  const original = originalTextNodes.get(node);
  const translated = translateText(original, language);
  if (node.nodeValue !== translated) node.nodeValue = translated;
}

function rememberAndTranslateAttribute(element, name, language) {
  let values = originalAttributes.get(element);
  if (!values) {
    values = new Map();
    originalAttributes.set(element, values);
  }
  if (!values.has(name)) values.set(name, element.getAttribute(name));
  const original = values.get(name);
  const translated = translateText(original, language);
  if (element.getAttribute(name) !== translated) element.setAttribute(name, translated);
}

function translateSubtree(root, language = currentLanguage) {
  if (!root) return;
  if (root.nodeType === Node.TEXT_NODE) {
    translateNode(root, language);
    return;
  }
  const attributes = ["placeholder", "aria-label", "aria-description", "title"];
  const elements = [];
  if (root.nodeType === Node.ELEMENT_NODE) elements.push(root);
  if (root.querySelectorAll) elements.push(...root.querySelectorAll("*"));
  elements.forEach((element) => {
    attributes.forEach((name) => {
      if (element.hasAttribute(name)) rememberAndTranslateAttribute(element, name, language);
    });
  });
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || parent.closest("script,style")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((node) => translateNode(node, language));
}

function setLanguage(language) {
  currentLanguage = language === "id" ? "id" : "en";
  try { localStorage.setItem("khs-dashboard-language", currentLanguage); } catch (_) {}
  document.documentElement.lang = currentLanguage;
  document.documentElement.dataset.language = currentLanguage;
  document.title = currentLanguage === "id" ? "Pemantauan & Pelacakan Kontrak" : "Contract Monitoring & Tracking";
  translateSubtree(document.body, currentLanguage);
  const button = $("languageToggle");
  if (button) {
    button.textContent = currentLanguage === "en" ? "ID" : "EN";
    button.setAttribute("aria-label", currentLanguage === "en" ? "Switch to Bahasa Indonesia" : "Switch to English");
    button.title = currentLanguage === "en" ? "Switch to Bahasa Indonesia" : "Switch to English";
  }
}

function initLanguageSwitcher() {
  try {
    const saved = localStorage.getItem("khs-dashboard-language");
    currentLanguage = saved === "id" ? "id" : "en";
  } catch (_) {
    currentLanguage = "en";
  }
  const button = $("languageToggle");
  if (button) {
    button.addEventListener("click", () => setLanguage(currentLanguage === "en" ? "id" : "en"));
  }
  if (!languageObserver && document.body) {
    languageObserver = new MutationObserver((records) => {
      if (currentLanguage !== "id") return;
      records.forEach((record) => {
        record.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE) {
            translateSubtree(node, currentLanguage);
          }
        });
      });
    });
    languageObserver.observe(document.body, { childList: true, subtree: true });
  }
  setLanguage(currentLanguage);
}

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
  workflowAgeBandFilter: null,
  workflowRoleFilter: null,
  workflowRows: [],
  showEmptyWorkflowStages: false,
  attentionOnly: false,
  workView: "active",
  workLpStageFilter: null
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
  ["action_owner", "Action owner / PIC", "text"],
  ["waiting_reason", "Waiting reason / next action", "textarea"],
  ["remarks", "Remarks", "textarea"]
];


const itemFieldGroups = [
  { id:"supplier-contract", title:"Supplier & contract", description:"The request, supplier, owner, and contract identity.", fields:["request_id","vendor_name","executor_code","subtype","dispatch_date","contract_start_date","contract_end_date"] },
  { id:"commercial-approvals", title:"Commercial & MI approvals", description:"Commercial checkpoints and approvals required before LP circulation.", fields:["boq_confirmation_date","negotiation_date","final_negotiation_date","mi_head_approval_date","mi_sm_approval_date","mi_gm_approval_date","legal_submission_date"] },
  { id:"lp-circulation", title:"LP Circulation", description:"Record each submission, completion, and approval date only when supported by evidence.", fields:["lp_circulation_start_date","lp_contract_team_completion_date","lp_junior_manager_approval_date","lp_senior_manager_approval_date","lp_gm_scm_approval_date","lp_completion_date"] },
  { id:"khs-injection", title:"KHS Injection", description:"This phase starts only after Director-signed LP completion.", fields:["khs_inject_start_date","khs_inject_completion_date"] },
  { id:"coordination", title:"Coordination & next action", description:"Who currently holds the action, why it is waiting, and contextual notes.", fields:["waiting_for","action_owner","waiting_reason","remarks"] }
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

function currentStageLabel(record) {
  if (record.current_stage_code === "LP_CIRCULATION") {
    return record.lp_stage_label || record.current_stage_name || "LP Circulation";
  }
  return record.current_stage_name || record.current_stage_code || "—";
}

function currentStageAgeLabel(record) {
  const age = record.current_stage_age_days;
  if (record.current_stage_age_status === "history_inconsistent") return "History needs review";
  if (record.process_status === "NOT_PROCEEDED") {
    return age == null ? "Closed · duration unavailable" : "Stopped after " + age + " days";
  }
  if (age === null || age === undefined || !Number.isFinite(Number(age))) {
    if (record.current_stage_code === "COMPLETED") return "Closed stage";
    if (record.current_stage_code === "LP_CIRCULATION" && (
      record.lp_timeline_has_gaps ||
      record.lp_prerequisite_exception ||
      record.lp_legacy_unverified
    )) return "History needs review";
    return "Stage age unavailable";
  }
  const days = Number(age);
  return days + (days === 1 ? " day in stage" : " days in stage");
}

function currentStageAgeMeta(record) {
  if (record.current_stage_started_on && record.current_stage_age_days !== null &&
      record.current_stage_age_days !== undefined) {
    return "Since " + fmt(record.current_stage_started_on);
  }
  return "Updated " + fmt(record.last_updated_date || record.updated_at);
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
  // Preserve legacy #lp links, but route them into the LP saved view in Work Queue.
  if (page === "lp") {
    state.workView = "lp";
    page = "register";
  }
  const allowed = ["overview", "requests", "register", "contracts", "workflow", "imports", "activity"];
  if (allowed.indexOf(page) < 0) return;
  state.page = page;
  document.querySelectorAll(".page-view").forEach((el) => {
    el.classList.toggle("active", el.id === "page-" + page);
  });
  document.querySelectorAll(".nav-link[data-page]").forEach((el) => {
    const isActive = page === "register"
      ? (state.workView === "lp" ? el.dataset.page === "lp" : el.dataset.page === "register")
      : el.dataset.page === page;
    el.classList.toggle("active", isActive);
    if (isActive) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  const active = $("page-" + page);
  const title = page === "register" && state.workView === "lp"
    ? "LP Circulation" : (active ? active.dataset.title : page);
  set("breadcrumbCurrent", title);
  syncRefreshVisibility(page);
  closeMobileNavigation();
  const hash = page === "register" && state.workView === "lp" ? "#lp" : "#" + page;
  if (window.location.hash !== hash) history.replaceState(null, "", hash);
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
    set("notProceededKhs", d.not_proceeded_khs || 0);
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
    emptyRow("attentionBody", 7, "No records currently require attention.");
    return;
  }
  body.innerHTML = rows.map((r) => {
    const stage = currentStageLabel(r);
    const age = currentStageAgeLabel(r);
    const ageMeta = currentStageAgeMeta(r);
    const exception = r.lp_started_without_mi_gm_approval
      ? '<span class="exception-label">MI GM prerequisite exception</span>' : "";
    const actionOwner = r.action_owner || "Unassigned";
    const waitingFor = r.waiting_for || "No waiting party recorded";
    return `<tr>
      <td data-label="REQUEST / KHS"><span class="cell-primary">${esc(r.request_subject || "Untitled request")}</span>
      <span class="cell-secondary">${esc(r.khs_id)} · ${esc(r.request_id)}</span></td>
      <td data-label="VENDOR">${esc(r.vendor_name)}</td>
      <td data-label="CURRENT STAGE">${esc(stage)}${exception}</td>
      <td data-label="ACTION OWNER"><span class="cell-primary">${esc(actionOwner)}</span></td>
      <td data-label="WAITING ON / CONTEXT"><span class="cell-primary">${esc(waitingFor)}</span>
      ${r.waiting_reason ? '<span class="cell-secondary">' + esc(r.waiting_reason) + "</span>" : ""}</td>
      <td data-label="STAGE AGE / UPDATED"><span class="cell-primary">${esc(age)}</span>
      <span class="cell-secondary">${esc(ageMeta)}</span></td>
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
  ["searchInput", "statusFilter", "executorFilter", "subtypeFilter", "waitingFilter", "stageFilter", "processStatusFilter"]
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
    ["stageFilter", "Workflow stage"],
    ["processStatusFilter", "Process status"]
  ];
  controls.forEach(([id, label]) => {
    const control = $(id);
    if (!control || !control.value) return;
    const option = control.tagName === "SELECT" ? control.options[control.selectedIndex] : null;
    const value = option ? option.textContent : control.value;
    filters.push({id, label, value});
  });
  if (state.workflowStageFilter) filters.push({id:"workflowStageFilter",label:"Stage",value:state.workflowStageFilter.replace(/_/g," ")});
  if (state.workflowAgeBandFilter) filters.push({
    id:"workflowAgeBandFilter",
    label:"WIP age",
    value:({
      "0_7":"0–7 days","8_14":"8–14 days","15_30":"15–30 days",
      "31_plus":"31+ days","unavailable":"Age unavailable"
    })[state.workflowAgeBandFilter] || state.workflowAgeBandFilter
  });
  if (state.workflowRoleFilter) filters.push({id:"workflowRoleFilter",label:"Approval role",value:state.workflowRoleFilter.replace(/_/g," ")});
  if (state.attentionOnly) filters.push({id:"attentionOnly",label:"Queue",value:"Needs attention"});
  const workViewLabels = {
    all: "All KHS",
    active: "Active WIP",
    attention: "Waiting / Attention",
    lp: "LP Circulation",
    exceptions: "Data Exceptions",
    unassigned: "Unassigned PIC"
  };
  if (state.workView && state.workView !== "all") {
    filters.push({id:"workView",label:"Saved view",value:workViewLabels[state.workView] || state.workView});
  }
  if (state.workView === "lp" && state.workLpStageFilter) {
    filters.push({id:"workLpStageFilter",label:"LP stage",value:state.workLpStageFilter.replace(/_/g," ")});
  }
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
    state.workflowAgeBandFilter = null;
    state.workflowRoleFilter = null;
    state.attentionOnly = false;
    state.workView = "active";
    state.workLpStageFilter = null;
  } else if (id === "workflowStageFilter") {
    state.workflowStageFilter = null;
  } else if (id === "workflowAgeBandFilter") {
    state.workflowAgeBandFilter = null;
  } else if (id === "workflowRoleFilter") {
    state.workflowRoleFilter = null;
  } else if (id === "attentionOnly") {
    state.attentionOnly = false;
  } else if (id === "workView") {
    state.workView = "active";
    state.workLpStageFilter = null;
  } else if (id === "workLpStageFilter") {
    state.workLpStageFilter = null;
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
  p.set("work_view", state.workView || "active");
  [["q","searchInput"],["lp_status","statusFilter"],["executor_code","executorFilter"],
   ["subtype","subtypeFilter"],["waiting_for","waitingFilter"],["process_status","processStatusFilter"]].forEach((pair) => {
    const el = $(pair[1]);
    if (el && el.value) p.set(pair[0], el.value);
  });
  if (state.workflowStageFilter) p.set("stage", state.workflowStageFilter);
  else if ($("stageFilter") && $("stageFilter").value) p.set("stage", $("stageFilter").value);
  if (state.workflowAgeBandFilter) p.set("age_band", state.workflowAgeBandFilter);
  if (state.workflowRoleFilter) p.set("waiting_role", state.workflowRoleFilter);
  if (state.workView === "lp" && state.workLpStageFilter) p.set("lp_stage", state.workLpStageFilter);
  if (state.attentionOnly) p.set("attention", "true");
  return p.toString();
}

async function loadRegister() {
  const result = await api("/api/dashboard/khs?" + registerQuery());
  const body = $("registerBody");
  if (!body) return;

  document.querySelectorAll("[data-work-queue-view]").forEach((button) => {
    const selected = button.dataset.workQueueView === state.workView;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  const lpStageWrap = $("lpWorkStageFilterWrap");
  if (lpStageWrap) lpStageWrap.hidden = state.workView !== "lp";
  const lpStageSelect = $("lpWorkStageFilter");
  if (lpStageSelect) lpStageSelect.value = state.workLpStageFilter || "";

  if (!result.data.length) emptyRow("registerBody", 7, "No KHS records match the current filters.");
  else body.innerHTML = result.data.map((r) => {
    const stage = currentStageLabel(r);
    const stageAge = currentStageAgeLabel(r);
    const lpStatus = String(r.lp_status || "not_started").replace(/_/g, " ");
    const injection = r.process_status === "NOT_PROCEEDED"
      ? '<span class="status-badge status-not_proceeded">Not Proceeded</span><span class="cell-secondary">' + esc(fmt(r.closure_date)) + '</span>'
      : r.khs_inject_completion_date
      ? '<span class="status-badge status-completed">Fully injected</span><span class="cell-secondary">' + esc(fmt(r.khs_inject_completion_date)) + "</span>"
      : r.khs_inject_start_date
        ? '<span class="status-badge status-in_progress">Injection started</span><span class="cell-secondary">' + esc(fmt(r.khs_inject_start_date)) + "</span>"
        : '<span class="status-badge status-neutral">Not started</span>';
    const lpBadge = '<span class="status-badge status-' + esc(r.lp_status || "not_started") + '">' + esc(lpStatus) + '</span>';
    const exception = r.lp_prerequisite_exception || r.lp_started_without_mi_gm_approval
      ? '<span class="exception-label">MI GM prerequisite review</span>'
      : r.lp_legacy_unverified
        ? '<span class="exception-label">Director sign-off unverified</span>'
        : r.lp_timeline_has_gaps || r.milestone_chronology_valid === false
          ? '<span class="exception-label">Historical timeline needs review</span>' : "";
    const requiresAction = r.process_status === "ACTIVE" && r.workflow_status !== "completed";
    const actionOwner = requiresAction ? (r.action_owner || "") : "";
    const ownerMarkup = requiresAction && !actionOwner
      ? '<span class="status-badge status-warning">Unassigned</span>'
      : '<span class="cell-primary">' + esc(actionOwner || "—") + '</span>';
    const waitingOn = r.waiting_for
      ? '<span class="cell-primary">' + esc(r.waiting_for) + '</span>'
      : '<span class="cell-secondary">No waiting party recorded</span>';
    const guidedLabel = r.guided_progress && r.guided_progress.label
      ? r.guided_progress.label : "";
    const nextAction = r.waiting_reason
      ? r.waiting_reason
      : guidedLabel
        ? "Complete: " + guidedLabel
        : r.milestone_chronology_valid === false
          ? "Review milestone history"
          : r.workflow_status === "completed"
            ? "Process completed"
            : r.process_status === "NOT_PROCEEDED"
              ? "Not Proceeded"
              : "No next action recorded";
    const nextMeta = guidedLabel && r.waiting_reason
      ? "Next milestone: " + guidedLabel
      : r.process_status === "NOT_PROCEEDED"
        ? "Closed " + fmt(r.closure_date)
        : "";
    const progressMarkup = lpBadge + '<span class="cell-secondary">' + injection + '</span>';
    return "<tr>" +
      '<td><span class="cell-primary">' + esc(r.request_subject || "Untitled request") + '</span>' +
      '<span class="cell-secondary">' + esc(r.vendor_name) + " · " + esc(r.khs_id) + '</span>' +
      '<span class="cell-tertiary">' + esc(r.executor_name || r.executor_code || "Unassigned") + "</span></td>" +
      '<td><span class="cell-primary">' + esc(stage) + '</span>' +
      '<span class="cell-secondary">' + esc(stageAge) + "</span>" + exception + "</td>" +
      "<td>" + ownerMarkup + "</td>" +
      "<td>" + waitingOn + "</td>" +
      '<td><span class="cell-primary">' + esc(nextAction) + '</span>' +
      (nextMeta ? '<span class="cell-secondary">' + esc(nextMeta) + "</span>" : "") + "</td>" +
      "<td>" + progressMarkup + "</td>" +
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

function renderWorkflowCards() {
  const wrap = $("workflowCards");
  if (!wrap) return;
  const rows = state.workflowRows || [];
  const occupied = rows.filter((row) => Number(row.total) > 0);
  const empty = rows.filter((row) => Number(row.total) === 0);
  const visibleRows = state.showEmptyWorkflowStages ? rows : occupied;
  const totalRecords = occupied.reduce((sum, row) => sum + Number(row.total || 0), 0);
  set(
    "workflowStageSummary",
    occupied.length + " of " + rows.length + " stages have records · " +
      totalRecords + " records assigned to a workflow stage"
  );

  const toggle = $("workflowEmptyToggle");
  if (toggle) {
    toggle.hidden = empty.length === 0;
    toggle.textContent = state.showEmptyWorkflowStages
      ? "Hide empty stages"
      : "Show " + empty.length + " empty stages";
    toggle.setAttribute("aria-expanded", String(state.showEmptyWorkflowStages));
  }

  wrap.innerHTML = visibleRows.length ? visibleRows.map((row) => {
    const isFullyInjected = /fully injected/i.test(row.stage_name || "");
    const detail = isFullyInjected
      ? Number(row.completed || 0) + " fully injected"
      : Number(row.total || 0) + " record" + (Number(row.total) === 1 ? "" : "s") + " at this stage";
    const age = isFullyInjected
      ? "Closed stage"
      : row.oldest_stage_age_days == null
        ? "Stage age unavailable"
        : "Oldest in stage: " + Number(row.oldest_stage_age_days) +
          (Number(row.oldest_stage_age_days) === 1 ? " day" : " days");
    const unavailable = !isFullyInjected && Number(row.stage_age_unavailable || 0) > 0
      ? " · " + Number(row.stage_age_unavailable) + " without a start date"
      : "";
    return '<button type="button" class="workflow-stage" data-workflow-stage="' + esc(row.stage_code) +
      '" aria-label="Open ' + esc(row.stage_name) + ', ' + esc(detail) + ', ' + esc(age) + unavailable + '">' +
      '<span class="workflow-stage-top"><span>' + esc(row.stage_name) + '</span><strong>' +
      esc(row.total) + "</strong></span>" +
      '<span class="workflow-stage-bottom"><span class="workflow-stage-count">' + esc(detail) +
      '</span><span class="workflow-stage-age">' + esc(age + unavailable) + '</span>' +
      '<span class="workflow-stage-action">Open records →</span></span>' +
      "</button>";
  }).join("") : '<div class="empty-state">No workflow stages currently contain records.</div>';
}


function slaStatusLabel(status) {
  return ({
    not_configured: "Not configured",
    age_unavailable: "Age unavailable",
    on_track: "On track",
    due_soon: "Due soon",
    overdue: "Overdue",
    escalation_due: "Escalation due"
  })[status] || status || "—";
}

function renderOperationsAnalytics(operations, followUps, sla) {
  const followUpRows = followUps && Array.isArray(followUps.data) ? followUps.data : null;
  const followUpsOverdue = followUpRows
    ? followUpRows.filter((row) => row.status === "OPEN" && !row.stage_changed && Number(row.days_from_due) > 0).length
    : "—";
  const slaData = sla && sla.data ? sla.data : null;
  const slaSummary = slaData ? (slaData.summary || {}) : {};
  const slaByStage = new Map((slaData && Array.isArray(slaData.stages) ? slaData.stages : [])
    .map((row) => [row.stage_code, row]));
  if (!operations || !operations.data) {
    ["opsActiveWip","opsOver30","opsAgeUnavailable"].forEach((id) => set(id, "—"));
    set("opsSlaOverdue", slaData ? (slaSummary.sla_overdue_records || 0) : "—");
    set("opsEscalations", slaData ? (slaSummary.escalation_records || 0) : "—");
    set("opsFollowUpsOverdue", followUpsOverdue);
    emptyRow("operationsStageBody", 13, "WIP analytics are temporarily unavailable.");
    renderOperationsFollowUps(followUpRows);
    return;
  }
  const summary = operations.data.summary || {};
  set("operationsAsOf", "As of " + fmt(operations.as_of_date));
  set("opsActiveWip", summary.active_wip || 0);
  set("opsOver30", summary.older_than_30_days || 0);
  set("opsAgeUnavailable", summary.stage_age_unavailable || 0);
  set("opsSlaOverdue", slaData ? (slaSummary.sla_overdue_records || 0) : "—");
  set("opsEscalations", slaData ? (slaSummary.escalation_records || 0) : "—");
  set("opsFollowUpsOverdue", followUpsOverdue);
  const configured = slaData ? (slaData.stages || []).filter((row) => row.sla_configured).length : 0;
  set("slaConfigurationStatus", !slaData ? "SLA data unavailable"
    : configured ? configured + " stages configured" : "SLA not configured");
  const target = $("operationsStageBody");
  const rows = operations.data.stages || [];
  if (target) target.innerHTML = rows.length ? rows.map((row) => {
    const slaRow = slaByStage.get(row.stage_code);
    const status = slaRow ? (slaRow.sla_status || "not_configured") : "age_unavailable";
    const policy = !slaData ? "SLA policy data unavailable"
      : !slaRow || slaRow.target_days == null ? "No target configured"
      : "Target " + slaRow.target_days + "d" +
        (slaRow.warning_after_days == null ? "" : " · warn " + slaRow.warning_after_days + "d") +
        (slaRow.escalation_after_days == null ? "" : " · escalate " + slaRow.escalation_after_days + "d");
    const stageButton = '<button type="button" class="analytics-filter analytics-stage-filter" data-operations-stage="' +
      esc(row.stage_code) + '" aria-label="Filter KHS by ' + esc(row.stage_name) + '">' +
      (row.bottleneck_rank ? '<span class="bottleneck-rank">#' + esc(row.bottleneck_rank) + '</span> ' : '') +
      esc(row.stage_name) + '</button>';
    const ageButton = (band, count, label) =>
      '<button type="button" class="analytics-filter" data-operations-stage="' + esc(row.stage_code) +
      '" data-operations-age-band="' + esc(band) + '" aria-label="Filter ' + esc(row.stage_name) +
      ', ' + esc(label) + ', ' + esc(count) + ' records">' + esc(count) + '</button>';
    return '<tr><td>' + stageButton + '<span class="cell-secondary">' +
      esc(policy) + '</span></td><td><button type="button" class="analytics-filter analytics-total-filter" data-operations-stage="' +
      esc(row.stage_code) + '">' + esc(row.wip_count) + '</button></td>' +
      '<td>' + esc(row.median_age_days == null ? "—" : row.median_age_days + "d") + '</td>' +
      '<td>' + esc(row.p90_age_days == null ? "—" : row.p90_age_days + "d") + '</td>' +
      '<td>' + ageButton("0_7", row.age_0_7, "0–7 days") + '</td>' +
      '<td>' + ageButton("8_14", row.age_8_14, "8–14 days") + '</td>' +
      '<td>' + ageButton("15_30", row.age_15_30, "15–30 days") + '</td>' +
      '<td>' + ageButton("31_plus", row.age_over_30, "31+ days") + '</td>' +
      '<td>' + ageButton("unavailable", row.age_unavailable, "age unavailable") + '</td>' +
      '<td>' + esc(row.oldest_age_days == null ? "—" : row.oldest_age_days + "d") + '</td>' +
      '<td><span class="status-badge status-sla-' + esc(status) + '">' + esc(slaStatusLabel(status)) + '</span></td>' +
      '<td>' + esc(slaRow ? (slaRow.overdue_count || 0) : "—") + '</td><td>' +
      esc(slaRow ? (slaRow.escalation_count || 0) : "—") + '</td></tr>';
  }).join("") : '<tr><td colspan="12" class="table-message">No active WIP records.</td></tr>';
  renderOperationsFollowUps(followUpRows);
}

function renderOperationsFollowUps(rows) {
  const body = $("operationsFollowUpBody");
  if (!body) return;
  if (!Array.isArray(rows)) {
    emptyRow("operationsFollowUpBody", 7, "Follow-up inbox unavailable. WIP analytics remain available.");
    return;
  }
  if (!rows.length) {
    emptyRow("operationsFollowUpBody", 7, "No open follow-ups are scheduled.");
    return;
  }
  const actionable = rows.filter((row) => row.status === "OPEN" && !row.stage_changed);
  body.innerHTML = actionable.length ? actionable.map((row) => {
    const dueState = Number(row.days_from_due) > 0 ? "Overdue"
      : Number(row.days_from_due) === 0 ? "Due today" : "Upcoming";
    return '<tr><td><strong>' + esc(fmt(row.due_date)) + '</strong><span class="cell-secondary">' +
      esc(dueState) + '</span></td><td><strong>' + esc(row.khs_id) + '</strong><span class="cell-secondary">' +
      esc(row.vendor_name || "—") + '</span></td><td>' + esc(row.stage_name || row.stage_code) +
      '</td><td>' + esc(row.follow_up_to || row.action_owner || "Unassigned") + '</td><td>' +
      esc(row.note) + '</td><td><span class="status-badge ' +
      (Number(row.days_from_due) > 0 ? "status-warning" : "status-in_progress") + '">' +
      esc(dueState) + '</span></td><td><button type="button" class="view-button" data-complete-followup="' +
      esc(row.id) + '">Complete</button> <button type="button" class="view-button" data-view-khs="' +
      esc(row.khs_id) + '">Open KHS</button></td></tr>';
  }).join("") : '<tr><td colspan="7" class="table-message">No current-stage follow-ups. Stage-moved reminders remain in record history.</td></tr>';
}

async function loadWorkflow() {
  const [workflow, operations] = await Promise.all([
    api("/api/dashboard/workflow"),
    api("/api/dashboard/operations/overview")
  ]);
  // Phase 4 SLA and follow-up services are optional overlays. Their failure
  // must never block the Phase 1 workflow and WIP-aging view.
  const [sla, followUps] = await Promise.all([
    api("/api/dashboard/operations/sla-overview").catch(() => null),
    api("/api/dashboard/operations/follow-ups?status=OPEN").catch(() => null)
  ]);
  state.workflowRows = workflow.data || [];
  state.showEmptyWorkflowStages = false;
  renderWorkflowCards();
  renderOperationsAnalytics(operations, followUps, sla);
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
      const stopped = r.process_status === "NOT_PROCEEDED";
      const ageDays = stopped ? r.current_stage_age_days : r.lp_stage_age_days;
      const age = ageDays == null ? "—" : (stopped ? "Stopped after " : "") + ageDays + " days";
      const history = stopped
        ? '<span class="status-badge status-not_proceeded">Not Proceeded</span>'
        : r.lp_timeline_has_gaps
        ? '<span class="status-badge status-warning">Partial history</span>'
        : '<span class="status-badge status-completed">Recorded</span>';
      const prerequisiteFlag = r.lp_prerequisite_exception
        ? '<span class="exception-label">MI GM prerequisite exception</span>' : "";
      const legacyFlag = r.lp_legacy_unverified
        ? '<span class="exception-label">Legacy Director sign-off unverified</span>' : "";
      return "<tr><td><span class=\"cell-primary\">" + esc(r.khs_id) + "</span>" +
        "<span class=\"cell-secondary\">" + esc(r.vendor_name) + "</span>" +
        (stopped ? '<span class="exception-label">Closed ' + esc(fmt(r.closure_date)) + '</span>' : "") +
        "</td>" +
        "<td><span class=\"cell-primary\">" + esc(r.request_subject || "Untitled request") + "</span>" +
        "<span class=\"cell-secondary\">" + esc(r.request_id) + "</span></td>" +
        "<td><span class=\"cell-primary\">" + esc(stopped ? "Not Proceeded" : (r.lp_stage_label || "—")) + "</span>" +
        (stopped ? '<span class="cell-secondary">' + esc(String(r.closure_reason_code || "").replace(/_/g, " ")) + '</span>' : prerequisiteFlag + legacyFlag +
        (r.waiting_for ? "<span class=\"cell-secondary\">Waiting for " + esc(r.waiting_for) + "</span>" : "")) + "</td>" +
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
  const chronologyInvalid = record.milestone_chronology_valid === false;
  const completed = record.lp_stage_key === "completed";
  const notStarted = record.lp_stage_key === "not_started";
  const processStopped = record.process_status === "NOT_PROCEEDED";
  const reviewRequired = chronologyInvalid || prerequisiteException || legacyUnverified || hasGaps;
  const lastRecordedIndex = stages.reduce((last, stage, index) => record[stage[0]] ? index : last, -1);

  let currentTitle = "Review required";
  let currentMeta = "The available milestone history does not support a reliable active-stage assignment.";
  let upcomingTitle = "After verification";
  let upcomingMeta = "No next approval stage has been inferred.";
  let ageTitle = "Not calculated";
  let ageMeta = "Stage age is withheld until the current stage can be established.";

  if (chronologyInvalid && lastRecordedIndex >= 1) {
    currentTitle = "History needs review";
    currentMeta = "Recorded milestone dates are not chronologically consistent. Verify the source history before assigning the next LP approver.";
    upcomingTitle = "Review source dates";
    upcomingMeta = "No next LP approver is inferred from inconsistent chronology.";
    ageTitle = "Unavailable";
    ageMeta = "Stage age is withheld until the recorded milestone order is verified.";
  } else if (currentIndex >= 1 && !reviewRequired) {
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

  if (processStopped) {
    if (completed) {
      currentTitle = "LP completed";
      currentMeta = "Director sign-off recorded on " + fmt(record.lp_completion_date) +
        "; the KHS process was later closed on " + fmt(record.closure_date) + ".";
      upcomingTitle = "KHS process stopped";
      upcomingMeta = "No fully-injected completion was recorded.";
      ageTitle = "—";
      ageMeta = "LP had no active stage. See Process Duration History for the later stoppage.";
    } else if (currentIndex >= 1) {
      currentTitle = "Not Proceeded";
      currentMeta = "The LP route stopped at " + stages[currentIndex][1] +
        " when the KHS was closed on " + fmt(record.closure_date) + ".";
      upcomingTitle = "No further LP milestone";
      upcomingMeta = "The approval route stopped when the KHS was closed.";
      const stoppedAge = record.current_stage_age_days;
      ageTitle = stoppedAge == null ? "Unavailable" : stoppedAge + (Number(stoppedAge) === 1 ? " day" : " days");
      ageMeta = "Stopped on " + fmt(record.closure_date);
    } else {
      currentTitle = "LP not reached";
      currentMeta = "The KHS process closed before LP Circulation began.";
      upcomingTitle = "No further LP milestone";
      upcomingMeta = "The LP approval route was not started.";
      ageTitle = "—";
      ageMeta = "No LP stage was opened.";
    }
  }

  const badge = $("lpTimelineStage");
  if (badge) {
    badge.className = "status-badge " + (processStopped ? "status-not_proceeded" :
      completed ? "status-completed" :
      currentIndex >= 1 && !reviewRequired ? "status-in_progress" :
      notStarted ? "status-not_started" : "status-missing");
    badge.textContent = processStopped ? "Not Proceeded" : completed ? "LP completed" :
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
    } else if (processStopped && index === currentIndex) {
      stateClass = "stopped";
      stateLabel = "Stopped";
      timeLabel = "Process closed on " + fmt(record.closure_date);
    } else if (processStopped) {
      stateClass = "not-reached";
      stateLabel = "Not reached";
      timeLabel = "Process stopped before this milestone";
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
    const noticeText = chronologyInvalid
      ? "Recorded milestone dates are not chronologically consistent. Verify the source dates before interpreting the LP sequence or assigning the next approver."
      : prerequisiteException
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



function renderWorkSummary(record) {
  const closed = record.process_status === "NOT_PROCEEDED";
  const completed = !!record.khs_inject_completion_date;
  const stage = closed
    ? (record.current_stage_name || "Not Proceeded")
    : currentStageLabel(record);
  const stageAge = closed
    ? currentStageAgeLabel(record)
    : completed
      ? "KHS fully injected " + fmt(record.khs_inject_completion_date)
      : currentStageAgeLabel(record);
  set("workSummaryStage", stage || "—");
  set("workSummaryStageAge", stageAge || "Date unavailable");
  set("workSummaryOwner", record.action_owner || "No action owner assigned");
  set("workSummaryOwnerMeta", record.action_owner
    ? "Responsible for coordinating the next action"
    : "Assign an action owner in Edit record or when scheduling a follow-up");
  set("workSummaryWaitingFor", record.waiting_for || "No waiting party recorded");
  set("workSummaryWaitingReason", record.waiting_reason || "No waiting reason recorded");

  let next = "No next milestone inferred";
  let nextMeta = "Review the recorded history before assigning another action.";
  if (record.guided_progress) {
    next = record.guided_progress.label;
    nextMeta = "Next milestone in the recorded workflow sequence";
  } else if (closed) {
    next = "Process stopped";
    nextMeta = "Closed " + fmt(record.closure_date);
  } else if (completed) {
    next = "KHS fully injected";
    nextMeta = "Contract lifecycle monitoring is now the next control";
  }
  set("workSummaryNextMilestone", next);
  set("workSummaryNextMeta", nextMeta);

  const stateBadge = $("workSummaryState");
  if (stateBadge) {
    stateBadge.className = "status-badge " + (
      closed ? "status-not_proceeded" :
      completed ? "status-completed" :
      "status-in_progress"
    );
    stateBadge.textContent = closed ? "Not Proceeded" :
      completed ? "Fully Injected" : "Active";
  }
  const notices = [];
  if (record.lp_prerequisite_exception) {
    notices.push("LP circulation has an MI GM prerequisite exception. Verify the approval evidence before treating the route as valid.");
  }
  if (record.lp_legacy_unverified) {
    notices.push("Legacy Director sign-off is unverified. A legacy completion label is not proof of a signed LP.");
  }
  if (record.lp_timeline_has_gaps) {
    notices.push("The LP history has missing milestone dates. The next approver is not inferred from incomplete history.");
  }
  if (record.milestone_chronology_valid === false) {
    notices.push("Recorded milestone dates are not chronologically consistent. Guided progress is disabled and process-duration totals are withheld until the source dates are reviewed.");
  }
  const notice = $("workSummaryNotice");
  if (notice) {
    notice.hidden = notices.length === 0;
    notice.textContent = notices.join(" ");
  }
}

function durationDaysLabel(value) {
  const days = Number(value);
  return days + (days === 1 ? " day" : " days");
}

function renderWorkbenchFollowUps(rows) {
  const list = $("followUpList");
  if (!list) return;
  if (!rows || !rows.length) {
    list.innerHTML = '<p class="muted">No follow-ups have been scheduled for this KHS.</p>';
    return;
  }
  list.innerHTML = rows.map((row) => {
    const open = row.status === "OPEN";
    const stale = open && !!row.stage_changed;
    const dueState = row.due_state || (
      row.days_from_due == null ? "date_unavailable" :
      Number(row.days_from_due) > 0 ? "overdue" :
      Number(row.days_from_due) === 0 ? "due_today" : "upcoming"
    );
    const dueLabels = {
      overdue: "Overdue", due_today: "Due today",
      upcoming: "Upcoming", date_unavailable: "Date unavailable"
    };
    const statusLabel = stale ? "Stage changed · review" :
      open ? (dueLabels[dueState] || "Open") :
      String(row.status || "Closed").replace(/_/g, " ").toLowerCase();
    const badgeClass = stale || dueState === "overdue"
      ? "status-warning" : open ? "status-in_progress" : "status-neutral";
    const stageLabel = row.stage_name || row.stage_code || "Unknown stage";
    return '<article class="follow-up-item ' + (open ? "follow-up-open" : "follow-up-closed") + '">' +
      '<div class="follow-up-item-main"><div class="follow-up-item-title"><strong>' +
      esc(fmt(row.due_date)) + ' · ' + esc(row.follow_up_to || "Unassigned") +
      '</strong><span class="status-badge ' + badgeClass + '">' + esc(statusLabel) + '</span></div>' +
      '<p>' + esc(row.note) + '</p><small>' + esc(stageLabel) + '</small></div>' +
      (open ? '<div class="follow-up-item-actions">' +
        (!stale ? '<button type="button" class="view-button" data-complete-followup="' +
          esc(row.id) + '">Complete</button>' : "") +
        '<button type="button" class="view-button" data-cancel-followup="' +
        esc(row.id) + '">Cancel</button></div>' : "") +
      '</article>';
  }).join("");
}

function refreshGuidedProgressControl(record) {
  const button = $("updateProgressButton");
  const definition = record.guided_progress;
  if (button) {
    button.hidden = !definition;
    button.textContent = definition ? "Update: " + definition.label : "No pending milestone";
  }
  const schedule = $("scheduleFollowUpButton");
  const followUpAllowed = record.process_status === "ACTIVE" &&
    record.workflow_status !== "completed";
  if (schedule) schedule.hidden = !followUpAllowed;
  const composer = $("followUpComposer");
  const readOnlyNotice = $("followUpReadOnlyNotice");
  if (composer) composer.hidden = !followUpAllowed;
  if (readOnlyNotice) readOnlyNotice.hidden = followUpAllowed;
  const stage = record.lp_stage_key === "contract_team" ? "LP Contract Team" :
    record.lp_stage_key === "junior_manager" ? "LP Junior Manager Vendor Management" :
    record.lp_stage_key === "senior_manager" ? "LP Senior Manager Strategic Sourcing" :
    record.lp_stage_key === "general_manager" ? "LP GM SCM" :
    record.lp_stage_key === "director" ? "LP Director Sign-off" :
    (record.current_stage_name || record.current_stage_code || "No active stage");
  set("followUpCurrentStage", stage);
  set("progressKhsLabel", record.khs_id);
  const milestoneInput = $("progressMilestoneLabel");
  if (milestoneInput) {
    milestoneInput.value = translateText(
      definition ? definition.label : "No guided milestone available",
      currentLanguage
    );
  }
  if ($("followUpTo")) $("followUpTo").value = record.action_owner || "";
}

function openGuidedProgressDialog() {
  const record = state.detail;
  if (!record || !record.guided_progress) return;
  $("progressKhsLabel").textContent = record.khs_id;
  $("progressMilestoneLabel").value = translateText(record.guided_progress.label, currentLanguage);
  $("progressMilestoneDate").value = localDateInputValue();
  $("progressNote").value = "";
  $("progressError").hidden = true;
  $("progressDialog").showModal();
}

async function submitGuidedProgress(event) {
  event.preventDefault();
  const record = state.detail;
  if (!record || !record.guided_progress) return;
  const button = $("confirmProgress");
  const error = $("progressError");
  const data = Object.fromEntries(new FormData($("progressForm")).entries());
  if (error) { error.hidden = true; error.textContent = ""; }
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    await api("/api/dashboard/khs/" + encodeURIComponent(record.khs_id) + "/progress",
      jsonOptions("POST", data));
    $("progressDialog").close();
    toast("Progress updated.", true);
    await Promise.all([loadOverview(), loadRegisterIfReady()]);
    if (state.page === "workflow") await loadWorkflow();
    if (state.page === "lp") await loadLPCirculation();
    await openDetails(record.khs_id);
  } catch (err) {
    if (error) { error.textContent = err.message; error.hidden = false; }
    toast(err.message);
  } finally {
    button.disabled = false;
    button.textContent = "Save progress";
  }
}

async function submitWorkbenchFollowUp(event) {
  event.preventDefault();
  const record = state.detail;
  if (!record) return;
  const button = $("saveFollowUpButton");
  const data = Object.fromEntries(new FormData($("followUpForm")).entries());
  button.disabled = true;
  button.textContent = "Scheduling…";
  try {
    await api("/api/dashboard/khs/" + encodeURIComponent(record.khs_id) + "/follow-ups",
      jsonOptions("POST", data));
    toast("Follow-up scheduled.", true);
    const fresh = await api("/api/dashboard/khs/" + encodeURIComponent(record.khs_id));
    state.detail = fresh.data;
    renderWorkbenchFollowUps(fresh.follow_ups || []);
    refreshGuidedProgressControl(fresh.data);
    renderWorkSummary(fresh.data);
    if (state.page === "workflow") await loadWorkflow();
  } catch (err) {
    toast(err.message);
  } finally {
    button.disabled = false;
    button.textContent = "Schedule follow-up";
  }
}

async function updateFollowUpStatus(id, action) {
  try {
    const result = await api("/api/dashboard/operations/follow-ups/" + encodeURIComponent(id) + "/" + action,
      jsonOptions("POST", {}));
    toast(action === "complete" ? "Follow-up completed." : "Follow-up cancelled.", true);
    if (state.page === "workflow") await loadWorkflow();
    if (state.detail && result.data && result.data.khs_id === state.detail.khs_id) {
      const fresh = await api("/api/dashboard/khs/" + encodeURIComponent(state.detail.khs_id));
      state.detail = fresh.data;
      renderWorkbenchFollowUps(fresh.follow_ups || []);
      refreshGuidedProgressControl(fresh.data);
      renderWorkSummary(fresh.data);
    }
  } catch (err) {
    toast(err.message);
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


function renderProcessDurationHistory(record) {
  const stages = record.process_duration_history || [];
  const labels = {
    completed: "Completed",
    in_progress: "In progress",
    stopped: "Stopped",
    history_incomplete: "History incomplete",
    date_unavailable: "Date unavailable",
    invalid_chronology: "Data needs review",
    not_started: "Not started"
  };
  const days = record.total_processing_duration_days;
  const lpDays = record.lp_circulation_duration_days;
  set("totalProcessingDays", days == null ? "Unavailable" : durationDaysLabel(days));
  set("lpProcessingDays", lpDays == null ? "Unavailable" : durationDaysLabel(lpDays));
  const chronologyInvalid = record.milestone_chronology_valid === false;
  const invalidStages = stages.filter((stage) => stage.status === "invalid_chronology");
  const durationNotices = [];
  if (chronologyInvalid) {
    durationNotices.push("Recorded milestone dates are not chronologically consistent. Overall and LP durations are withheld until the source dates are reviewed.");
  }
  if (invalidStages.length) {
    durationNotices.push(
      "Chronology needs review in: " + invalidStages.map((stage) => stage.stage_label).join(", ") +
      ". Durations are not estimated for these intervals."
    );
  }
  const durationNotice = $("processDurationNotice");
  if (durationNotice) {
    durationNotice.hidden = durationNotices.length === 0;
    durationNotice.textContent = durationNotices.join(" ");
  }
  const badge = $("totalProcessDuration");
  if (badge) {
    const status = record.total_processing_status || "date_unavailable";
    badge.className = "status-badge " + (
      status === "completed" ? "status-completed" :
      status === "stopped" ? "status-not_proceeded" :
      status === "in_progress" ? "status-in_progress" : "status-neutral"
    );
    badge.textContent = labels[status] || status;
  }
  const target = $("processDurationHistory");
  if (!target) return;
  target.innerHTML = stages.length ? stages.map((stage) => {
    const status = stage.status || "history_incomplete";
    return '<div class="process-duration-row">' +
      '<div class="process-duration-main"><strong>' + esc(stage.stage_label) +
      '</strong><span class="process-duration-status status-' + esc(status) + '">' +
      esc(labels[status] || status) + '</span></div>' +
      '<div class="process-duration-dates"><span>' + esc(fmt(stage.start_date)) +
      '</span><span aria-hidden="true">→</span><span>' + esc(fmt(stage.end_date)) + '</span></div>' +
      '<strong class="process-duration-days">' +
      esc(stage.duration_days == null ? "—" : durationDaysLabel(stage.duration_days)) +
      '</strong></div>';
  }).join("") : '<p class="muted">No process milestones are recorded.</p>';
}

function refreshClosureControls(record) {
  const closed = record.process_status === "NOT_PROCEEDED";
  const closeButton = $("closeKhsButton");
  const reopenButton = $("reopenKhsButton");
  if (closeButton) closeButton.hidden = closed || !!record.khs_inject_completion_date;
  if (reopenButton) reopenButton.hidden = !closed;
  const summary = $("closureSummary");
  if (!summary) return;
  summary.hidden = !closed;
  summary.innerHTML = closed
    ? '<div class="closure-summary-heading"><strong>Not Proceeded</strong><span>' +
      esc(fmt(record.closure_date)) + '</span></div><p><strong>Reason:</strong> ' +
      esc(String(record.closure_reason_code || "").replace(/_/g, " ")) +
      '</p><p>' + esc(record.closure_notes || "No additional notes recorded.") +
      '</p><small>Closed by ' + esc(record.closed_by || "manual-entry") +
      (record.reopened_at ? ' · Reopened ' + esc(fmt(record.reopened_at)) : '') + '</small>'
    : "";
}

function localDateInputValue() {
  const now = new Date();
  return [now.getFullYear(), String(now.getMonth() + 1).padStart(2, "0"), String(now.getDate()).padStart(2, "0")].join("-");
}

async function submitKhsClosure(event) {
  event.preventDefault();
  const record = state.detail;
  if (!record) return;
  const button = $("confirmClosure");
  const error = $("closureError");
  const data = Object.fromEntries(new FormData($("closureForm")).entries());
  if (error) { error.hidden = true; error.textContent = ""; }
  button.disabled = true;
  button.textContent = "Closing…";
  try {
    await api("/api/dashboard/khs/" + encodeURIComponent(record.khs_id) + "/close", jsonOptions("POST", data));
    $("closureDialog").close();
    $("detailDialog").close();
    toast("KHS closed as Not Proceeded.", true);
    await Promise.all([loadOverview(), loadRegisterIfReady()]);
    if (state.page === "lp") await loadLPCirculation();
    if (state.page === "workflow") await loadWorkflow();
    await openDetails(record.khs_id);
  } catch (err) {
    if (error) { error.textContent = err.message; error.hidden = false; }
    toast(err.message);
  } finally {
    button.disabled = false;
    button.textContent = "Confirm closure";
  }
}

async function submitKhsReopen(event) {
  event.preventDefault();
  const record = state.detail;
  if (!record) return;
  const button = $("confirmReopen");
  const error = $("reopenError");
  const data = Object.fromEntries(new FormData($("reopenForm")).entries());
  if (error) { error.hidden = true; error.textContent = ""; }
  button.disabled = true;
  button.textContent = "Reopening…";
  try {
    await api("/api/dashboard/khs/" + encodeURIComponent(record.khs_id) + "/reopen", jsonOptions("POST", data));
    $("reopenDialog").close();
    $("detailDialog").close();
    toast("KHS reopened.", true);
    await Promise.all([loadOverview(), loadRegisterIfReady()]);
    if (state.page === "lp") await loadLPCirculation();
    if (state.page === "workflow") await loadWorkflow();
    await openDetails(record.khs_id);
  } catch (err) {
    if (error) { error.textContent = err.message; error.hidden = false; }
    toast(err.message);
  } finally {
    button.disabled = false;
    button.textContent = "Reopen KHS";
  }
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
    renderProcessDurationHistory(r);
    renderWorkSummary(r);
    refreshClosureControls(r);
    refreshGuidedProgressControl(r);
    renderWorkbenchFollowUps(result.follow_ups || []);
    $("followUpDueDate").value = localDateInputValue();
    $("followUpNote").value = "";

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
        ["Action owner / PIC",r.action_owner],["Waiting for",r.waiting_for],["Waiting reason",r.waiting_reason],
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
      if (el.dataset.page === "register" || el.dataset.page === "lp") {
        state.workView = el.dataset.page === "lp" ? "lp" : (el.dataset.workView || "active");
        state.workLpStageFilter = null;
        state.workflowStageFilter = null;
        state.workflowAgeBandFilter = null;
        state.workflowRoleFilter = null;
        state.attentionOnly = false;
        state.registerPage = 1;
      }
      go(el.dataset.page);
    });
  });
  document.querySelectorAll("[data-go]").forEach((el) =>
    el.addEventListener("click", () => {
      if (el.dataset.go === "register") {
        state.workView = el.dataset.attentionOnly === "true" ? "attention" : (el.dataset.workView || "active");
        state.workLpStageFilter = null;
        state.workflowStageFilter = null;
        state.workflowAgeBandFilter = null;
        state.workflowRoleFilter = null;
        state.attentionOnly = false;
        state.registerPage = 1;
        if (state.workView === "attention") clearRegisterFilters();
      }
      go(el.dataset.go);
    })
  );
  document.querySelectorAll("[data-queue-stage]").forEach((el) =>
    el.addEventListener("click", () => {
      state.workView = "active";
      state.workLpStageFilter = null;
      state.workflowStageFilter = el.dataset.queueStage;
      state.workflowAgeBandFilter = null;
      state.workflowRoleFilter = null;
      state.attentionOnly = false;
      state.registerPage = 1;
      clearRegisterFilters();
      go("register");
    })
  );
  document.querySelectorAll("[data-queue-role]").forEach((el) =>
    el.addEventListener("click", () => {
      state.workView = "active";
      state.workLpStageFilter = null;
      state.workflowStageFilter = null;
      state.workflowAgeBandFilter = null;
      state.workflowRoleFilter = el.dataset.queueRole;
      state.attentionOnly = false;
      state.registerPage = 1;
      clearRegisterFilters();
      go("register");
    })
  );
  document.querySelectorAll("[data-lp-queue-stage]").forEach((el) =>
    el.addEventListener("click", () => {
      state.workView = "lp";
      state.workLpStageFilter = el.dataset.lpQueueStage || null;
      state.registerPage = 1;
      state.workflowStageFilter = null;
      state.workflowAgeBandFilter = null;
      state.workflowRoleFilter = null;
      clearRegisterFilters();
      go("lp");
    })
  );
  $("refreshButton").addEventListener("click", () => loadPage(state.page).catch((e) => toast(e.message)));
  $("overviewRefresh").addEventListener("click", () => loadOverview().catch((e) => toast(e.message)));
  const workflowCards = $("workflowCards");
  workflowCards.addEventListener("click", (event) => {
    const card = event.target.closest("[data-workflow-stage]");
    if (!card) return;
    state.workView = "active";
    state.workLpStageFilter = null;
    state.workflowStageFilter = card.dataset.workflowStage;
    state.workflowRoleFilter = null;
    state.attentionOnly = false;
    state.registerPage = 1;
    clearRegisterFilters();
    go("register");
  });
  $("workflowEmptyToggle").addEventListener("click", () => {
    state.showEmptyWorkflowStages = !state.showEmptyWorkflowStages;
    renderWorkflowCards();
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
  $("closureForm").addEventListener("submit", submitKhsClosure);
  $("reopenForm").addEventListener("submit", submitKhsReopen);
  $("progressForm").addEventListener("submit", submitGuidedProgress);
  $("followUpForm").addEventListener("submit", submitWorkbenchFollowUp);
  $("updateProgressButton").addEventListener("click", openGuidedProgressDialog);
  $("scheduleFollowUpButton").addEventListener("click", () => {
    $("followUpSection").scrollIntoView({behavior:"smooth",block:"start"});
    $("followUpDueDate").focus();
  });
  $("closeProgressDialog").addEventListener("click", () => $("progressDialog").close());
  $("cancelProgress").addEventListener("click", () => $("progressDialog").close());
  $("refreshOperationsButton").addEventListener("click", () => loadWorkflow().catch((err) => toast(err.message)));
  document.querySelectorAll("[data-workbench-target]").forEach((button) => button.addEventListener("click", () => {
    const target = $(button.dataset.workbenchTarget);
    if (!target) return;
    target.scrollIntoView({behavior:"smooth",block:"start"});
    document.querySelectorAll("[data-workbench-target]").forEach((item) => {
      item.classList.toggle("active", item === button);
      if (item === button) item.setAttribute("aria-current", "location");
      else item.removeAttribute("aria-current");
    });
  }));
  $("operationsStageBody").addEventListener("click", (event) => {
    const filter = event.target.closest("[data-operations-stage]");
    if (!filter) return;
    state.workView = "active";
    state.workLpStageFilter = null;
    state.workflowStageFilter = filter.dataset.operationsStage;
    state.workflowAgeBandFilter = filter.dataset.operationsAgeBand || null;
    state.workflowRoleFilter = null;
    state.attentionOnly = false;
    state.registerPage = 1;
    clearRegisterFilters();
    go("register");
  });
  $("operationsFollowUpBody").addEventListener("click", (event) => {
    const complete = event.target.closest("[data-complete-followup]");
    if (complete) updateFollowUpStatus(complete.dataset.completeFollowup, "complete");
    const open = event.target.closest("[data-view-khs]");
    if (open) openDetails(open.dataset.viewKhs);
  });
  $("followUpList").addEventListener("click", (event) => {
    const complete = event.target.closest("[data-complete-followup]");
    const cancel = event.target.closest("[data-cancel-followup]");
    if (complete) updateFollowUpStatus(complete.dataset.completeFollowup, "complete");
    if (cancel) updateFollowUpStatus(cancel.dataset.cancelFollowup, "cancel");
  });
  $("closeKhsButton").addEventListener("click", () => {
    if (!state.detail) return;
    $("closureKhsLabel").textContent = state.detail.khs_id;
    $("closureDate").value = localDateInputValue();
    $("closureReason").value = "";
    $("closureNotes").value = "";
    $("closureError").hidden = true;
    $("closureDialog").showModal();
  });
  $("reopenKhsButton").addEventListener("click", () => {
    if (!state.detail) return;
    $("reopenKhsLabel").textContent = state.detail.khs_id;
    $("reopenReason").value = "";
    $("reopenError").hidden = true;
    $("reopenDialog").showModal();
  });
  ["closeClosureDialog", "cancelClosure"].forEach((id) => $(id).addEventListener("click", () => $("closureDialog").close()));
  ["closeReopenDialog", "cancelReopen"].forEach((id) => $(id).addEventListener("click", () => $("reopenDialog").close()));
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
  ["statusFilter", "executorFilter", "subtypeFilter", "waitingFilter", "stageFilter", "processStatusFilter"].forEach((id) =>
    $(id).addEventListener("change", () => { state.registerPage = 1; loadRegister().catch((e) => toast(e.message)); })
  );
  $("resetFilters").addEventListener("click", () => {
    clearRegisterFilters();
    state.workflowStageFilter = null;
    state.workflowAgeBandFilter = null;
    state.workflowRoleFilter = null;
    state.attentionOnly = false;
    state.workView = "active";
    state.workLpStageFilter = null;
    state.registerPage = 1;
    loadRegister().catch((e) => toast(e.message));
  });
  document.querySelectorAll("[data-work-queue-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.workView = button.dataset.workQueueView || "active";
      state.workLpStageFilter = null;
      state.workflowStageFilter = null;
      state.workflowAgeBandFilter = null;
      state.workflowRoleFilter = null;
      state.attentionOnly = false;
      state.registerPage = 1;
      loadRegister().catch((e) => toast(e.message));
    });
  });
  $("lpWorkStageFilter").addEventListener("change", () => {
    state.workLpStageFilter = $("lpWorkStageFilter").value || null;
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
  initLanguageSwitcher();
  bind();
  const initial = window.location.hash.replace("#", "");
  go(["overview", "requests", "register", "lp", "contracts", "workflow", "imports", "activity"].indexOf(initial) >= 0 ? initial : "overview");
});
})();