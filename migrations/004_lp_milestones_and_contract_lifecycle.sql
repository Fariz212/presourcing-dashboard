BEGIN;

-- Add the missing LP circulation milestones without rewriting historical data.
ALTER TABLE khs_items
    ADD COLUMN IF NOT EXISTS lp_contract_team_completion_date DATE,
    ADD COLUMN IF NOT EXISTS lp_junior_manager_approval_date DATE,
    ADD COLUMN IF NOT EXISTS lp_senior_manager_approval_date DATE,
    ADD COLUMN IF NOT EXISTS lp_gm_scm_approval_date DATE;

-- Keep milestone dates chronologically valid when adjacent dates are recorded.
-- Null intermediate dates remain permitted for legacy records whose history
-- was not captured in the previous application versions.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lp_contract_team_after_start'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_lp_contract_team_after_start
            CHECK (
                lp_contract_team_completion_date IS NULL
                OR lp_circulation_start_date IS NULL
                OR lp_contract_team_completion_date >= lp_circulation_start_date
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lp_junior_after_contract_team'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_lp_junior_after_contract_team
            CHECK (
                lp_junior_manager_approval_date IS NULL
                OR (
                    (lp_circulation_start_date IS NULL
                        OR lp_junior_manager_approval_date >= lp_circulation_start_date)
                    AND (lp_contract_team_completion_date IS NULL
                        OR lp_junior_manager_approval_date >= lp_contract_team_completion_date)
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lp_senior_after_junior'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_lp_senior_after_junior
            CHECK (
                lp_senior_manager_approval_date IS NULL
                OR (
                    (lp_circulation_start_date IS NULL
                        OR lp_senior_manager_approval_date >= lp_circulation_start_date)
                    AND (lp_contract_team_completion_date IS NULL
                        OR lp_senior_manager_approval_date >= lp_contract_team_completion_date)
                    AND (lp_junior_manager_approval_date IS NULL
                        OR lp_senior_manager_approval_date >= lp_junior_manager_approval_date)
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lp_gm_after_senior'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_lp_gm_after_senior
            CHECK (
                lp_gm_scm_approval_date IS NULL
                OR (
                    (lp_circulation_start_date IS NULL
                        OR lp_gm_scm_approval_date >= lp_circulation_start_date)
                    AND (lp_contract_team_completion_date IS NULL
                        OR lp_gm_scm_approval_date >= lp_contract_team_completion_date)
                    AND (lp_junior_manager_approval_date IS NULL
                        OR lp_gm_scm_approval_date >= lp_junior_manager_approval_date)
                    AND (lp_senior_manager_approval_date IS NULL
                        OR lp_gm_scm_approval_date >= lp_senior_manager_approval_date)
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lp_director_after_gm'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_lp_director_after_gm
            CHECK (
                lp_completion_date IS NULL
                OR (
                    (lp_circulation_start_date IS NULL
                        OR lp_completion_date >= lp_circulation_start_date)
                    AND (lp_contract_team_completion_date IS NULL
                        OR lp_completion_date >= lp_contract_team_completion_date)
                    AND (lp_junior_manager_approval_date IS NULL
                        OR lp_completion_date >= lp_junior_manager_approval_date)
                    AND (lp_senior_manager_approval_date IS NULL
                        OR lp_completion_date >= lp_senior_manager_approval_date)
                    AND (lp_gm_scm_approval_date IS NULL
                        OR lp_completion_date >= lp_gm_scm_approval_date)
                )
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_khs_items_contract_end_fully_injected
    ON khs_items(contract_end_date)
    WHERE khs_inject_completion_date IS NOT NULL;

INSERT INTO schema_migrations (version)
VALUES ('004_lp_milestones_and_contract_lifecycle')
ON CONFLICT (version) DO NOTHING;

COMMIT;
