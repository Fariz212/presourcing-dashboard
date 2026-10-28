-- Idempotent compatibility backfill for historic site-level offers into the
-- service-agnostic coverage model. Apply ONLY after leasing_scale_hardening_migration.sql
-- has been successfully applied to schema leasing in leasing_db.
--
-- This migration intentionally does not assign an unscoped OTC/MRC amount to multiple
-- services. Ambiguous legacy quotes remain available in the legacy commercial table/report.
BEGIN;

DO $$
BEGIN
    IF to_regclass('leasing.partner_offer_service_lines') IS NULL THEN
        RAISE EXCEPTION 'Missing leasing.partner_offer_service_lines. Apply leasing_scale_hardening_migration.sql first.';
    END IF;
    IF to_regclass('leasing.partner_offer_lines') IS NULL OR to_regclass('leasing.requirements') IS NULL THEN
        RAISE EXCEPTION 'Required Leasing tables are missing; apply the Leasing MVP and prerequisite migrations first.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='leasing' AND table_name='partner_offer_lines' AND column_name='mrc_inet_dedicated_25_amount')
       OR NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='leasing' AND table_name='partner_offer_lines' AND column_name='mrc_metro_25_amount') THEN
        RAISE EXCEPTION 'Legacy MRC columns are missing. Verify the Project pricing migration before applying this backfill.';
    END IF;
END $$;

-- Map legacy service-specific MRCs to the corresponding requested service when present.
-- If not explicitly requested, preserve the legacy service label as an offer-only service row.
WITH normalized AS (
    SELECT r.id AS requirement_id,
           CASE
             WHEN COALESCE(array_length(r.requested_services, 1), 0) > 0 THEN r.requested_services
             ELSE ARRAY(
               SELECT BTRIM(part)
               FROM regexp_split_to_table(COALESCE(r.service_type, ''), E'[;|\\n\\r]+') AS part
               WHERE BTRIM(part) <> ''
             )::TEXT[]
           END AS services
    FROM leasing.requirements r
)
INSERT INTO leasing.partner_offer_service_lines
    (offer_id, requirement_id, service_name, feasibility_status, mrc_amount, otc_amount, currency, notes, created_at)
SELECT pol.offer_id, pol.requirement_id,
       COALESCE((SELECT BTRIM(svc) FROM unnest(n.services) AS svc
                 WHERE LOWER(BTRIM(svc))='internet dedicated' LIMIT 1), 'Internet Dedicated'),
       'can_provide', pol.mrc_inet_dedicated_25_amount, NULL,
       UPPER(BTRIM(pol.currency::TEXT)), pol.notes, pol.created_at
FROM leasing.partner_offer_lines pol
JOIN normalized n ON n.requirement_id=pol.requirement_id
WHERE pol.mrc_inet_dedicated_25_amount IS NOT NULL
  AND UPPER(BTRIM(COALESCE(pol.currency::TEXT,''))) ~ '^[A-Z]{3}$'
ON CONFLICT DO NOTHING;

WITH normalized AS (
    SELECT r.id AS requirement_id,
           CASE
             WHEN COALESCE(array_length(r.requested_services, 1), 0) > 0 THEN r.requested_services
             ELSE ARRAY(
               SELECT BTRIM(part)
               FROM regexp_split_to_table(COALESCE(r.service_type, ''), E'[;|\\n\\r]+') AS part
               WHERE BTRIM(part) <> ''
             )::TEXT[]
           END AS services
    FROM leasing.requirements r
)
INSERT INTO leasing.partner_offer_service_lines
    (offer_id, requirement_id, service_name, feasibility_status, mrc_amount, otc_amount, currency, notes, created_at)
SELECT pol.offer_id, pol.requirement_id,
       COALESCE((SELECT BTRIM(svc) FROM unnest(n.services) AS svc
                 WHERE LOWER(BTRIM(svc))='metro e' LIMIT 1), 'Metro E'),
       'can_provide', pol.mrc_metro_25_amount, NULL,
       UPPER(BTRIM(pol.currency::TEXT)), pol.notes, pol.created_at
FROM leasing.partner_offer_lines pol
JOIN normalized n ON n.requirement_id=pol.requirement_id
WHERE pol.mrc_metro_25_amount IS NOT NULL
  AND UPPER(BTRIM(COALESCE(pol.currency::TEXT,''))) ~ '^[A-Z]{3}$'
ON CONFLICT DO NOTHING;

-- For a genuinely single-service request, the old generic MRC/OTC can be mapped safely.
-- For multi-service requests, do NOT copy the same unscoped price to every service.
WITH normalized AS (
    SELECT r.id AS requirement_id,
           CASE
             WHEN COALESCE(array_length(r.requested_services, 1), 0) > 0 THEN r.requested_services
             ELSE ARRAY(
               SELECT BTRIM(part)
               FROM regexp_split_to_table(COALESCE(r.service_type, ''), E'[;|\\n\\r]+') AS part
               WHERE BTRIM(part) <> ''
             )::TEXT[]
           END AS services
    FROM leasing.requirements r
)
INSERT INTO leasing.partner_offer_service_lines
    (offer_id, requirement_id, service_name, feasibility_status, mrc_amount, otc_amount, currency, notes, created_at)
SELECT pol.offer_id, pol.requirement_id, BTRIM(n.services[1]),
       CASE WHEN pol.mrc_amount IS NOT NULL OR pol.otc_amount IS NOT NULL THEN 'can_provide'
            WHEN pol.feasibility_status IN ('can_provide','cannot_provide','needs_clarification') THEN pol.feasibility_status
            ELSE 'needs_clarification' END,
       pol.mrc_amount, pol.otc_amount,
       CASE WHEN pol.mrc_amount IS NOT NULL OR pol.otc_amount IS NOT NULL
            THEN UPPER(BTRIM(pol.currency::TEXT)) ELSE NULL END,
       pol.notes, pol.created_at
FROM leasing.partner_offer_lines pol
JOIN normalized n ON n.requirement_id=pol.requirement_id
WHERE CARDINALITY(n.services)=1
  AND (pol.mrc_amount IS NOT NULL OR pol.otc_amount IS NOT NULL
       OR pol.feasibility_status IN ('can_provide','cannot_provide','needs_clarification')
       OR NULLIF(BTRIM(COALESCE(pol.notes,'')), '') IS NOT NULL)
  AND ((pol.mrc_amount IS NULL AND pol.otc_amount IS NULL)
       OR UPPER(BTRIM(COALESCE(pol.currency::TEXT,''))) ~ '^[A-Z]{3}$')
  AND NOT EXISTS (
      SELECT 1 FROM leasing.partner_offer_service_lines existing
      WHERE existing.offer_id=pol.offer_id
        AND existing.requirement_id=pol.requirement_id
        AND LOWER(BTRIM(existing.service_name))=LOWER(BTRIM(n.services[1]))
  )
ON CONFLICT DO NOTHING;

COMMIT;
