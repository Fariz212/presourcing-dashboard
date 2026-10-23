-- Leasing multi-site/project, service-specific MRC, and safe grouping extension.
-- Apply ONLY to leasing_db after a database backup. Repeatable/non-destructive.
BEGIN;

-- Work Item type is the grouping boundary: Project owns many sites; Non-Project is a normal request.
ALTER TABLE leasing.work_items ADD COLUMN IF NOT EXISTS work_type TEXT DEFAULT 'non_project';
ALTER TABLE leasing.work_items ADD COLUMN IF NOT EXISTS project_name TEXT;
UPDATE leasing.work_items
SET work_type = CASE
    WHEN LOWER(BTRIM(COALESCE(work_type, ''))) IN ('project', 'proyek') THEN 'project'
    ELSE 'non_project'
END
WHERE work_type IS NULL OR BTRIM(work_type) = '' OR LOWER(BTRIM(work_type)) NOT IN ('project', 'non_project');
ALTER TABLE leasing.work_items ALTER COLUMN work_type SET DEFAULT 'non_project';
ALTER TABLE leasing.work_items ALTER COLUMN work_type SET NOT NULL;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='leasing_work_items_work_type_check') THEN
        ALTER TABLE leasing.work_items ADD CONSTRAINT leasing_work_items_work_type_check
            CHECK (work_type IN ('project','non_project')) NOT VALID;
    END IF;
END $$;

-- Multi-site attributes. Existing values remain intact.
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS external_reference TEXT;
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS zone TEXT;
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS site_name TEXT;
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS postal_code TEXT;
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS latitude NUMERIC(9,6);
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS longitude NUMERIC(9,6);
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS project_mrc_inet_dedicated_25 NUMERIC(18,2);
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS project_mrc_metro_25 NUMERIC(18,2);
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS requested_otc NUMERIC(18,2);
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS project_notes TEXT;

-- One site can request Internet Dedicated and Metro E together while each service keeps its own MRC.
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS existing_mrc_inet_dedicated_25_amount NUMERIC(18,2);
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS existing_mrc_metro_25_amount NUMERIC(18,2);

-- Supplier and negotiation prices are captured separately for each service type.
ALTER TABLE leasing.partner_offer_lines ADD COLUMN IF NOT EXISTS mrc_inet_dedicated_25_amount NUMERIC(18,2);
ALTER TABLE leasing.partner_offer_lines ADD COLUMN IF NOT EXISTS mrc_metro_25_amount NUMERIC(18,2);
ALTER TABLE leasing.negotiation_events ADD COLUMN IF NOT EXISTS mrc_inet_dedicated_25_amount NUMERIC(18,2);
ALTER TABLE leasing.negotiation_events ADD COLUMN IF NOT EXISTS mrc_metro_25_amount NUMERIC(18,2);

-- Guard against negative specialized price values at the database boundary as well as in the UI/API.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='leasing_requirements_project_prices_nonnegative') THEN
        ALTER TABLE leasing.requirements ADD CONSTRAINT leasing_requirements_project_prices_nonnegative
            CHECK ((project_mrc_inet_dedicated_25 IS NULL OR project_mrc_inet_dedicated_25 >= 0)
               AND (project_mrc_metro_25 IS NULL OR project_mrc_metro_25 >= 0)
               AND (requested_otc IS NULL OR requested_otc >= 0)
               AND (existing_mrc_inet_dedicated_25_amount IS NULL OR existing_mrc_inet_dedicated_25_amount >= 0)
               AND (existing_mrc_metro_25_amount IS NULL OR existing_mrc_metro_25_amount >= 0)) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='leasing_partner_offer_prices_nonnegative') THEN
        ALTER TABLE leasing.partner_offer_lines ADD CONSTRAINT leasing_partner_offer_prices_nonnegative
            CHECK ((mrc_inet_dedicated_25_amount IS NULL OR mrc_inet_dedicated_25_amount >= 0)
               AND (mrc_metro_25_amount IS NULL OR mrc_metro_25_amount >= 0)) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='leasing_negotiation_prices_nonnegative') THEN
        ALTER TABLE leasing.negotiation_events ADD CONSTRAINT leasing_negotiation_prices_nonnegative
            CHECK ((mrc_inet_dedicated_25_amount IS NULL OR mrc_inet_dedicated_25_amount >= 0)
               AND (mrc_metro_25_amount IS NULL OR mrc_metro_25_amount >= 0)) NOT VALID;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_leasing_requirements_work_item_no
    ON leasing.requirements (work_item_id, requirement_no);
