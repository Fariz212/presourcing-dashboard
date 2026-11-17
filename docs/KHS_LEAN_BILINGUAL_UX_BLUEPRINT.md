# KHS Lean Bilingual UX — Design & Implementation Brief

**Branch:** \`feature/khs-lean-bilingual-ux\`  
**Base:** \`khs\` at \`0d9907ff3bf55bc04dc8baa099bef86cdd9a1aee\`

## Product direction

Evolve KHS into a **Contract Operations Command Center**. The goal is to reduce the time and effort required to move a request or KHS record to its next verified state, not to maximize the amount of information on screen.

## Experience principles

1. Action before information: actionable work is more prominent than portfolio statistics.
2. One record, one source of truth: Current Stage, LP sub-stage, injection state, and lifecycle eligibility remain derived from existing business rules.
3. Progressive disclosure: show the fields and context needed for the current task; keep history and advanced details accessible.
4. No silent ambiguity: missing dates, historical gaps, prerequisite exceptions, and unknown owners remain explicit.
5. Designed for actual work conditions: desktop, tablet, and mobile support task completion, not only responsive rendering.
6. Every status leads to a next step: explain why the status matters and where the user can act.
7. Bilingual by design: Indonesian and English are first-class interface locales.

## Bilingual requirements

- Supported locales: \`id\` and \`en\`; initial default is Indonesian.
- Language choice is a browser preference and must not modify business records or server-side workflow codes.
- Navigation, headings, buttons, filters, validation, status labels, empty states, accessibility labels, import feedback, and detail views must use the selected locale.
- User-entered content remains unchanged: vendor names, request subjects, remarks, waiting reasons, uploaded filenames, and document contents are not translated.
- Dates are unambiguous: Indonesian \`dd/MM/yyyy\`; English \`dd MMM yyyy\` (e.g. \`16 Nov 2026\`).
- API errors should use stable error codes and localized client messages. Raw exception details must not be exposed.
- Database values and stable stage codes are not localized; only presentation labels change.

## Navigation model

### Workspace
- Contract Operations — command center / portfolio summary.
- Request Intake — parent request capture and follow-up.
- Work Queue — KHS Register, LP Circulation, and Workflow Monitoring as coordinated worklists.
- Contract Lifecycle — post-injection expiry and renewal control.

### Data & governance
- Excel Import / Export.
- Activity & Audit Log.

Existing routes and deep links should remain valid while navigation is simplified.

## Page-level design intent

- **Overview:** lead with Action Required, bottlenecks, and contract renewal exposure. Portfolio KPIs become supporting context. Avoid repeated summaries.
- **Request Intake:** make parent-to-child KHS progress visible, including current stages and completion.
- **KHS Register:** support task-oriented filters such as Needs My Action, Waiting for Approval, LP Exceptions, and Fully Injected. Do not create a "My" queue until reliable user identity and ownership exist.
- **LP Circulation:** retain the six ordered milestones; show current stage, stage age, next milestone, waiting party, and evidence status.
- **Workflow Monitoring:** show WIP, age distribution, oldest item, and actionable worklists by role/stage. Do not invent SLA thresholds or owners.
- **Contract Lifecycle:** only fully injected KHS records are eligible. Prefer mutually exclusive buckets for portfolio distribution (Expired, 0–14 days, 15–30 days, 31–90 days, 91–180 days, >180 days, Missing/Invalid dates). Cumulative filters must be labelled cumulative.
- **KHS Workbench:** unify identity, current workflow state, LP milestones, injection, contract lifecycle, documents, activity, and next action.
- **Guided Progress Update:** expose only fields relevant to the current stage first; retain Advanced Edit for full-record corrections. Validate chronology and prerequisites before save.
- **Excel Import / Export:** preserve download → edit by stable ID → preview → review → confirm. Never imply changes are saved before confirmation.
- **Activity & Audit Log:** show who changed what and when. Keep manual-entry attribution explicit until authenticated identity exists.

## Seven Wastes — design response

| Waste | UX response | Guardrail |
|---|---|---|
| Overproduction | Remove repeated summary blocks; surface decision-useful KPIs | Keep detailed metrics in their source module |
| Waiting | Expose waiting party, since date, next action, follow-up and escalation | SLA thresholds require process-owner approval |
| Transportation | Unified KHS Workbench with deep links from queues | Preserve route and API contracts |
| Overprocessing | Guided stage update and progressive disclosure | Never auto-fill an evidence date |
| Inventory | WIP and age distribution by stage/role | Use milestone dates; never use \`updated_at\` as stage start |
| Motion | Compact responsive worklists and sticky filters | Do not hide critical information on mobile |
| Defects | Inline validation, consistent dates, explicit uncertainty, auditable identity | Never infer missing approval or legacy sign-off |

## Measurement plan

Measure before/after using comparable production cohorts:
- Median time to locate a KHS record.
- Median interactions from opening a record to saving a valid milestone update.
- Percentage of active records with a named waiting party / next action.
- WIP count and age distribution by stage.
- Missing or invalid milestone dates.
- Import validation errors and rejected uploads.
- Task completion success on desktop, tablet, and mobile.
- Language-switch completion and untranslated-system-string defects.

Do not set numerical targets until a production baseline is measured.

## Delivery sequence

1. Bilingual foundation: language control, locale preference, translation catalogue, date formatting, dynamic content, and error localization.
2. Action Queue: organize priority work around stage, age, waiting party, next action, and direct record access.
3. KHS Workbench: unify record context and expose guided milestone updates.
4. Bottleneck control: WIP aging, role/stage distribution, and escalation after SLA agreement.
5. Responsive refinements and measurement: tablet/mobile tables, accessibility, and task analytics.

## Guardrails / exclusions

- No changes to \`main\`; no direct production edits or restarts.
- No database migration unless a later approved capability requires it.
- No invented SLA, escalation policy, owner assignment, or notification behavior.
- No automatic reconstruction of missing historical milestones.
- No translation or rewriting of user-entered business content.
