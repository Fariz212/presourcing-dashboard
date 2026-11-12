BEGIN;

ALTER TABLE khs_import_batches
    ADD COLUMN IF NOT EXISTS unchanged_requests INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS unchanged_items INTEGER NOT NULL DEFAULT 0;

ALTER TABLE khs_import_rows
    ADD COLUMN IF NOT EXISTS change_type TEXT NOT NULL DEFAULT 'NEW';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_import_change_type'
          AND conrelid = 'khs_import_rows'::regclass
    ) THEN
        ALTER TABLE khs_import_rows
            ADD CONSTRAINT chk_import_change_type
            CHECK (
                change_type IN (
                    'NEW',
                    'UPDATED',
                    'UNCHANGED'
                )
            );
    END IF;
END
$$;

INSERT INTO schema_migrations (version)
VALUES ('002_import_change_classification')
ON CONFLICT (version) DO NOTHING;

COMMIT;
