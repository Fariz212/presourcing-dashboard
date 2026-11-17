# KHS Operations: SLA Policy Configuration

The WIP analytics page calculates elapsed calendar days from the current workflow stage's recorded opening milestone. The age buckets (0–7, 8–14, 15–30, 31+ days) are descriptive reporting bands; they are **not** service-level commitments.

## Important: agree the policy before entering thresholds

No target days are seeded by migration 006. This is intentional. The relevant business owners must agree the warning, target, and escalation thresholds for each stage before the dashboard can label work as Due Soon, Overdue, or Escalation Due.

The dashboard uses these rules (calendar days, evaluated using the Jakarta-local date):

- **On track**: age is below the configured warning threshold.
- **Due soon**: age has reached `warning_after_days`, but is below the target.
- **Overdue**: age has reached `target_days`.
- **Escalation due**: age has reached `escalation_after_days`.
- **Not configured**: no target is available. The system will not infer an SLA.
- **Age unavailable**: the record has no valid stage-start milestone date.

Threshold precedence is escalation, then target, then warning. Configure non-decreasing values: warning ≤ target ≤ escalation.

## Review current configuration

Run this read-only query against the KHS database:

```sql
SELECT
    stage.stage_code,
    stage.stage_name,
    policy.warning_after_days,
    COALESCE(policy.target_days, stage.default_sla_days) AS effective_target_days,
    policy.escalation_after_days
FROM khs_stage_config AS stage
LEFT JOIN khs_stage_sla_policies AS policy
    ON policy.stage_code = stage.stage_code
WHERE stage.is_active = TRUE
  AND stage.stage_code NOT IN ('COMPLETED', 'NOT_PROCEEDED')
ORDER BY stage.sequence_number;
```

## Set an approved policy

After the business owner approves a threshold, update only the relevant stage. Example structure (replace the NULL placeholders with approved integer day values):

```sql
UPDATE khs_stage_sla_policies
SET warning_after_days = NULL,
    target_days = NULL,
    escalation_after_days = NULL,
    updated_at = NOW(),
    updated_by = 'approved-operator'
WHERE stage_code = 'NEGOTIATION';
```

The table constraint rejects negative values and rejects warning/target/escalation values in the wrong order. If using the legacy `khs_stage_config.default_sla_days` as the target, leave `target_days` NULL and configure warning/escalation separately. The effective target is the policy `target_days` when populated, otherwise `default_sla_days`.

To disable SLA status for a stage, set both `khs_stage_sla_policies.target_days` and `khs_stage_config.default_sla_days` to NULL. WIP aging remains visible.

## Reminders and escalation

Follow-ups are stored in `khs_follow_ups` and displayed in the in-app Workflow inbox and KHS Workbench. A follow-up is attached to the stage active when it was scheduled. When that stage advances, the reminder is marked `SUPERSEDED`, rather than remaining as an actionable reminder for the wrong stage.

This release provides **in-app** reminders and escalation indicators only. It does not send email, WhatsApp, SMS, or push notifications. External delivery requires a separately approved notification service and recipient/identity model.
