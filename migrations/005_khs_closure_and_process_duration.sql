BEGIN;

ALTER TABLE khs_items
    ADD COLUMN IF NOT EXISTS process_status TEXT NOT NULL DEFAULT 'ACTIVE',
    ADD COLUMN IF NOT EXISTS closure_date DATE,
    ADD COLUMN IF NOT EXISTS closure_reason_code TEXT,
    ADD COLUMN IF NOT EXISTS closure_notes TEXT,
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS closed_by TEXT,
    ADD COLUMN IF NOT EXISTS reopened_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reopened_by TEXT,
    ADD COLUMN IF NOT EXISTS reopen_reason TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_khs_process_status'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_khs_process_status
            CHECK (process_status IN ('ACTIVE', 'NOT_PROCEEDED'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_khs_closure_reason'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_khs_closure_reason
            CHECK (
                closure_reason_code IS NULL
                OR closure_reason_code IN (
                    'NO_MUTUAL_AGREEMENT',
                    'REQUESTER_WITHDRAWAL',
                    'VENDOR_DECLINED',
                    'INTERNAL_REJECTION',
                    'DUPLICATE',
                    'OTHER'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_khs_not_proceeded_has_closure'
          AND conrelid = 'khs_items'::regclass
    ) THEN
        ALTER TABLE khs_items
            ADD CONSTRAINT chk_khs_not_proceeded_has_closure
            CHECK (
                process_status <> 'NOT_PROCEEDED'
                OR (
                    closure_date IS NOT NULL
                    AND closure_reason_code IS NOT NULL
                    AND closed_at IS NOT NULL
                )
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_khs_items_process_status
    ON khs_items(process_status);

INSERT INTO khs_stage_config (
    stage_code, stage_name, sequence_number, is_active
)
VALUES ('NOT_PROCEEDED', 'Not Proceeded', 14, TRUE)
ON CONFLICT (stage_code) DO UPDATE
SET stage_name = EXCLUDED.stage_name,
    sequence_number = EXCLUDED.sequence_number,
    is_active = TRUE;

INSERT INTO schema_migrations (version)
VALUES ('005_khs_closure_and_process_duration')
ON CONFLICT (version) DO NOTHING;

COMMIT;
