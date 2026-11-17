# KHS Lean UI/UX — P1 Progress & Handoff Report

**Phase:** P1 — Progressive Control Tower Analytics & KHS Workbench  
**Status:** IMPLEMENTED AND CI-VERIFIED; awaiting human review / merge.  
**Report date:** 18 November 2026 (Asia/Jakarta)  
**Repository:** `Fariz212/presourcing-dashboard`  
**P1 base branch:** `feature/khs-lean-p0-work-queue`  
**P1 base SHA:** `921e04537423bca0acfac04fe4dd57e51f50a909`  
**P1 feature branch:** `feature/khs-lean-p1-control-tower-workbench`  
**Verified application/test SHA:** `281656f9ea7ddd69e4ad41caa72aba89bf187512`  
**Pull request:** [#18 — Implement Lean P1 progressive Control Tower and KHS Workbench](https://github.com/Fariz212/presourcing-dashboard/pull/18)  
**PR state:** Open, draft, not merged.  
**Production:** Not deployed. No production database or EC2 changes.

## 1. Objective

P1 reduces overprocessing, motion and cognitive load after P0 unified KHS/LP worklists. It simplifies the default presentation of WIP analytics and KHS details while preserving all supporting evidence, drill-downs, history, and controls.

## 2. Implemented scope

### 2.1 Operations Analytics
- Workflow stage distribution / quick stage shortcuts are now in a closed-by-default disclosure. The WIP aging profile is the primary stage-control view; stage shortcuts remain available.
- WIP aging's always-visible table is reduced from 13 columns to six: Stage/Bottleneck Rank, WIP, Median, P90, Oldest, and Condition.
- All five age bands remain available under a per-stage `Age bands & SLA details` disclosure: 0–7, 8–14, 15–30, 31+ and Age unavailable.
- Per-stage SLA policy, overdue and escalation values remain accessible in the same disclosure. The UI does not invent or configure SLA thresholds.
- Existing `data-operations-stage` and `data-operations-age-band` filters are preserved, so stage and age drill-down still opens the matching P0 Work Queue.
- Mobile layout now uses a fixed six-column responsive table that wraps content to fit narrow viewports; it no longer imposes a 620px table minimum.

### 2.2 KHS Workbench
- The seven work areas are preserved: Overview, Process History, LP Milestones, Contract, Record & Activity, Follow-ups, and Evidence.
- Workbench navigation now switches one visible panel at a time instead of scrolling through seven long sections.
- Work Summary opens by default; secondary panels remain accessible on demand.
- Closure summary is grouped into the Overview panel.
- Schedule Follow-up opens the Follow-ups panel and focuses the due-date field.
- The global Refresh button preserves the currently selected Workbench panel when reloading the open KHS record.

### 2.3 Refresh controls
- Duplicate page-level refresh controls were removed.
- One persistent top-bar Refresh action reloads the current page or the open Workbench record.
- Import History refresh now uses that contextual control as well.

## 3. Seven-Waste mapping

| Waste | P1 change | Expected effect |
|---|---|---|
| Overprocessing | Six scan-first WIP columns; other detail is disclosed per stage | Less information to parse during first-pass scanning, without deleting detail |
| Overproduction | Stage distribution is optional rather than repeated beside the primary aging profile | Fewer always-visible duplicate summaries |
| Motion | Workbench sections switch as panels instead of scroll anchors | Fewer long scroll movements and context changes |
| Motion / Overprocessing | One global contextual Refresh replaces repeated page-level controls | One consistent refresh location |
| Defects | Data quality warnings, all five age bands, SLA and existing deep links remain accessible | Simplification does not hide or remove evidence needed to diagnose WIP |

Waiting-time reduction is not claimed. No SLA thresholds, staffing/capacity assumptions, notification channels, or service commitments were introduced.

## 4. Files changed by P1

- `app/templates/dashboard.html` — optional stage-distribution disclosure, six-column aging table, single-panel Workbench markup, removal of duplicate refresh controls
- `app/static/js/dashboard.js` — compact aging renderer with per-stage disclosure, Workbench panel controller, contextual refresh behavior, follow-up panel navigation and new translations
- `app/static/css/dashboard-studio.css` — disclosure styles, panel visibility/active state, responsive six-column mobile layout
- `tests/visual_preview.py` — browser interaction tests for progressive Workbench panels, detail/follow-up tabs, age disclosures, and responsive checks
- `tests/test_dashboard_ui.py` — static UI test for single-panel Workbench and one refresh control
- `tests/test_khs_operations_ui.py` — analytics / progressive disclosure assertions

P1 adds no database migration and changes no backend workflow logic.

## 5. Verification evidence

**GitHub Actions run #234**  
Run ID: `44174896812`  
[Open CI run #234](https://github.com/Fariz212/presourcing-dashboard/actions/runs/44174896812)  
Verified source SHA: `281656f9ea7ddd69e4ad41caa72aba89bf187512`

| Check | Verified result |
|---|---|
| Disposable CI database schema/migrations | Passed |
| Python application/test compilation | Passed |
| JavaScript syntax (`node --check`) | Passed |
| Automated test suite | **171 passed in 2.22s** |
| Browser Visual Preview | Passed |
| Browser screenshots | **21 captures** across desktop, tablet and mobile, including Workbench detail/form captures |
| Bilingual navigation | Passed |
| WIP bucket reconciliation | Passed; all five buckets reconcile to WIP |
| Aging percentile ordering | Passed; Median ≤ P90 ≤ Oldest |
| 31+ day drill-down | Passed |
| Age-unavailable / inconsistent-history drill-down | Passed |
| Guided Progress chronology, MI GM and audit history | Passed |
| LP approvals and injection preparation/execution | Passed |
| Stage-scoped reminder supersession | Passed |
| P0 saved views and ownership separation | Passed |
| Workbench LP / Follow-ups panel interactions | Passed |
| API failures | **0** |
| Uncaught page errors | **0** |
| Capture errors | **0** |
| Responsive overflow warnings | **0** |

Run #233 (earlier P1 iteration) was not a passing run: it exposed two overly strict static class assertions, hidden Workbench-panel assumptions in the browser tests, and one 620px mobile table-width warning. Those issues were corrected in the verified SHA above. Only run #234 is evidence of completion.

## 6. Guardrails and unchanged behavior

- `main` remained at `8c5a25490622c689456287d21bd70984d15f9bd1`.
- `khs` remained at `206ab270c91fd78293b299a65f2f094e86e2b7b8`.
- P0 branch remains `feature/khs-lean-p0-work-queue` with its report at `docs/KHS_LEAN_P0_PROGRESS_REPORT.md`.
- P0 PR #17 remains open, draft and unmerged.
- P1 PR #18 remains open, draft and unmerged. Its base should be `feature/khs-lean-p0-work-queue` (stacked on P0). During this verification, PR #18 was temporarily retargeted to `khs` only to trigger the repository's CI workflow, which is configured to run PR checks only for PRs targeting `khs`. After run #234 passed, restore its base to the P0 feature branch.
- No production deployment, Gunicorn restart, production database migration, or live-data change was performed.
- No schema migrations, backend workflow logic, LP approval order, chronology guard, Guided Progress rules, closure/reopen semantics, evidence integrity behavior, or Excel import confirmation semantics were intentionally changed.
- No SLA thresholds, notifications, staffing/capacity limits, or identity assumptions were introduced.

## 7. Next phase gate

P1 is complete from an implementation and CI perspective. It remains subject to human review and stacked PR merge order:
1. Review/merge P0 PR #17 into `khs` first.
2. Rebase/retarget P1 PR #18 onto the updated `khs` and run CI again if its base/head changes.
3. Merge P1 only after its PR checks pass against the updated base.
4. Start P2 only after P1 is accepted. P2 candidates from the Lean audit include role-specific task queues/ownership discipline and identity-backed actor audit, but these need explicit requirements and must not be invented as part of P1.

## 8. Recovery instructions if conversation context is lost

1. Read `docs/KHS_LEAN_P0_PROGRESS_REPORT.md` and this file before changing source.
2. Open PR #17 and PR #18; confirm both are open/draft/unmerged.
3. Confirm P1 branch `feature/khs-lean-p1-control-tower-workbench` contains verified implementation SHA `281656f9ea7ddd69e4ad41caa72aba89bf187512` (or the later report-only commit).
4. Verify CI run #234 passed at that source SHA.
5. Restore PR #18 base to `feature/khs-lean-p0-work-queue` while P0 PR #17 is still unmerged.
6. Do not repeat P0 or P1 implementation. Continue with the review/merge sequence, then define P2 as a new separately reported phase.
