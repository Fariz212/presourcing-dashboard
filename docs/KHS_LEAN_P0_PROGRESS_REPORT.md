# KHS Lean UI/UX — P0 Progress & Handoff Report

**Phase:** P0 — Unified KHS Work Queue  
**Status:** IMPLEMENTED AND CI-VERIFIED; awaiting human review / merge.  
**Report date:** 18 November 2026 (Asia/Jakarta)  
**Repository:** `Fariz212/presourcing-dashboard`  
**Base branch:** `khs`  
**Base SHA:** `206ab270c91fd78293b299a65f2f094e86e2b7b8`  
**Feature branch:** `feature/khs-lean-p0-work-queue`  
**Verified application commit:** `02abf208282f21f609ebab5a74682c43729b3531`  
**Pull request:** [#17 — Implement Lean P0 unified KHS Work Queue](https://github.com/Fariz212/presourcing-dashboard/pull/17)  
**PR state:** Open, draft, not merged.  
**Production:** Not deployed. No production database or EC2 changes.

## 1. Objective and problem statement

The 7-Waste source review found that KHS Register, LP Circulation, and Workflow Monitoring presented overlapping operational worklists. It also found an ambiguous owner fallback in which `action_owner || waiting_for` caused the party being waited for to appear as though it were the internal action owner.

P0 reduces navigation and interpretation waste without changing the underlying workflow rules or adding new infrastructure.

## 2. Implemented scope

1. **Unified Work Queue.** KHS Register is reframed as Work Queue.
2. **Six saved views:** All KHS, Active WIP, Waiting / Attention, LP Circulation, Data Exceptions, and Unassigned PIC. Each view reuses the existing KHS register source-of-truth and a server-side, validated filter.
3. **LP compatibility.** The LP sidebar shortcut and existing `#lp` route remain supported, but route into the LP saved view inside Work Queue. LP view includes active, completed, and legacy-partial LP histories based on recorded milestone evidence.
4. **Operations Analytics.** Workflow Monitoring is renamed Operations Analytics. Stage and aging drill-downs enter Active WIP in Work Queue and preserve the chosen stage/age filter.
5. **Separate accountability fields.** Work Queue and Overview Priority Action Queue now distinguish:
   - Action Owner — internal person/PIC recorded in `action_owner`
   - Waiting On — party recorded in `waiting_for`
   - Next Action / Milestone — recorded `waiting_reason` context or the evidence-derived Guided Progress milestone
6. **Missing owner visibility.** Active incomplete KHS with no Action Owner display as Unassigned and are discoverable via the Unassigned PIC saved view. The system does not auto-assign a person.
7. **Bilingual consistency.** New work-oriented labels use the existing ID/EN language switcher and preserve the saved language preference.

## 3. Seven-Waste mapping

| Waste | P0 change | What is and is not claimed |
|---|---|---|
| Transportation | One Work Queue contains KHS and LP worklists through saved views | Reduces navigation between overlapping operational lists; no measured travel/time study has been performed |
| Motion | LP shortcut routes into Work Queue; analytics drill-down enters the right saved view | Reduces page switching and repeated filtering |
| Inventory | Unassigned PIC view exposes active incomplete WIP without an owner | Makes unowned WIP visible; does not assign capacity or people |
| Defects | Action Owner, Waiting On, and Next Action are distinct in both work queues | Removes the owner/waiting-party substitution identified in source review |
| Overprocessing | One shared table and endpoint power the saved views | Avoids maintaining multiple operational tables for the same KHS source |
| Overproduction | P0 consolidates overlapping LP work surfaces | Further summary/KPI reduction is intentionally deferred to P1 |
| Waiting | No new SLA or notification behavior was introduced | Actual waiting-time reduction is not claimed; SLA remains subject to process-owner agreement |

## 4. Files changed

- `app/routes/dashboard.py` — validated saved-view parameters and SQL filters
- `app/templates/dashboard.html` — work-oriented navigation, saved-view controls, distinct queue columns
- `app/static/js/dashboard.js` — saved-view state, LP route compatibility, independent owner/waiting/action rendering, translations and drill-down behavior
- `app/static/css/dashboard-studio.css` — nested LP shortcut and responsive saved-view tabs
- `tests/test_dashboard_api.py` — saved-view API validation/filter tests
- `tests/test_dashboard_ui.py` — Work Queue and accountability UI assertions
- `tests/visual_preview.py` — LP saved-view, ownership, clear-all and analytics drill-down browser checks
- `docs/KHS_LEAN_P0_PROGRESS_REPORT.md` — this report / recovery handoff

No database migration was added.

## 5. Verification evidence

**GitHub Actions run #231**  
Run ID: `44172148261`  
[Open CI run #231](https://github.com/Fariz212/presourcing-dashboard/actions/runs/44172148261)  
Tested SHA: `02abf208282f21f609ebab5a74682c43729b3531`

| Check | Verified result |
|---|---|
| Disposable CI database schema/migrations | Passed |
| Python application/test compilation | Passed |
| JavaScript syntax (`node --check`) | Passed |
| Automated test suite | **170 passed in 2.06s** |
| Browser Visual Preview | Passed |
| Browser screenshots | **21 captures** (desktop, tablet and mobile coverage) |
| Bilingual browser check | Passed |
| WIP analytics and aging drill-down | Passed |
| Guided Progress chronology, MI GM update and audit entry | Passed |
| LP approvals and injection preparation/execution | Passed |
| P0 saved views | Passed |
| Inclusion of LP-completed records in LP view | Passed |
| Explicit Unassigned PIC / separate Waiting On / Next Action | Passed |
| Clear-all saved-view reset | Passed |
| Operations Analytics drill-down into Active WIP | Passed |
| API failures | **0** |
| Uncaught page errors | **0** |
| Capture errors | **0** |
| Responsive overflow warnings | **0** |

Earlier CI attempts exposed a missing comma in the translation dictionary and browser assertions still tied to the pre-P0 labels/column layout. Those issues were corrected before run #231. Run #231 is the passing verification record; earlier failed attempts are not used as evidence of completion.

## 6. Guardrails and unchanged behavior

- `main` was not changed. At the time of verification its SHA remained `8c5a25490622c689456287d21bd70984d15f9bd1`.
- Base branch `khs` remained at `206ab270c91fd78293b299a65f2f094e86e2b7b8`; P0 changes are isolated on the feature branch.
- PR #17 remains draft and unmerged.
- No production deployment, Gunicorn restart, production database backup or migration was performed by this P0 work.
- No new SLA thresholds, notification channels, staffing targets, user identity or permission assumptions were invented.
- LP approval sequence, chronology validation, Guided Progress, closure/reopen, evidence integrity, and Excel import behavior were not intentionally changed.
- The separate older PR #15 (`feature/khs-lean-bilingual-ux`) was left untouched. Do not assume that PR has been merged; it remains a separate, stale open PR based on an older `khs` commit.

## 7. P1 gate and next-phase scope

P0 is complete from an implementation and CI perspective. P1 has **not** started.

The next Lean phase should focus on:
1. Reduce repeated portfolio/approval/LP summaries between Control Tower and Operations Analytics.
2. Simplify WIP Aging table presentation: show the essential stage/WIP/median/P90/oldest/condition first, with aging buckets and SLA details on drill-down.
3. Apply progressive disclosure to KHS Workbench so the current work state and next action are immediately visible, with detailed process history, LP, contract, record/activity, follow-up, and evidence revealed only when needed.
4. Revisit duplicate refresh controls and make refresh behavior consistent.

P1 must preserve all P0 saved views and the three accountability concepts. It must not invent SLA values or remove data-quality controls. Keep changes on a separate feature branch based on the accepted P0/base state; do not edit `main` directly.

## 8. Recovery instructions if conversation context is lost

1. Open PR [#17](https://github.com/Fariz212/presourcing-dashboard/pull/17).
2. Confirm head branch `feature/khs-lean-p0-work-queue` and the verified source SHA `02abf208282f21f609ebab5a74682c43729b3531` (or a later report-only commit on that branch).
3. Read this report before changing source.
4. Do not repeat or recreate P0. It is implemented and verified.
5. Continue with P1 as a new phase/branch and prepare a separate P1 progress report before starting P2.
