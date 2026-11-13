-- Leasing site coordinates and controlled order types. Run only against leasing_db.
-- Non-destructive: adds nullable coordinates and validates future inserts/updates.
BEGIN;
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS latitude NUMERIC(9,6);
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS longitude NUMERIC(9,6);

CREATE OR REPLACE FUNCTION leasing.validate_requirement_fields()
RETURNS TRIGGER AS $$
DECLARE normalized_order_type TEXT;
BEGIN
    IF NEW.bandwidth_unit IS NULL OR BTRIM(NEW.bandwidth_unit) = '' THEN NEW.bandwidth_unit := 'Mbps'; END IF;
    NEW.bandwidth_unit := CASE LOWER(BTRIM(NEW.bandwidth_unit)) WHEN 'mbps' THEN 'Mbps' WHEN 'gbps' THEN 'Gbps' WHEN 'kbps' THEN 'Kbps' WHEN 'other' THEN 'Other' ELSE NULL END;
    IF NEW.bandwidth_unit IS NULL THEN RAISE EXCEPTION 'Satuan harus Mbps, Gbps, Kbps, atau Other.'; END IF;
    normalized_order_type := UPPER(BTRIM(REGEXP_REPLACE(COALESCE(NEW.order_type, ''), '[^A-Za-z0-9]+', ' ', 'g')));
    IF normalized_order_type IN ('PSB','PASANG BARU','PASANG BARU PSB') THEN NEW.order_type := 'PSB';
    ELSIF normalized_order_type IN ('RELOKASI','UPGRADE','DOWNGRADE','CHANGE MITRA','CHANGE SERVICE') THEN NEW.order_type := INITCAP(LOWER(BTRIM(NEW.order_type)));
    ELSE RAISE EXCEPTION 'Jenis Order harus PSB, Relokasi, Upgrade, Downgrade, Change Mitra, atau Change Service.'; END IF;
    IF NEW.area IS NULL OR BTRIM(NEW.area)='' THEN RAISE EXCEPTION 'Area wajib diisi.'; END IF;
    IF NEW.address IS NULL OR BTRIM(NEW.address)='' THEN RAISE EXCEPTION 'Alamat wajib diisi.'; END IF;
    IF NEW.a_end IS NULL OR BTRIM(NEW.a_end)='' THEN RAISE EXCEPTION 'A End wajib diisi.'; END IF;
    IF NEW.bandwidth IS NULL OR NEW.bandwidth<=0 THEN RAISE EXCEPTION 'Bandwidth harus lebih besar dari nol.'; END IF;
    IF NEW.service_type IS NULL OR BTRIM(NEW.service_type)='' THEN RAISE EXCEPTION 'Jasa wajib diisi.'; END IF;
    IF NEW.special_features IS NULL OR BTRIM(NEW.special_features)='' THEN RAISE EXCEPTION 'Fitur Khusus wajib diisi.'; END IF;
    IF NEW.order_type <> 'PSB' AND (NEW.si IS NULL OR BTRIM(NEW.si)='') THEN RAISE EXCEPTION 'SI wajib untuk selain PSB.'; END IF;
    IF NEW.latitude IS NOT NULL AND (NEW.latitude < -90 OR NEW.latitude > 90) THEN RAISE EXCEPTION 'Latitude harus antara -90 dan 90.'; END IF;
    IF NEW.longitude IS NOT NULL AND (NEW.longitude < -180 OR NEW.longitude > 180) THEN RAISE EXCEPTION 'Longitude harus antara -180 dan 180.'; END IF;
    IF NEW.existing_mrc_amount IS NOT NULL AND NEW.existing_mrc_amount < 0 THEN RAISE EXCEPTION 'MRC Eksisting tidak boleh negatif.'; END IF;
    IF NEW.existing_mrc_amount IS NOT NULL AND (NEW.existing_mrc_currency IS NULL OR BTRIM(NEW.existing_mrc_currency)='') THEN NEW.existing_mrc_currency := 'IDR'; END IF;
    IF NEW.existing_mrc_amount IS NULL THEN NEW.existing_mrc_currency := NULL; END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_requirements_validate_fields_insert ON leasing.requirements;
CREATE TRIGGER trg_requirements_validate_fields_insert BEFORE INSERT ON leasing.requirements FOR EACH ROW EXECUTE FUNCTION leasing.validate_requirement_fields();
DROP TRIGGER IF EXISTS trg_requirements_validate_fields_update ON leasing.requirements;
CREATE TRIGGER trg_requirements_validate_fields_update BEFORE UPDATE OF order_type, si, area, address, a_end, bandwidth, bandwidth_unit, service_type, special_features, existing_mrc_amount, existing_mrc_currency, latitude, longitude ON leasing.requirements FOR EACH ROW EXECUTE FUNCTION leasing.validate_requirement_fields();
COMMIT;