CREATE INDEX IF NOT EXISTS idx_leasing_requirements_external_reference
    ON leasing.requirements (external_reference) WHERE external_reference IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leasing_partner_offer_lines_requirement
    ON leasing.partner_offer_lines (requirement_id, offer_id);

-- Project site rows do not require Non-Project fields (A-End, bandwidth, order type, etc.).
-- Preserve one record per site, and keep existing MRC currency when only service-specific MRC exists.
CREATE OR REPLACE FUNCTION leasing.validate_requirement_fields()
RETURNS TRIGGER AS $$
DECLARE
    normalized_order_type TEXT;
    parent_work_type TEXT;
    has_existing_price BOOLEAN;
BEGIN
    SELECT LOWER(BTRIM(COALESCE(NULLIF(w.work_type, ''), 'non_project')))
      INTO parent_work_type
      FROM leasing.work_items w
     WHERE w.id = NEW.work_item_id;
    parent_work_type := COALESCE(parent_work_type, 'non_project');

    -- Project: one row is one site and can carry several requested services/prices.
    IF parent_work_type = 'project' THEN
        IF NEW.site_name IS NULL OR BTRIM(NEW.site_name) = '' THEN
            RAISE EXCEPTION 'Site wajib diisi untuk Project.';
        END IF;
        IF NEW.address IS NULL OR BTRIM(NEW.address) = '' THEN
            RAISE EXCEPTION 'Alamat wajib diisi untuk Project.';
        END IF;
        IF NEW.area IS NULL OR BTRIM(NEW.area) = '' THEN
            NEW.area := COALESCE(NULLIF(BTRIM(NEW.zone), ''), 'Project');
        END IF;
        IF NEW.latitude IS NOT NULL AND (NEW.latitude < -90 OR NEW.latitude > 90) THEN
            RAISE EXCEPTION 'Latitude harus antara -90 dan 90.';
        END IF;
        IF NEW.longitude IS NOT NULL AND (NEW.longitude < -180 OR NEW.longitude > 180) THEN
            RAISE EXCEPTION 'Longitude harus antara -180 dan 180.';
        END IF;
        IF NEW.project_mrc_inet_dedicated_25 IS NOT NULL AND NEW.project_mrc_inet_dedicated_25 < 0 THEN
            RAISE EXCEPTION 'Target MRC Internet Dedicated tidak boleh negatif.';
        END IF;
        IF NEW.project_mrc_metro_25 IS NOT NULL AND NEW.project_mrc_metro_25 < 0 THEN
            RAISE EXCEPTION 'Target MRC Metro E tidak boleh negatif.';
        END IF;
        IF NEW.requested_otc IS NOT NULL AND NEW.requested_otc < 0 THEN
            RAISE EXCEPTION 'Target OTC tidak boleh negatif.';
        END IF;
        IF NEW.bandwidth_unit IS NULL OR BTRIM(NEW.bandwidth_unit) = '' THEN NEW.bandwidth_unit := 'Mbps'; END IF;
        RETURN NEW;
    END IF;

    -- Non-Project: detailed service request validation.
    IF NEW.bandwidth_unit IS NULL OR BTRIM(NEW.bandwidth_unit) = '' THEN
        NEW.bandwidth_unit := 'Mbps';
    ELSE
        NEW.bandwidth_unit := CASE LOWER(BTRIM(NEW.bandwidth_unit))
            WHEN 'mbps' THEN 'Mbps' WHEN 'gbps' THEN 'Gbps' WHEN 'kbps' THEN 'Kbps'
            WHEN 'other' THEN 'Other' ELSE NULL END;
        IF NEW.bandwidth_unit IS NULL THEN RAISE EXCEPTION 'Satuan harus Mbps, Gbps, Kbps, atau Other.'; END IF;
    END IF;
    IF NEW.order_type IS NULL OR BTRIM(NEW.order_type) = '' THEN RAISE EXCEPTION 'Jenis Order wajib diisi.'; END IF;
    IF NEW.area IS NULL OR BTRIM(NEW.area) = '' THEN RAISE EXCEPTION 'Area wajib diisi.'; END IF;
    IF NEW.address IS NULL OR BTRIM(NEW.address) = '' THEN RAISE EXCEPTION 'Alamat wajib diisi.'; END IF;
    IF NEW.a_end IS NULL OR BTRIM(NEW.a_end) = '' THEN RAISE EXCEPTION 'A End wajib diisi.'; END IF;
    IF NEW.bandwidth IS NULL OR NEW.bandwidth <= 0 THEN RAISE EXCEPTION 'Bandwidth harus lebih besar dari nol.'; END IF;
    IF NEW.service_type IS NULL OR BTRIM(NEW.service_type) = '' THEN RAISE EXCEPTION 'Jasa wajib diisi.'; END IF;
    IF NEW.special_features IS NULL OR BTRIM(NEW.special_features) = '' THEN RAISE EXCEPTION 'Fitur Khusus wajib diisi. Jika tidak ada, isi "Tidak ada".'; END IF;

    normalized_order_type := UPPER(BTRIM(REGEXP_REPLACE(COALESCE(NEW.order_type, ''), '[^A-Za-z0-9]+', ' ', 'g')));
    IF normalized_order_type IN ('PSB','PASANG BARU','PASANG BARU PSB') THEN NEW.order_type := 'PSB';
    ELSIF normalized_order_type IN ('RELOKASI','UPGRADE','DOWNGRADE','CHANGE MITRA','CHANGE SERVICE') THEN
        NEW.order_type := INITCAP(LOWER(BTRIM(NEW.order_type)));
    ELSE
        RAISE EXCEPTION 'Jenis Order harus PSB, Relokasi, Upgrade, Downgrade, Change Mitra, atau Change Service.';
    END IF;
    IF NEW.order_type <> 'PSB' AND (NEW.si IS NULL OR BTRIM(NEW.si) = '') THEN
        RAISE EXCEPTION 'SI wajib untuk selain PSB.';
    END IF;
    IF NEW.latitude IS NOT NULL AND (NEW.latitude < -90 OR NEW.latitude > 90) THEN RAISE EXCEPTION 'Latitude harus antara -90 dan 90.'; END IF;
    IF NEW.longitude IS NOT NULL AND (NEW.longitude < -180 OR NEW.longitude > 180) THEN RAISE EXCEPTION 'Longitude harus antara -180 dan 180.'; END IF;
    IF NEW.existing_mrc_amount IS NOT NULL AND NEW.existing_mrc_amount < 0 THEN RAISE EXCEPTION 'MRC Eksisting tidak boleh negatif.'; END IF;
    IF NEW.existing_mrc_inet_dedicated_25_amount IS NOT NULL AND NEW.existing_mrc_inet_dedicated_25_amount < 0 THEN RAISE EXCEPTION 'MRC Existing Internet Dedicated tidak boleh negatif.'; END IF;
    IF NEW.existing_mrc_metro_25_amount IS NOT NULL AND NEW.existing_mrc_metro_25_amount < 0 THEN RAISE EXCEPTION 'MRC Existing Metro E tidak boleh negatif.'; END IF;

    has_existing_price := NEW.existing_mrc_amount IS NOT NULL
        OR NEW.existing_mrc_inet_dedicated_25_amount IS NOT NULL
        OR NEW.existing_mrc_metro_25_amount IS NOT NULL;
    IF has_existing_price THEN
        NEW.existing_mrc_currency := UPPER(BTRIM(COALESCE(NULLIF(NEW.existing_mrc_currency, ''), 'IDR')));
        IF NEW.existing_mrc_currency !~ '^[A-Z]{3}$' THEN RAISE EXCEPTION 'Currency MRC harus kode 3 huruf.'; END IF;
    ELSE
        NEW.existing_mrc_currency := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_requirements_validate_fields_insert ON leasing.requirements;
DROP TRIGGER IF EXISTS trg_requirements_validate_fields_update ON leasing.requirements;
DROP TRIGGER IF EXISTS trg_requirements_validate_fields ON leasing.requirements;
CREATE TRIGGER trg_requirements_validate_fields
BEFORE INSERT OR UPDATE ON leasing.requirements
FOR EACH ROW EXECUTE FUNCTION leasing.validate_requirement_fields();

COMMIT;
