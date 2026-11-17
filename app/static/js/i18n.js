(() => {
"use strict";
const EN_ID = {
"WORKSPACE":"RUANG KERJA","DATA MANAGEMENT":"PENGELOLAAN DATA","CONTRACT OPERATIONS":"OPERASIONAL KONTRAK",
"CONTRACT OPERATIONS / PORTFOLIO OVERVIEW":"OPERASIONAL KONTRAK / RINGKASAN PORTOFOLIO",
"Contract Monitoring":"Pemantauan Kontrak","Contract Monitoring & Tracking":"Pemantauan & Pelacakan Kontrak",
"Request Management":"Pengelolaan Permintaan","KHS Register":"Daftar KHS","LP Circulation":"Sirkulasi LP",
"Contract Lifecycle":"Siklus Kontrak","Workflow Monitoring":"Pemantauan Alur Kerja",
"Excel Import / Export":"Impor / Ekspor Excel","Activity & Audit Log":"Aktivitas & Log Audit",
"Contract Creation Workspace":"Ruang Kerja Pembuatan Kontrak",
"Manage requests, KHS records, and the complete workflow in one place.":"Kelola permintaan, data KHS, dan seluruh alur kerja dalam satu tempat.",
"Internal operations":"Operasional internal","Operations":"Operasional","Overview":"Ringkasan",
"Ready":"Siap","Connected":"Terhubung","Unavailable":"Tidak tersedia","Refreshing":"Memperbarui",
"Connection issue":"Gangguan koneksi","Refresh":"Segarkan","Refresh overview":"Segarkan ringkasan",
"LAST UPDATED":"TERAKHIR DIPERBARUI","New Request":"Permintaan Baru","Import Excel":"Impor Excel",
"Total Requests":"Total Permintaan","Parent requests":"Permintaan induk","Total KHS":"Total KHS",
"Contract records":"Data kontrak","Needs Attention":"Perlu Perhatian","Waiting / exception records":"Menunggu / data pengecualian",
"Fully Injected":"Injeksi Selesai","Fully injected":"Injeksi selesai","of all KHS records":"dari seluruh data KHS",
"ACTION REQUIRED":"PERLU TINDAKAN","Priority action queue":"Antrean tindakan prioritas",
"Records awaiting approval, owner follow-up, or prerequisite review.":"Data yang menunggu persetujuan, tindak lanjut penanggung jawab, atau pemeriksaan prasyarat.",
"View attention queue →":"Lihat antrean perhatian →","REQUEST / KHS":"PERMINTAAN / KHS","VENDOR":"VENDOR",
"CURRENT STAGE":"TAHAP SAAT INI","WAITING FOR / NEXT ACTION":"MENUNGGU PIHAK / TINDAKAN BERIKUTNYA",
"STAGE AGE / UPDATED":"LAMA DI TAHAP / DIPERBARUI","ACTION":"TINDAKAN",
"Loading…":"Memuat…","Showing the three highest-priority items. Open the full queue to see every outstanding record.":"Menampilkan tiga pekerjaan dengan prioritas tertinggi. Buka antrean lengkap untuk melihat seluruh pekerjaan yang belum selesai.",
"LIVE WORKFLOW QUEUE":"ANTREAN ALUR KERJA","Approval Pipeline":"Jalur Persetujuan",
"Next approver is calculated from the recorded milestone dates, not the optional Waiting For field.":"Penyetuju berikutnya ditentukan dari tanggal milestone yang tercatat, bukan dari kolom opsional Pihak yang Ditunggu.",
"Milestone-derived":"Berdasarkan milestone","Memo Internal":"Memo Internal",
"Pending management approvals":"Menunggu persetujuan manajemen","in queue":"dalam antrean",
"Junior Manager":"Manajer Junior","Senior Manager":"Manajer Senior","General Manager":"Manajer Umum",
"Awaiting Head approval":"Menunggu persetujuan Head","Awaiting SM approval":"Menunggu persetujuan SM",
"Awaiting GM approval":"Menunggu persetujuan GM","Fixed six-step sign-off route":"Alur persetujuan enam tahap",
"Tim Kontrak":"Tim Kontrak","Vendor Management":"Manajemen Vendor","Strategic Sourcing":"Strategic Sourcing",
"Initial review":"Pemeriksaan awal","Management approval":"Persetujuan manajemen","Final sign-off":"Persetujuan akhir Direktur",
"MI GM prerequisite":"Prasyarat MI GM","MI GM prerequisite exception":"Pengecualian prasyarat MI GM",
"MI GM prerequisite review":"Pemeriksaan prasyarat MI GM","Legacy stage unverified":"Tahap historis belum terverifikasi",
"Legacy Unverified":"Data historis belum terverifikasi","Timeline gaps":"Celah pada linimasa",
"Records requiring reconciliation are kept outside normal approval lanes.":"Data yang perlu rekonsiliasi dipisahkan dari antrean persetujuan normal.",
"Current LP stage is derived from the ordered milestone dates. Exceptions are kept outside the approval lanes.":"Tahap LP saat ini ditentukan dari urutan tanggal milestone. Data pengecualian dipisahkan dari antrean persetujuan.",
"POST-INJECTION MONITORING":"PEMANTAUAN SETELAH INJEKSI","Contract Lifecycle Watch":"Pantauan Siklus Kontrak",
"Renewal visibility starts once a KHS is fully injected.":"Pemantauan perpanjangan dimulai setelah KHS selesai diinjeksi.",
"Open contract lifecycle →":"Buka siklus kontrak →","Renewal preparation":"Persiapan perpanjangan",
"Renewal watch":"Pantauan perpanjangan","Action required":"Perlu tindakan","Expired":"Kedaluwarsa",
"Past contract end date":"Melewati tanggal akhir kontrak","Missing dates":"Tanggal belum tersedia",
"Fully injected · incomplete period":"Injeksi selesai · periode belum lengkap",
"WORKSPACE / INTAKE":"RUANG KERJA / PENERIMAAN",
"Create and manage parent requests. One request may contain multiple KHS items.":"Buat dan kelola permintaan induk. Satu permintaan dapat memiliki beberapa data KHS.",
"REQUEST SUBJECT":"SUBJEK PERMINTAAN","VENDOR PORTFOLIO":"PORTOFOLIO VENDOR","REQUEST DATE":"TANGGAL PERMINTAAN",
"REQUESTER / OWNER":"PEMOHON / PENANGGUNG JAWAB","KHS ITEMS":"DATA KHS","FULLY INJECTED":"INJEKSI SELESAI",
"Loading requests…":"Memuat permintaan…","WORKSPACE / RECORDS":"RUANG KERJA / DATA",
"Manage each contract record, assign ownership, and update its milestones.":"Kelola setiap data kontrak, tetapkan penanggung jawab, dan perbarui milestone.",
"Add KHS":"Tambah KHS","Filter KHS records":"Filter data KHS","Search KHS records":"Cari data KHS",
"Search by request, vendor or KHS ID…":"Cari berdasarkan permintaan, vendor, atau ID KHS…",
"Filter by LP status":"Filter berdasarkan status LP","All LP statuses":"Semua status LP",
"Completed":"Selesai","In progress":"Sedang berlangsung","Not started":"Belum dimulai",
"More filters":"Filter lainnya","Executor":"Pelaksana","All executors":"Semua pelaksana",
"Contract type":"Jenis kontrak","All subtypes":"Semua jenis","Waiting for":"Menunggu pihak",
"All waiting parties":"Semua pihak","Workflow stage":"Tahap alur kerja","All workflow stages":"Semua tahap alur kerja",
"Reset filters":"Atur ulang filter","CURRENT STAGE & AGE":"TAHAP SAAT INI & DURASI",
"LP STATUS":"STATUS LP","INJECTION":"INJEKSI","NEXT ACTION":"TINDAKAN BERIKUTNYA",
"No KHS records match the current filters.":"Tidak ada data KHS yang sesuai dengan filter saat ini.",
"No records currently require attention.":"Saat ini tidak ada data yang memerlukan perhatian.",
"Untitled request":"Permintaan tanpa judul","Review prerequisite":"Periksa prasyarat",
"Review next action":"Periksa tindakan berikutnya","Closed stage":"Tahap ditutup",
"History needs review":"Riwayat perlu ditinjau","Stage age unavailable":"Durasi tahap tidak tersedia",
"Since ":"Sejak ","Updated ":"Diperbarui ","View record":"Lihat data","Details":"Detail",
"Injection started":"Injeksi dimulai","Review data / prerequisite":"Periksa data / prasyarat",
"No waiting owner recorded":"Belum ada pihak penanggung jawab yang tercatat",
"Director sign-off unverified":"Persetujuan Direktur belum terverifikasi",
"Historical timeline gaps":"Celah pada linimasa historis",
"WORKSPACE / PROCESS CONTROL":"RUANG KERJA / KENDALI PROSES",
"See where records are waiting and open the matching worklist directly.":"Lihat tahap tempat data sedang menunggu dan buka daftar pekerjaan terkait secara langsung.",
"Loading workflow stages…":"Memuat tahapan alur kerja…","Show empty stages":"Tampilkan tahap kosong",
"Loading workflow…":"Memuat alur kerja…","LP CIRCULATION":"SIRKULASI LP",
"LoA Sign-off Route":"Alur Persetujuan LoA",
"LP circulation is gated by GM SCM MI approval. The route is shown for process visibility; individual sign-off dates remain tracked on each KHS record.":"Sirkulasi LP mensyaratkan persetujuan MI dari GM SCM. Alur ditampilkan untuk visibilitas proses; tanggal setiap persetujuan tetap dicatat pada masing-masing data KHS.",
"POST-INJECTION / RENEWAL CONTROL":"SETELAH INJEKSI / KENDALI PERPANJANGAN",
"Monitor contract duration and expiry exposure after KHS is fully injected.":"Pantau durasi dan risiko berakhirnya kontrak setelah KHS selesai diinjeksi.",
"Eligible contracts":"Kontrak yang memenuhi kriteria","Expiring ≤ 6 months":"Berakhir dalam ≤ 6 bulan",
"Expiring ≤ 3 months":"Berakhir dalam ≤ 3 bulan","Expiring ≤ 1 month":"Berakhir dalam ≤ 1 bulan",
"Start renewal preparation":"Mulai persiapan perpanjangan","Renewal action required":"Perlu tindakan perpanjangan",
"Escalate renewal":"Eskalasi perpanjangan","All lifecycle statuses":"Semua status siklus kontrak",
"Upcoming contract":"Kontrak yang akan berlaku","Expiring within 6 months":"Berakhir dalam 6 bulan",
"Expiring within 3 months":"Berakhir dalam 3 bulan","Expiring within 1 month":"Berakhir dalam 1 bulan",
"Urgent · 14 days":"Mendesak · 14 hari","Final warning · 7 days":"Peringatan terakhir · 7 hari",
"Missing contract dates":"Tanggal kontrak belum tersedia","Invalid contract dates":"Tanggal kontrak tidak valid",
"Active · over 6 months":"Aktif · lebih dari 6 bulan","KHS / VENDOR":"KHS / VENDOR",
"REQUEST":"PERMINTAAN","CONTRACT PERIOD":"PERIODE KONTRAK","TERM":"JANGKA WAKTU",
"TIME REMAINING":"SISA WAKTU","CONTRACT STATUS":"STATUS KONTRAK","RENEWAL ALERT":"PERINGATAN PERPANJANGAN",
"No fully injected contracts match this lifecycle filter.":"Tidak ada kontrak yang sudah diinjeksi penuh dan sesuai dengan filter siklus ini.",
"The 6-, 3-, and 1-month counts are cumulative urgency thresholds, so shorter horizons are included in longer ones. Alert stages use Contract End Date and Jakarta local date. Monitoring is in-app; email and WhatsApp notifications are not enabled.":"Jumlah 6, 3, dan 1 bulan merupakan ambang urgensi kumulatif; periode yang lebih singkat juga termasuk dalam periode yang lebih panjang. Tahap peringatan menggunakan Tanggal Akhir Kontrak dan tanggal lokal Jakarta. Pemantauan dilakukan di aplikasi; notifikasi email dan WhatsApp belum tersedia.",
"DATA MANAGEMENT / WORKBOOK WORKSPACE":"PENGELOLAAN DATA / RUANG KERJA EXCEL",
"Download the latest database workbook, edit existing records by ID, then preview and confirm the changes. Legacy v2.2 and v2.3 workbooks remain supported.":"Unduh workbook basis data terbaru, ubah data berdasarkan ID, lalu tinjau dan konfirmasi perubahan. Workbook lama versi 2.2 dan 2.3 tetap didukung.",
"Download current Excel":"Unduh Excel terbaru","Export KHS CSV":"Ekspor KHS ke CSV",
"Download the live workbook":"Unduh workbook terbaru","Start with the latest database snapshot":"Mulai dari salinan data terbaru",
"Update in Excel":"Perbarui di Excel","Keep record IDs unchanged":"Jangan ubah ID data",
"Validate & confirm":"Validasi & konfirmasi","Review changes before they are saved":"Tinjau perubahan sebelum disimpan",
"Upload edited KHS workbook":"Unggah workbook KHS yang telah diperbarui",
"Use the current workbook download for updates. Keep Request ID and KHS ID unchanged. Blank cells preserve existing database values; removed rows do not delete records.":"Gunakan workbook terbaru untuk pembaruan. Jangan ubah Request ID dan KHS ID. Sel kosong mempertahankan nilai yang ada di basis data; baris yang dihapus tidak menghapus data.",
"You can also drag and drop an .xlsx file here.":"Anda juga dapat menarik dan meletakkan file .xlsx di sini.",
"Choose file":"Pilih file","No file selected":"Belum ada file dipilih","Validate workbook":"Validasi workbook",
"VALIDATION RESULT":"HASIL VALIDASI","Workbook preview":"Pratinjau workbook","PREVIEWED":"TELAH DITINJAU",
"Total rows":"Total baris","Valid rows":"Baris valid","Warnings":"Peringatan","Errors":"Kesalahan",
"Changes to be applied":"Perubahan yang akan diterapkan","New records":"Data baru",
"Updated records":"Data diperbarui","Unchanged records":"Data tidak berubah","Changed fields":"Kolom berubah",
"No record fields will change. The uploaded values match the current database.":"Tidak ada kolom data yang berubah. Nilai yang diunggah sama dengan data di basis data.",
"The preview is calculated against the current database values. Blank cells remain no-change; no records are written until Confirm Import.":"Pratinjau dihitung berdasarkan nilai basis data saat ini. Sel kosong tidak mengubah data; tidak ada data yang disimpan sebelum Konfirmasi Impor.",
"Validation issues":"Masalah validasi","SEVERITY":"TINGKAT KEPARAHAN","ENTITY":"ENTITAS","SHEET / ROW":"LEMBAR / BARIS","DETAIL":"RINCIAN",
"Additional issues are not displayed.":"Masalah tambahan tidak ditampilkan.",
"I have reviewed and acknowledge the warnings.":"Saya telah meninjau dan memahami peringatan.",
"Review validation result.":"Tinjau hasil validasi.","Confirm import":"Konfirmasi impor",
"Acknowledge warnings before confirmation.":"Setujui peringatan sebelum konfirmasi.",
"Validation passed.":"Validasi berhasil.","Resolve errors before import.":"Selesaikan kesalahan sebelum impor.",
"AUDIT TRAIL":"JEJAK AUDIT","Import History":"Riwayat Impor","Refresh history":"Segarkan riwayat",
"BATCH":"BATCH","WORKBOOK":"WORKBOOK","STATUS":"STATUS","ROWS":"BARIS","INSERTED":"DITAMBAHKAN",
"UPDATED":"DIPERBARUI","UNCHANGED":"TIDAK BERUBAH","UPLOADED":"DIUNGGAH","Not loaded.":"Belum dimuat.",
"DATA MANAGEMENT / TRACEABILITY":"PENGELOLAAN DATA / KETERTELUSURAN",
"Manual edits and Excel imports are recorded for traceability. Manual edits are labelled manual-entry until sign-in is introduced.":"Perubahan manual dan impor Excel dicatat untuk ketertelusuran. Perubahan manual diberi label manual-entry sampai fitur login diterapkan.",
"Search activity history":"Cari riwayat aktivitas","Search record ID, actor, action…":"Cari ID data, pelaku, tindakan…",
"Filter activity entity":"Filter entitas aktivitas","All entities":"Semua entitas","KHS records":"Data KHS","Requests":"Permintaan",
"WHEN":"WAKTU","ENTITY":"ENTITAS","RECORD ID":"ID DATA","ACTOR":"PELAKU","CHANGES":"PERUBAHAN",
"No activity matches the current filters.":"Tidak ada aktivitas yang sesuai dengan filter saat ini.",
"Reset":"Atur ulang","NEW RECORD":"DATA BARU","EDIT RECORD":"UBAH DATA","Create record":"Buat data",
"Create Request":"Buat Permintaan","Create KHS item":"Buat data KHS","Save record":"Simpan data",
"Saving…":"Menyimpan…","Cancel":"Batal","Close":"Tutup","KHS RECORD":"DATA KHS","KHS Details":"Detail KHS",
"Approval journey":"Perjalanan persetujuan","Evidence-led view of the six LP milestones":"Tampilan berbasis bukti untuk enam milestone LP",
"Current Stage":"Tahap Saat Ini","Stage Age":"Lama di Tahap","Upcoming":"Berikutnya",
"Evidence Documents":"Dokumen Bukti","Supporting files attached to this KHS record.":"Dokumen pendukung yang dilampirkan pada data KHS ini.",
"Document type":"Jenis dokumen","KHS Evidence":"Bukti KHS","KHS Inject Evidence":"Bukti Injeksi KHS",
"LP Evidence":"Bukti LP","Supporting Document":"Dokumen Pendukung","Upload evidence":"Unggah bukti",
"Loading documents…":"Memuat dokumen…","Edit record":"Ubah data",
"Supplier & contract":"Supplier & kontrak","The request, supplier, owner, and contract identity.":"Identitas permintaan, supplier, penanggung jawab, dan kontrak.",
"Commercial & MI approvals":"Persetujuan Komersial & MI",
"Commercial checkpoints and approvals required before LP circulation.":"Tahap pemeriksaan komersial dan persetujuan yang diperlukan sebelum sirkulasi LP.",
"Record each submission, completion, and approval date only when supported by evidence.":"Catat tanggal pengajuan, penyelesaian, dan persetujuan hanya jika didukung bukti.",
"6 milestones":"6 milestone","KHS Injection":"Injeksi KHS",
"This phase starts only after Director-signed LP completion.":"Tahap ini hanya dimulai setelah LP ditandatangani Direktur.",
"Coordination & next action":"Koordinasi & tindakan berikutnya",
"Who currently holds the action, why it is waiting, and contextual notes.":"Pihak yang sedang memegang tindakan, alasan menunggu, dan catatan konteks.",
"Parent request":"Permintaan induk","Vendor name":"Nama vendor","Dispatch date":"Tanggal penerusan",
"Contract start date":"Tanggal mulai kontrak","Contract end date":"Tanggal akhir kontrak",
"BOQ confirmation date":"Tanggal konfirmasi BOQ","Negotiation date":"Tanggal negosiasi",
"Final negotiation date":"Tanggal negosiasi final","MI Head approval":"Persetujuan MI Head",
"MI SM approval":"Persetujuan MI SM","MI GM approval":"Persetujuan MI GM","Legal submission date":"Tanggal pengajuan ke Legal",
"LP circulation start / User submitted":"Mulai sirkulasi LP / Diajukan User",
"LP Contract Team completion":"Penyelesaian Tim Kontrak LP","LP Junior Manager approval":"Persetujuan Junior Manager LP",
"LP Senior Manager approval":"Persetujuan Senior Manager LP","LP GM SCM approval":"Persetujuan GM SCM LP",
"LP Director sign-off / LP completion":"Tanda tangan Direktur LP / LP selesai",
"KHS injection start":"Mulai injeksi KHS","KHS fully injected date":"Tanggal KHS selesai diinjeksi",
"Currently waiting for":"Sedang menunggu pihak","Waiting reason / next action":"Alasan menunggu / tindakan berikutnya","Remarks":"Catatan",
"Enter milestone dates only when supported by a recorded submission, approval, or completion. MI GM approval and LP chronology are validated when saved.":"Masukkan tanggal milestone hanya jika didukung catatan pengajuan, persetujuan, atau penyelesaian. Persetujuan MI GM dan urutan tanggal LP divalidasi saat disimpan.",
"Request ID is generated automatically when the record is saved.":"Request ID dibuat secara otomatis saat data disimpan.",
"Select request":"Pilih permintaan","Select executor":"Pilih pelaksana","Select type":"Pilih jenis",
"current / inactive":"saat ini / tidak aktif","No changes to save.":"Tidak ada perubahan untuk disimpan.",
"Record updated.":"Data berhasil diperbarui.","Record created.":"Data berhasil dibuat.",
"Blank cells preserve existing values.":"Sel kosong mempertahankan nilai yang sudah ada.",
"Ready to confirm. Review and acknowledge warnings where present.":"Siap dikonfirmasi. Tinjau dan setujui peringatan jika ada.",
"Import blocked: correct the validation errors and upload the corrected workbook.":"Impor diblokir: perbaiki kesalahan validasi dan unggah workbook yang sudah diperbaiki.",
"Import completed.":"Impor selesai.",
"Import completed. Existing records were preserved where source cells were blank.":"Impor selesai. Data yang sudah ada dipertahankan jika sel sumber kosong.",
"Choose a document first.":"Pilih dokumen terlebih dahulu.",
"Evidence document uploaded.":"Dokumen bukti berhasil diunggah.",
"Please choose an Excel workbook in .xlsx format.":"Pilih workbook Excel dengan format .xlsx.",
"Only .xlsx Excel workbooks can be uploaded.":"Hanya workbook Excel berformat .xlsx yang dapat diunggah.",
"Use Choose file to select this workbook in your browser.":"Gunakan Pilih file untuk memilih workbook ini di browser.",
"No import batches yet.":"Belum ada batch impor.","No LP records match the selected stage.":"Tidak ada data LP yang sesuai dengan tahap yang dipilih.",
"Review required":"Perlu ditinjau",
"The available milestone history does not support a reliable active-stage assignment.":"Riwayat milestone yang tersedia belum cukup untuk menentukan tahap aktif secara andal.",
"After verification":"Setelah diverifikasi","No next approval stage has been inferred.":"Tahap persetujuan berikutnya belum dapat ditentukan.",
"Not calculated":"Belum dihitung","Stage age is withheld until the current stage can be established.":"Durasi tahap belum ditampilkan sampai tahap saat ini dapat dipastikan.",
"The next approval or completion milestone is outstanding.":"Milestone persetujuan atau penyelesaian berikutnya masih menunggu.",
"Since the last recorded LP milestone":"Sejak milestone LP terakhir yang tercatat",
"LP completed":"LP selesai","The post-LP contract phase.":"Tahap kontrak setelah LP.",
"LP circulation has not been initiated.":"Sirkulasi LP belum dimulai.",
"User submission":"Pengajuan User","First milestone in the LP route.":"Milestone pertama dalam alur LP.",
"The clock starts when LP is submitted.":"Perhitungan waktu dimulai saat LP diajukan.",
"Prerequisite review":"Pemeriksaan prasyarat",
"The LP start date does not satisfy the MI GM approval prerequisite.":"Tanggal mulai LP tidak memenuhi prasyarat persetujuan MI GM.",
"A legacy completion label is not proof of a Director-signed LP.":"Label penyelesaian historis bukan bukti LP telah ditandatangani Direktur.",
"Historical timeline incomplete":"Linimasa historis belum lengkap",
"Missing historical dates prevent a reliable current-stage assignment.":"Tanggal historis yang hilang menghalangi penentuan tahap saat ini secara andal.",
"Date not recorded":"Tanggal tidak tercatat","No historical date on record":"Tidak ada tanggal historis yang tercatat",
"Awaiting completion":"Menunggu penyelesaian","Unverified":"Belum terverifikasi","Needs verification":"Perlu verifikasi",
"Historical sequence cannot be confirmed":"Urutan historis tidak dapat dikonfirmasi",
"LP circulation started":"Sirkulasi LP dimulai","Contract Team completion":"Penyelesaian Tim Kontrak",
"Vendor Management approval":"Persetujuan Manajemen Vendor","Strategic Sourcing approval":"Persetujuan Strategic Sourcing",
"General Management approval":"Persetujuan Manajemen Umum",
"Director-signed LP completion":"Penyelesaian LP yang ditandatangani Direktur",
"There is no active LP stage.":"Tidak ada tahap LP yang sedang aktif.",
"Not yet reached":"Belum tercapai","Dates required":"Tanggal diperlukan",
"Expires today":"Berakhir hari ini","Contract status":"Status kontrak","Renewal alert":"Peringatan perpanjangan",
"Contract start":"Mulai kontrak","Contract end":"Akhir kontrak","Contract term":"Jangka waktu kontrak",
"Time remaining":"Sisa waktu","Injection started":"Injeksi dimulai",
"Supplier & request":"Supplier & permintaan","Commercial & approval history":"Riwayat komersial & persetujuan",
"Dispatch":"Penerusan","BOQ confirmation":"Konfirmasi BOQ","Negotiation":"Negosiasi","Final negotiation":"Negosiasi final",
"Last updated":"Terakhir diperbarui","Unassigned":"Belum ditetapkan",
"days overdue":"hari terlambat","days remaining":"hari tersisa",
"Request failed":"Permintaan gagal","Please try again.":"Silakan coba lagi.",
"Contract Monitoring & Tracking":"Pemantauan & Pelacakan Kontrak",
"KHS Contract Creation Management":"Pengelolaan Pembuatan Kontrak KHS",
"Director":"Direktur",
"Search LP circulation records":"Cari data sirkulasi LP",
"Search KHS, request, vendor…":"Cari KHS, permintaan, vendor…",
"Action required · 1 month":"Perlu tindakan · 1 bulan",
"Renewal watch · 3 months":"Pantauan perpanjangan · 3 bulan",
"Renewal preparation · 6 months":"Persiapan perpanjangan · 6 bulan",
"Active":"Aktif",
"Not fully injected":"Belum diinjeksi penuh",
"Renewal action due":"Tindakan perpanjangan perlu dilakukan",
"Choose language":"Pilih bahasa",
"CONTRACT OPERATIONS":"OPERASIONAL KONTRAK",
"DATA MANAGEMENT":"PENGELOLAAN DATA",
"Operations":"Operasional",
"Overview":"Ringkasan",
"Activity & Audit Log":"Aktivitas & Log Audit",
"One place to move each request from intake to LP sign-off, injection, and renewal.":"Satu tempat untuk mengelola permintaan sejak diterima hingga persetujuan LP, injeksi, dan perpanjangan.",
"↻ Refresh overview":"↻ Segarkan ringkasan",
"+ New Request":"+ Permintaan Baru",
"+ Add KHS":"+ Tambah KHS",
"Import Excel":"Impor Excel",
"Parent requests":"Permintaan induk",
"Total KHS":"Total KHS",
"Needs Attention":"Perlu Perhatian",
"Waiting / exception records":"Data menunggu / pengecualian",
"of all KHS records":"dari seluruh data KHS",
"Priority action queue":"Antrean tindakan prioritas",
"REQUEST / KHS":"PERMINTAAN / KHS",
"VENDOR":"VENDOR",
"WAITING FOR / NEXT ACTION":"MENUNGGU PIHAK / TINDAKAN BERIKUTNYA",
"ACTION":"TINDAKAN",
"Showing the three highest-priority items. Open the full queue to see every outstanding record.":"Menampilkan tiga pekerjaan dengan prioritas tertinggi. Buka antrean lengkap untuk melihat seluruh pekerjaan yang belum selesai.",
"Approval Pipeline":"Jalur Persetujuan",
"Memo Internal":"Memo Internal",
"in queue":"dalam antrean",
"in normal queue":"dalam antrean normal",
"Senior Manager":"Manajer Senior",
"Awaiting SM approval":"Menunggu persetujuan SM",
"General Manager":"Manajer Umum",
"Fixed six-step sign-off route":"Alur persetujuan enam tahap",
"Vendor Management":"Manajemen Vendor",
"Strategic Sourcing":"Strategic Sourcing",
"Management approval":"Persetujuan manajemen",
"Final sign-off":"Persetujuan akhir",
"Legacy stage unverified":"Tahap historis belum terverifikasi",
"Timeline gaps":"Celah pada linimasa",
"Contract Lifecycle Watch":"Pantauan Siklus Kontrak",
"Renewal preparation":"Persiapan perpanjangan",
"≤ 6 months · cumulative":"≤ 6 bulan · kumulatif",
"≤ 3 months · cumulative":"≤ 3 bulan · kumulatif",
"≤ 1 month · cumulative":"≤ 1 bulan · kumulatif",
"Action required":"Perlu tindakan",
"Expired":"Kedaluwarsa",
"Missing dates":"Tanggal belum tersedia",
"Past contract end date":"Melewati tanggal akhir kontrak",
"Fully injected · incomplete period":"Injeksi selesai · periode belum lengkap",
"VENDOR PORTFOLIO":"PORTOFOLIO VENDOR",
"REQUEST DATE":"TANGGAL PERMINTAAN",
"KHS ITEMS":"DATA KHS",
"FULLY INJECTED":"INJEKSI SELESAI",
"WORKSPACE / RECORDS":"RUANG KERJA / DATA",
"+ Add KHS":"+ Tambah KHS",
"All LP statuses":"Semua status LP",
"In progress":"Sedang berlangsung",
"Not started":"Belum dimulai",
"Executor":"Pelaksana",
"All executors":"Semua pelaksana",
"All subtypes":"Semua jenis",
"Waiting for":"Menunggu pihak",
"Workflow stage":"Tahap alur kerja",
"All workflow stages":"Semua tahap alur kerja",
"REQUEST / VENDOR":"PERMINTAAN / VENDOR",
"CURRENT STAGE & AGE":"TAHAP SAAT INI & DURASI",
"INJECTION":"INJEKSI",
"NEXT ACTION":"TINDAKAN BERIKUTNYA",
"APPROVAL JOURNEY / LP":"ALUR PERSETUJUAN / LP",
"Track every LP milestone from User submission through Director sign-off, with current stage and stage age.":"Lacak setiap milestone LP sejak pengajuan User hingga tanda tangan Direktur, termasuk tahap saat ini dan durasinya.",
"Refresh":"Segarkan",
"All LP records":"Semua data LP",
"Started or historically recorded":"Sudah dimulai atau tercatat secara historis",
"Next milestone":"Milestone berikutnya",
"Awaiting approval":"Menunggu persetujuan",
"LP Completed":"LP Selesai",
"Director signed":"Ditandatangani Direktur",
"Historical data quality":"Kualitas data historis",
"Review these separately from the live approval route.":"Tinjau data ini secara terpisah dari alur persetujuan aktif.",
"MI GM Exceptions":"Pengecualian MI GM",
"LP gate not met":"Prasyarat LP belum terpenuhi",
"Timeline Gaps":"Celah pada linimasa",
"Missing historical dates":"Tanggal historis belum tersedia",
"All LP stages":"Semua tahap LP",
"MI GM prerequisite exception":"Pengecualian prasyarat MI GM",
"Director / Direktur":"Direktur",
"KHS / VENDOR":"KHS / VENDOR",
"STAGE AGE":"DURASI TAHAP",
"LP START":"MULAI LP",
"HISTORY":"RIWAYAT",
"Loading LP records…":"Memuat data LP…",
"Show empty stages":"Tampilkan tahap kosong",
"LP CIRCULATION":"SIRKULASI LP",
"User":"User",
"Junior Manager Vendor Management":"Manajer Junior Manajemen Vendor",
"Senior Manager Strategic Sourcing":"Manajer Senior Strategic Sourcing",
"Direktur":"Direktur",
"Expiring ≤ 6 months":"Berakhir dalam ≤ 6 bulan",
"Expiring ≤ 3 months":"Berakhir dalam ≤ 3 bulan",
"Expiring ≤ 1 month":"Berakhir dalam ≤ 1 bulan",
"Renewal action required":"Perlu tindakan perpanjangan",
"Requires data completion":"Perlu melengkapi data",
"All lifecycle statuses":"Semua status siklus kontrak",
"Expiring within 6 months":"Berakhir dalam 6 bulan",
"Expiring within 3 months":"Berakhir dalam 3 bulan",
"Expiring within 1 month":"Berakhir dalam 1 bulan",
"Final warning · 7 days":"Peringatan terakhir · 7 hari",
"Invalid contract dates":"Tanggal kontrak tidak valid",
"CONTRACT PERIOD":"PERIODE KONTRAK",
"TERM":"JANGKA WAKTU",
"CONTRACT STATUS":"STATUS KONTRAK",
"RENEWAL ALERT":"PERINGATAN PERPANJANGAN",
"Loading contracts…":"Memuat data kontrak…",
"Start with the latest database snapshot":"Mulai dari salinan basis data terbaru",
"Keep record IDs unchanged":"Jangan ubah ID data",
"Review changes before they are saved":"Tinjau perubahan sebelum disimpan",
"No file selected":"Belum ada file yang dipilih",
"Validate workbook":"Validasi workbook",
"Workbook preview":"Pratinjau workbook",
"PREVIEWED":"TELAH DITINJAU",
"Valid rows":"Baris valid",
"Warnings":"Peringatan",
"Errors":"Kesalahan",
"New records":"Data baru",
"Unchanged records":"Data tidak berubah",
"Changed fields":"Kolom yang berubah",
"RECORD":"DATA",
"OPERATION":"OPERASI",
"FIELDS TO CHANGE":"KOLOM YANG DIUBAH",
"SEVERITY":"TINGKAT KEPARAHAN",
"ENTITY":"ENTITAS",
"SHEET / ROW":"LEMBAR / BARIS",
"DETAIL":"RINCIAN",
"Confirm import":"Konfirmasi impor",
"Import History":"Riwayat Impor",
"Refresh history":"Segarkan riwayat",
"WORKBOOK":"WORKBOOK",
"STATUS":"STATUS",
"ROWS":"BARIS",
"INSERTED":"DITAMBAHKAN",
"UNCHANGED":"TIDAK BERUBAH",
"UPLOADED":"DIUNGGAH",
"Not loaded.":"Belum dimuat.",
"All entities":"Semua entitas",
"KHS records":"Data KHS",
"Requests":"Permintaan",
"RECORD ID":"ID DATA",
"ACTOR":"PELAKU",
"CHANGES":"PERUBAHAN",
"KHS Contract Operations":"Operasional Kontrak KHS",
"Contract Monitoring & Tracking · Internal workspace":"Pemantauan & Pelacakan Kontrak · Ruang kerja internal",
"NEW RECORD":"DATA BARU",
"Create record":"Buat data",
"Cancel":"Batal",
"Save record":"Simpan data",
"KHS RECORD":"DATA KHS",
"KHS Details":"Detail KHS",
"Evidence-led view of the six LP milestones":"Tampilan berbasis bukti untuk enam milestone LP",
"Stage Age":"Durasi Tahap",
"Upcoming":"Berikutnya",
"POST-INJECTION":"SETELAH INJEKSI",
"Supporting files attached to this KHS record.":"Dokumen pendukung yang dilampirkan pada data KHS ini.",
"KHS Evidence":"Bukti KHS",
"KHS Inject Evidence":"Bukti Injeksi KHS",
"Supporting Document":"Dokumen Pendukung",
"Upload evidence":"Unggah bukti",
"Edit record":"Ubah data",
"Close":"Tutup",
"Open navigation":"Buka navigasi",
"Close navigation":"Tutup navigasi",
"Main navigation":"Navigasi utama",
"Data management":"Pengelolaan data",
"Choose file":"Pilih file",
"Search requests":"Cari permintaan",
"Search subject, vendor, owner…":"Cari subjek, vendor, penanggung jawab…",
"Search KHS, request, vendor…":"Cari KHS, permintaan, vendor…",
"LP approval stages":"Tahapan persetujuan LP",
"Historical data quality filters":"Filter kualitas data historis",
"Search contract lifecycle records":"Cari data siklus kontrak",
"Workbook workflow":"Alur kerja workbook",
"Excel workbook upload area":"Area unggah workbook Excel",
"Current LP stage summary":"Ringkasan tahap LP saat ini",
"LP approval milestones":"Milestone persetujuan LP",
"Request Received":"Permintaan diterima",
"MI Approval - GM":"Persetujuan MI - GM",
"KHS Inject":"Injeksi KHS",
"Legal Processing":"Proses Legal",
"Legal Submission":"Pengajuan ke Legal",
"Director Sign-off":"Tanda tangan Direktur"

};
const ID_EN=Object.fromEntries(Object.entries(EN_ID).map(([en,id])=>[id,en]));
const ATTRS=["placeholder","aria-label","title","data-label","data-title"];

function pattern(value, lang) {
  let m;
  if(lang==="id"){
    if((m=/^(\d+) day in stage$/.exec(value)) || (m=/^(\d+) days in stage$/.exec(value))) return m[1]+" hari di tahap";
    if((m=/^(\d+) days overdue$/.exec(value))) return m[1]+" hari terlambat";
    if((m=/^(\d+) days remaining$/.exec(value))) return m[1]+" hari tersisa";
    if((m=/^(\d+) of (\d+) stages have records · (\d+) records assigned to a workflow stage$/.exec(value))) return m[1]+" dari "+m[2]+" tahap memiliki data · "+m[3]+" data berada dalam tahap alur kerja";
    if((m=/^Show (\d+) empty stages$/.exec(value))) return "Tampilkan "+m[1]+" tahap kosong";
    if((m=/^Open KHS (.+)$/.exec(value))) return "Buka KHS "+m[1];
    if((m=/^Waiting for (.+)$/.exec(value))) return "Menunggu pihak: "+m[1];
    if((m=/^Page (\d+) of (\d+)$/.exec(value))) return "Halaman "+m[1]+" dari "+m[2];
    if((m=/^(\d+) records$/.exec(value))) return m[1]+" data";

    if((m=/^(\d+) days$/.exec(value)) || (m=/^(\d+) day$/.exec(value))) return m[1]+" hari";
    if((m=/^Since (.+)$/.exec(value))) return "Sejak "+m[1];
    if((m=/^Updated (.+)$/.exec(value))) return "Diperbarui "+m[1];
    if((m=/^Waiting since (.+)$/.exec(value))) return "Menunggu sejak "+m[1];
    if((m=/^Page (\d+) of (\d+) · (\d+) records$/.exec(value))) return "Halaman "+m[1]+" dari "+m[2]+" · "+m[3]+" data";
    if((m=/^Page (\d+) of (\d+) · (\d+) LP records$/.exec(value))) return "Halaman "+m[1]+" dari "+m[2]+" · "+m[3]+" data LP";
    if((m=/^Page (\d+) of (\d+) · (\d+) contracts$/.exec(value))) return "Halaman "+m[1]+" dari "+m[2]+" · "+m[3]+" kontrak";
    if((m=/^Page (\d+) of (\d+) · (\d+) activities$/.exec(value))) return "Halaman "+m[1]+" dari "+m[2]+" · "+m[3]+" aktivitas";
    if((m=/^Page (\d+) · (\d+) batches$/.exec(value))) return "Halaman "+m[1]+" · "+m[2]+" batch";
    if((m=/^(\d+) records checked$/.exec(value))) return m[1]+" data diperiksa";
    if((m=/^(\d+) issue\(s\)$/.exec(value))) return m[1]+" masalah";
  } else {
    if((m=/^(\d+) hari di tahap$/.exec(value))) return m[1]+(m[1]==="1"?" day in stage":" days in stage");
    if((m=/^(\d+) hari terlambat$/.exec(value))) return m[1]+" days overdue";
    if((m=/^(\d+) hari tersisa$/.exec(value))) return m[1]+" days remaining";
    if((m=/^(\d+) dari (\d+) tahap memiliki data · (\d+) data berada dalam tahap alur kerja$/.exec(value))) return m[1]+" of "+m[2]+" stages have records · "+m[3]+" records assigned to a workflow stage";
    if((m=/^Tampilkan (\d+) tahap kosong$/.exec(value))) return "Show "+m[1]+" empty stages";
    if((m=/^Buka KHS (.+)$/.exec(value))) return "Open KHS "+m[1];
    if((m=/^Menunggu pihak: (.+)$/.exec(value))) return "Waiting for "+m[1];
    if((m=/^Halaman (\d+) dari (\d+)$/.exec(value))) return "Page "+m[1]+" of "+m[2];
    if((m=/^(\d+) data$/.exec(value))) return m[1]+" records";

    if((m=/^(\d+) hari$/.exec(value))) return m[1]+" days";
    if((m=/^Sejak (.+)$/.exec(value))) return "Since "+m[1];
    if((m=/^Diperbarui (.+)$/.exec(value))) return "Updated "+m[1];
    if((m=/^Menunggu sejak (.+)$/.exec(value))) return "Waiting since "+m[1];
    if((m=/^Halaman (\d+) dari (\d+) · (\d+) data LP$/.exec(value))) return "Page "+m[1]+" of "+m[2]+" · "+m[3]+" LP records";
    if((m=/^Halaman (\d+) dari (\d+) · (\d+) kontrak$/.exec(value))) return "Page "+m[1]+" of "+m[2]+" · "+m[3]+" contracts";
    if((m=/^Halaman (\d+) dari (\d+) · (\d+) aktivitas$/.exec(value))) return "Page "+m[1]+" of "+m[2]+" · "+m[3]+" activities";
    if((m=/^Halaman (\d+) dari (\d+) · (\d+) data$/.exec(value))) return "Page "+m[1]+" of "+m[2]+" · "+m[3]+" records";
    if((m=/^Halaman (\d+) · (\d+) batch$/.exec(value))) return "Page "+m[1]+" · "+m[2]+" batches";
    if((m=/^(\d+) data diperiksa$/.exec(value))) return m[1]+" records checked";
    if((m=/^(\d+) masalah$/.exec(value))) return m[1]+" issue(s)";
  }
  return value;
}
function tr(value,lang){
  const original=String(value==null?"":value), trimmed=original.trim();
  if(!trimmed)return original;
  const result=lang==="id"?(Object.prototype.hasOwnProperty.call(EN_ID,trimmed)?EN_ID[trimmed]:pattern(trimmed,lang)):(Object.prototype.hasOwnProperty.call(ID_EN,trimmed)?ID_EN[trimmed]:pattern(trimmed,lang));
  if(result===trimmed)return original;
  return (original.match(/^\s*/)||[""])[0]+result+(original.match(/\s*$/)||[""])[0];
}
function skip(el){return !el||!!el.closest("script,style,textarea,input,[contenteditable='true'],[data-no-translate],.user-content,.raw-data");}
function skipAttribute(el){return !el||!!el.closest("script,style,[contenteditable='true'],[data-no-translate],.user-content,.raw-data");}
function walk(root,lang){
  const element=root.nodeType===1?root:root.parentElement;
  if(element&&skip(element)&&!(root.nodeType===1&&(root.tagName==="INPUT"||root.tagName==="TEXTAREA")))return;
  if(root.nodeType===3){if(root.parentElement&&!skip(root.parentElement))root.nodeValue=tr(root.nodeValue,lang);return;}
  if(root.nodeType!==1&&root!==document)return;
  const target=root===document?document.body:root;
  if(!target)return;
  if(target.nodeType===1){
    const dateInputs=target.matches&&target.matches('input[type="date"]')?[target]:[];
    dateInputs.concat(Array.from(target.querySelectorAll('input[type="date"]'))).forEach(input=>input.setAttribute("lang",lang==="id"?"id-ID":"en-GB"));
  }
  if(target.nodeType===1&&!skipAttribute(target))ATTRS.forEach(a=>{if(target.hasAttribute(a)){const before=target.getAttribute(a),after=tr(before,lang);if(after!==before)target.setAttribute(a,after);}});
  const tree=document.createTreeWalker(target,NodeFilter.SHOW_TEXT),nodes=[];
  while(tree.nextNode())nodes.push(tree.currentNode);
  nodes.forEach(n=>{if(!skip(n.parentElement))n.nodeValue=tr(n.nodeValue,lang);});
  target.querySelectorAll(ATTRS.map(a=>"["+a+"]").join(",")).forEach(n=>{if(!skipAttribute(n))ATTRS.forEach(a=>{if(n.hasAttribute(a)){const before=n.getAttribute(a),after=tr(before,lang);if(after!==before)n.setAttribute(a,after);}});});
}
function getLanguage(){try{return localStorage.getItem("khs-language")==="en"?"en":"id";}catch(_){return "id";}}
function setLanguage(language){
  const lang=language==="en"?"en":"id";
  document.documentElement.lang=lang;
  document.querySelectorAll('input[type="date"]').forEach(input=>{input.setAttribute("lang",lang==="id"?"id-ID":"en-GB");});
  const languageSwitch=document.querySelector(".language-switch");
  if(languageSwitch) languageSwitch.setAttribute("aria-label",lang==="id"?"Pilih bahasa":"Choose language");
  document.title=tr("Contract Monitoring & Tracking",lang);
  const description=document.querySelector('meta[name="description"]');
  if(description) description.setAttribute("content",tr("KHS Contract Creation Management",lang));
  walk(document,lang);
  document.querySelectorAll("[data-khs-language]").forEach(b=>{const active=b.dataset.khsLanguage===lang;b.classList.toggle("is-active",active);b.setAttribute("aria-pressed",String(active));});
  try{localStorage.setItem("khs-language",lang);}catch(_){}
  window.dispatchEvent(new CustomEvent("khs:localechange",{detail:{language:lang}}));
}
document.addEventListener("DOMContentLoaded",()=>{
  let lang=getLanguage();setLanguage(lang);
  document.querySelectorAll("[data-khs-language]").forEach(b=>b.addEventListener("click",()=>{lang=b.dataset.khsLanguage==="en"?"en":"id";setLanguage(lang);}));
  const observer=new MutationObserver(ms=>ms.forEach(m=>{
    if(m.type==="childList")m.addedNodes.forEach(n=>walk(n,lang));
    else if(m.type==="attributes")ATTRS.forEach(a=>{if(m.target.hasAttribute&&m.target.hasAttribute(a)){const before=m.target.getAttribute(a),after=tr(before,lang);if(after!==before)m.target.setAttribute(a,after);}});
  }));
  observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:ATTRS});
});
window.KHS_I18N={t:value=>tr(value,getLanguage()),language:getLanguage};
})();