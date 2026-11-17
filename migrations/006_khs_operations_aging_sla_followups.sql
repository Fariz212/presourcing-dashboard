BEGIN;

ALTER TABLE khs_items
    ADD COLUMN IF NOT EXISTS action_owner TEXT;

CREATE TABLE IF NOT EXISTS khs_stage_sla_policies (
    stage_code TEXT PRIMARY KEY
        REFERENCES khs_stage_config(stage_code) ON UPDATE CASCADE ON DELETE CASCADE,
    warning_after_days INTEGER,
    target_days INTEGER,
    escalation_after_days INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    CONSTRAINT chk_khs_sla_nonnegative CHECK (
        (warning_after_days IS NULL OR warning_after_days >= 0)
        AND (target_days IS NULL OR target_days >= 0)
        AND (escalation_after_days IS NULL OR escalation_after_days >= 0)
    ),
    CONSTRAINT chk_khs_sla_order CHECK (
        (warning_after_days IS NULL OR target_days IS NULL OR warning_after_days <= target_days)
        AND (target_days IS NULL OR escalation_after_days IS NULL OR target_days <= escalation_after_days)
    )
);

-- Intentionally leave policy thresholds NULL: management must define the agreed SLA.
INSERT INTO khs_stage_sla_policies(stage_code)
SELECT stage_code
FROM khs_stage_config
WHERE is_active = TRUE
  AND stage_code NOT IN ('COMPLETED', 'NOT_PROCEEDED')
ON CONFLICT (stage_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS khs_follow_ups (
    id BIGSERIAL PRIMARY KEY,
    khs_id TEXT NOT NULL REFERENCES khs_items(khs_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    stage_code TEXT NOT NULL REFERENCES khs_stage_config(stage_code) ON UPDATE CASCADE ON DELETE RESTRICT,
    due_date DATE NOT NULL,
    follow_up_to TEXT,
    note TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'manual-entry',
    completed_at TIMESTAMPTZ,
    completed_by TEXT,
    cancelled_at TIMESTAMPTZ,
    cancelled_by TEXT,
    CONSTRAINT chk_khs_follow_up_status CHECK (status IN ('OPEN', 'COMPLETED', 'CANCELLED', 'SUPERSEDED'))
);

CREATE INDEX IF NOT EXISTS idx_khs_follow_ups_open_due
    ON khs_follow_ups(due_date, khs_id)
    WHERE status = 'OPEN';

CREATE INDEX IF NOT EXISTS idx_khs_follow_ups_khs
    ON khs_follow_ups(khs_id, created_at DESC);

INSERT INTO schema_migrations(version)
VALUES ('006_khs_operations_aging_sla_followups')
ON CONFLICT (version) DO NOTHING;

COMMIT;
