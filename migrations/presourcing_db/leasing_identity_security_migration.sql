-- Apply to presourcing_db (NOT leasing_db) before deploying the hardened auth code.
BEGIN;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS password_must_change BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ;
-- The application lazily hashes legacy passwords after successful login. New accounts store no plaintext.
ALTER TABLE public.users ALTER COLUMN password DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_public_users_username ON public.users (username);
COMMIT;
