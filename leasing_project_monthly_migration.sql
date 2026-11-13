-- Leasing: explicit Project / Non-Project support + monthly reporting fields.
-- Apply to leasing_db only, AFTER leasing_mvp_schema.sql and the existing requirement-field migration.
-- Repeatable and non-destructive; review on staging and back up before production.
BEGIN;

ALTER TABLE leasing.work_items
  ADD COLUMN IF NOT EXISTS work_type TEXT NOT NULL DEFAULT 'non_project',
  ADD COLUMN IF NOT EXISTS project_name TEXT;
ALTER TABLE leasing.work_items DROP CONSTRAINT IF EXISTS work_items_work_type_check;
ALTER TABLE leasing.work_items ADD CONSTRAINT work_items_work_type_check
  CHECK (work_type IN ('project', 'non_project'));

ALTER TABLE leasing.requirements
  ADD COLUMN IF NOT EXISTS zone TEXT,
  ADD COLUMN IF NOT EXISTS site_name TEXT,
  ADD COLUMN IF NOT EXISTS postal_code TEXT,
  ADD COLUMN IF NOT EXISTS project_mrc_inet_dedicated_25 NUMERIC(18,2),
  ADD COLUMN IF NOT EXISTS project_mrc_metro_25 NUMERIC(18,2),
  ADD COLUMN IF NOT EXISTS requested_otc NUMERIC(18,2),
  ADD COLUMN IF NOT EXISTS project_notes TEXT;
ALTER TABLE leasing.requirements
  DROP CONSTRAINT IF EXISTS requirements_project_prices_nonnegative;
ALTER TABLE leasing.requirements ADD CONSTRAINT requirements_project_prices_nonnegative
  CHECK ((project_mrc_inet_dedicated_25 IS NULL OR project_mrc_inet_dedicated_25 >= 0)
     AND (project_mrc_metro_25 IS NULL OR project_mrc_metro_25 >= 0)
     AND (requested_otc IS NULL OR requested_otc >= 0));

ALTER TABLE leasing.partner_offer_lines
  ADD COLUMN IF NOT EXISTS mrc_inet_dedicated_25_amount NUMERIC(18,2),
  ADD COLUMN IF NOT EXISTS mrc_metro_25_amount NUMERIC(18,2);
ALTER TABLE leasing.negotiation_events
  ADD COLUMN IF NOT EXISTS mrc_inet_dedicated_25_amount NUMERIC(18,2),
  ADD COLUMN IF NOT EXISTS mrc_metro_25_amount NUMERIC(18,2);
ALTER TABLE leasing.negotiation_events
  DROP CONSTRAINT IF EXISTS negotiation_events_project_prices_nonnegative;
ALTER TABLE leasing.negotiation_events ADD CONSTRAINT negotiation_events_project_prices_nonnegative
  CHECK ((mrc_inet_dedicated_25_amount IS NULL OR mrc_inet_dedicated_25_amount >= 0)
     AND (mrc_metro_25_amount IS NULL OR mrc_metro_25_amount >= 0));

ALTER TABLE leasing.partner_offer_lines
  DROP CONSTRAINT IF EXISTS partner_offer_lines_project_prices_nonnegative;
ALTER TABLE leasing.partner_offer_lines ADD CONSTRAINT partner_offer_lines_project_prices_nonnegative
  CHECK ((mrc_inet_dedicated_25_amount IS NULL OR mrc_inet_dedicated_25_amount >= 0)
     AND (mrc_metro_25_amount IS NULL OR mrc_metro_25_amount >= 0));

-- Keep legacy Non-Project validations; Project rows use the site/location + commercial brief.
CREATE OR REPLACE FUNCTION leasing.validate_requirement_fields()
RETURNS TRIGGER AS $$
DECLARE
    normalized_order_type TEXT;
    item_type TEXT;
