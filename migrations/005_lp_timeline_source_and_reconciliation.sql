BEGIN;

-- Distinguish genuinely active new milestone tracking from historic LP records
-- whose current owner cannot be reconstructed from the old single-date format.
ALTER TABLE khs_items
    ADD COLUMN IF NOT EXISTS lp_timeline_source TEXT NOT NULL DEFAULT 'MILESTONE_TRACKED';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_khs_lp_timeline_source'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_khs_lp_timeline_source
            CHECK (lp_timeline_source IN ('MILESTONE_TRACKED', 'LEGACY_UNVERIFIED'));
    END IF;
END
$$;

-- Existing records with only a circulation-start date do not contain enough
-- evidence to infer whether they are still with Tim Kontrak or have advanced.
-- Preserve all dates and place them in a separate reconciliation bucket.
UPDATE khs_items
SET lp_timeline_source = 'LEGACY_UNVERIFIED'
WHERE lp_circulation_start_date IS NOT NULL
  AND lp_contract_team_completion_date IS NULL
  AND lp_junior_manager_approval_date IS NULL
  AND lp_senior_manager_approval_date IS NULL
  AND lp_gm_scm_approval_date IS NULL
  AND lp_completion_date IS NULL;

INSERT INTO schema_migrations (version)
VALUES ('005_lp_timeline_source_and_reconciliation')
ON CONFLICT (version) DO NOTHING;

COMMIT;
