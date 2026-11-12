BEGIN;

-- Track the post-LP KHS injection work separately from LP circulation.
ALTER TABLE khs_items
    ADD COLUMN IF NOT EXISTS khs_inject_start_date DATE,
    ADD COLUMN IF NOT EXISTS khs_inject_completion_date DATE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_khs_inject_start_after_lp'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_khs_inject_start_after_lp
            CHECK (
                khs_inject_start_date IS NULL
                OR (
                    lp_completion_date IS NOT NULL
                    AND khs_inject_start_date >= lp_completion_date
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_khs_inject_completion_after_start'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_khs_inject_completion_after_start
            CHECK (
                khs_inject_completion_date IS NULL
                OR (
                    khs_inject_start_date IS NOT NULL
                    AND khs_inject_completion_date >= khs_inject_start_date
                )
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_khs_items_inject_completion
    ON khs_items(khs_inject_completion_date);

-- Insert KHS Injection before the terminal Fully Injected stage.
UPDATE khs_stage_config
SET sequence_number = 13,
    stage_name = 'Fully Injected',
    is_active = TRUE
WHERE stage_code = 'COMPLETED';

INSERT INTO khs_stage_config (
    stage_code, stage_name, sequence_number, is_active
)
VALUES ('KHS_INJECTION', 'KHS Inject', 12, TRUE)
ON CONFLICT (stage_code) DO UPDATE
SET stage_name = EXCLUDED.stage_name,
    sequence_number = EXCLUDED.sequence_number,
    is_active = TRUE;

-- Keep the existing monitoring view contract while redefining completion.
CREATE OR REPLACE VIEW v_khs_monitoring AS
SELECT
    i.khs_id,
    i.request_id,
    r.request_date,
    r.request_subject,
    r.requester_owner,

    i.source_row_no,
    i.dispatch_date,
    i.executor_code,
    i.subtype,
    i.vendor_name,

    i.contract_start_date,
    i.contract_end_date,

    i.boq_confirmation_date,
    i.negotiation_date,
    i.final_negotiation_date,

    i.mi_head_approval_date,
    i.mi_sm_approval_date,
    i.mi_gm_approval_date,

    CASE
        WHEN i.mi_gm_approval_date IS NOT NULL THEN 'Completed'
        ELSE 'Not Completed'
    END AS mi_status,

    i.legal_submission_date,
    i.lp_circulation_start_date,
    i.lp_completion_date,

    CASE
        WHEN i.lp_completion_date IS NOT NULL THEN 'Completed'
        ELSE 'Not Completed'
    END AS lp_status,

    CASE
        WHEN i.khs_inject_completion_date IS NOT NULL THEN 'Fully Injected'
        WHEN i.lp_completion_date IS NOT NULL THEN 'KHS Inject'
        WHEN i.lp_circulation_start_date IS NOT NULL THEN 'LP Circulation'
        WHEN i.legal_submission_date IS NOT NULL THEN 'Legal Processing'
        WHEN i.mi_gm_approval_date IS NOT NULL THEN 'Legal Submission'
        WHEN i.mi_sm_approval_date IS NOT NULL THEN 'MI Approval - GM'
        WHEN i.mi_head_approval_date IS NOT NULL THEN 'MI Approval - SM'
        WHEN i.final_negotiation_date IS NOT NULL THEN 'MI Approval - Head'
        WHEN i.negotiation_date IS NOT NULL THEN 'Final Negotiation'
        WHEN i.boq_confirmation_date IS NOT NULL THEN 'Negotiation'
        WHEN i.dispatch_date IS NOT NULL THEN 'BOQ Confirmation'
        WHEN r.request_date IS NOT NULL THEN 'Dispatch'
        ELSE 'Request Received'
    END AS current_stage,

    CASE
        WHEN i.khs_inject_completion_date IS NOT NULL THEN 'Fully Injected'
        ELSE 'In Progress'
    END AS overall_status,

    CASE
        WHEN r.request_date IS NULL THEN NULL
        ELSE COALESCE(i.khs_inject_completion_date, CURRENT_DATE) - r.request_date
    END AS processing_days,

    i.waiting_for,
    i.waiting_reason,
    i.last_updated_date,
    i.remarks,

    i.legacy_overall_status,
    i.legacy_detailed_status,
    i.source_col_s_audit_date,
    i.migration_review,

    i.created_at,
    i.updated_at,

    i.khs_inject_start_date,
    i.khs_inject_completion_date

FROM khs_items i
JOIN khs_requests r
    ON r.request_id = i.request_id;

CREATE OR REPLACE VIEW v_khs_request_monitoring AS
SELECT
    r.request_id,
    r.request_date,
    r.request_subject,
    r.requester_owner,

    COUNT(i.khs_id) AS total_khs,

    COUNT(i.khs_id) FILTER (
        WHERE i.khs_inject_completion_date IS NOT NULL
    ) AS completed_khs,

    COUNT(i.khs_id) FILTER (
        WHERE i.khs_inject_completion_date IS NULL
    ) AS in_progress_khs,

    CASE
        WHEN COUNT(i.khs_id) = 0 THEN 'Not Started'
        WHEN COUNT(i.khs_id) FILTER (
            WHERE i.khs_inject_completion_date IS NOT NULL
        ) = COUNT(i.khs_id) THEN 'Completed'
        WHEN COUNT(i.khs_id) FILTER (
            WHERE i.khs_inject_completion_date IS NOT NULL
        ) > 0 THEN 'Partially Completed'
        ELSE 'In Progress'
    END AS request_status,

    r.created_at,
    r.updated_at

FROM khs_requests r
LEFT JOIN khs_items i
    ON i.request_id = r.request_id

GROUP BY
    r.request_id,
    r.request_date,
    r.request_subject,
    r.requester_owner,
    r.created_at,
    r.updated_at;

INSERT INTO schema_migrations (version)
VALUES ('003_khs_injection_and_evidence')
ON CONFLICT (version) DO NOTHING;

COMMIT;