BEGIN
    SELECT COALESCE(work_type, 'non_project') INTO item_type
      FROM leasing.work_items WHERE id = NEW.work_item_id;

    IF NEW.bandwidth_unit IS NULL OR BTRIM(NEW.bandwidth_unit) = '' THEN
        NEW.bandwidth_unit := 'Mbps';
    ELSE
        NEW.bandwidth_unit := CASE LOWER(BTRIM(NEW.bandwidth_unit))
            WHEN 'mbps' THEN 'Mbps' WHEN 'gbps' THEN 'Gbps'
            WHEN 'kbps' THEN 'Kbps' WHEN 'other' THEN 'Other' ELSE NULL END;
        IF NEW.bandwidth_unit IS NULL THEN
            RAISE EXCEPTION 'Satuan harus Mbps, Gbps, Kbps, atau Other.';
        END IF;
    END IF;

    IF item_type = 'project' THEN
        IF NEW.site_name IS NULL OR BTRIM(NEW.site_name) = '' THEN
            RAISE EXCEPTION 'Site wajib diisi untuk Project.';
        END IF;
        IF NEW.address IS NULL OR BTRIM(NEW.address) = '' THEN
            RAISE EXCEPTION 'Alamat wajib diisi untuk Project.';
        END IF;
        IF NEW.latitude IS NOT NULL AND (NEW.latitude < -90 OR NEW.latitude > 90) THEN
            RAISE EXCEPTION 'Latitude di luar rentang -90 sampai 90.';
        END IF;
        IF NEW.longitude IS NOT NULL AND (NEW.longitude < -180 OR NEW.longitude > 180) THEN
            RAISE EXCEPTION 'Longitude di luar rentang -180 sampai 180.';
        END IF;
        IF NEW.project_mrc_inet_dedicated_25 < 0 OR NEW.project_mrc_metro_25 < 0 OR NEW.requested_otc < 0 THEN
            RAISE EXCEPTION 'Nilai komersial Project tidak boleh negatif.';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.order_type IS NULL OR BTRIM(NEW.order_type) = '' THEN RAISE EXCEPTION 'Jenis Order wajib diisi.'; END IF;
    IF NEW.area IS NULL OR BTRIM(NEW.area) = '' THEN RAISE EXCEPTION 'Area wajib diisi.'; END IF;
    IF NEW.address IS NULL OR BTRIM(NEW.address) = '' THEN RAISE EXCEPTION 'Alamat wajib diisi; Gedung/Kawasan bersifat opsional.'; END IF;
    IF NEW.a_end IS NULL OR BTRIM(NEW.a_end) = '' THEN RAISE EXCEPTION 'A End wajib diisi.'; END IF;
    IF NEW.bandwidth IS NULL OR NEW.bandwidth <= 0 THEN RAISE EXCEPTION 'Bandwidth wajib berupa angka lebih besar dari nol.'; END IF;
    IF NEW.service_type IS NULL OR BTRIM(NEW.service_type) = '' THEN RAISE EXCEPTION 'Jasa wajib diisi.'; END IF;
    IF NEW.special_features IS NULL OR BTRIM(NEW.special_features) = '' THEN RAISE EXCEPTION 'Fitur Khusus wajib diisi. Jika tidak ada, isi "Tidak ada".'; END IF;
    normalized_order_type := UPPER(BTRIM(REGEXP_REPLACE(COALESCE(NEW.order_type, ''), '[^A-Za-z0-9]+', ' ', 'g')));
    IF normalized_order_type NOT IN ('PSB', 'PASANG BARU', 'PASANG BARU PSB') AND (NEW.si IS NULL OR BTRIM(NEW.si) = '') THEN
        RAISE EXCEPTION 'SI wajib diisi untuk Jenis Order selain Pasang Baru (PSB).';
    END IF;
    IF NEW.existing_mrc_amount IS NOT NULL THEN
        IF NEW.existing_mrc_amount < 0 THEN RAISE EXCEPTION 'MRC Eksisting tidak boleh negatif.'; END IF;
        IF NEW.existing_mrc_currency IS NULL OR BTRIM(NEW.existing_mrc_currency) = '' THEN NEW.existing_mrc_currency := 'IDR'; END IF;
    ELSE NEW.existing_mrc_currency := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_requirements_validate_fields_insert ON leasing.requirements;
CREATE TRIGGER trg_requirements_validate_fields_insert
BEFORE INSERT ON leasing.requirements FOR EACH ROW EXECUTE FUNCTION leasing.validate_requirement_fields();
DROP TRIGGER IF EXISTS trg_requirements_validate_fields_update ON leasing.requirements;
CREATE TRIGGER trg_requirements_validate_fields_update
BEFORE UPDATE ON leasing.requirements FOR EACH ROW EXECUTE FUNCTION leasing.validate_requirement_fields();

CREATE INDEX IF NOT EXISTS idx_leasing_work_items_work_type_received_at ON leasing.work_items(work_type, received_at);
CREATE INDEX IF NOT EXISTS idx_leasing_work_items_buyer_received_at ON leasing.work_items(buyer_owner_id, received_at);
CREATE INDEX IF NOT EXISTS idx_leasing_outreaches_sent_at_partner ON leasing.partner_outreaches(sent_at, partner_id) WHERE sent_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leasing_activity_occurred_actor ON leasing.activity_events(occurred_at, actor_id);
COMMIT;
