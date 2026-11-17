# KHS Lean UI/UX — P0 Progress Report

**Status:** Implemented on a feature branch; pending CI verification and review.  
**Base branch:** `khs`  
**Base commit:** `206ab270c91fd78293b299a65f2f094e86e2b7b8`  
**Feature branch:** `feature/khs-lean-p0-work-queue`  
**Production:** Not changed by this work.

## Why P0 exists

The 7-Waste review found avoidable navigation between KHS Register, LP Circulation, and Workflow Monitoring, plus an ambiguous register field that used `action_owner || waiting_for` as a single ownership display. The P0 implementation turns the KHS list into one operational Work Queue and keeps LP as a saved view.

## Scope implemented

1. Rename the main KHS Register workspace to **Work Queue**.
2. Add six server-filtered saved views: All KHS, Active WIP, Waiting / Attention, LP Circulation, Data Exceptions, and Unassigned PIC.
3. Keep the LP sidebar shortcut and legacy `#lp` deep link, but route both into the LP saved view inside Work Queue.
4. Keep workflow stage/aging drill-downs connected to the Active WIP queue.
5. Separate the worklist display into Action Owner, Waiting On, and Next Action / Milestone. An absent action owner is displayed as **Unassigned**; Waiting On is never substituted as the internal owner.
6. Rename Workflow Monitoring to **Operations Analytics** to distinguish analytical review from operator worklists.
7. Keep the saved views on the existing KHS register query and source-of-truth milestone derivation. No schema migration is required.

## Guardrails

- No edits to `main`.
- No production deployment or production database changes.
- No new SLA thresholds, staffing assumptions, notifications, or user identity model.
- No changes to milestone chronology, LP approval order, closure behavior, evidence handling, or Excel import semantics.
- Existing `#lp` links remain supported as a route into the LP saved view.

## Waste targeted

| Waste | P0 response |
|---|---|
| Transportation | One Work Queue for KHS and LP worklists |
| Motion | Saved views and deep links reduce page switching |
| Inventory | Unassigned PIC view exposes active WIP without an action owner |
| Defects | Action Owner, Waiting On, and Next Action are separate fields |
| Overprocessing | One shared register table and API for the saved views |

Waiting time itself is not claimed to be reduced by this UI change. SLA policies and escalation rules remain unconfigured until process owners approve them.

## Verification

CI and browser visual preview results will be added here after the feature branch checks complete. Do not interpret this report as evidence of production deployment.

## Next phase gate: P1

P1 may start only after:
- P0 CI and visual preview pass;
- saved-view queries are checked against production-like synthetic records;
- the LP saved view still includes legacy partial histories and completed LP records;
- the unassigned view is confirmed to include only active, incomplete KHS work;
- a human review confirms the three ownership concepts are understandable.

P1 scope expected from the Lean audit: simplify duplicate overview/analytics summaries and progressive disclosure in KHS Workbench. Do not add or invent SLA targets as part of P1.
