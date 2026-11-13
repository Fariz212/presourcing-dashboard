-- Leasing requirement rules update: non-destructive and repeatable.
-- Run only in leasing_db. Existing rows are retained; new and edited requirement details are validated.
BEGIN;

ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS order_type TEXT;
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS si TEXT;
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS area TEXT;
ALTER TABLE leasing.requirements ADD COLUMN IF NOT EXISTS address TEXT;

UPDATE leasing.requirements
SET bandwidth_unit = 'Mbps'
WHERE bandwidth_unit IS NULL OR BTRIM(bandwidth_unit) = '';

-- Existing records with an MRC amount but no currency follow the same IDR default.
UPDATE leasing.requirements
SET existing_mrc_currency = 'IDR'
WHERE existing_mrc_amount IS NOT NULL
  AND (existing_mrc_currency IS NULL OR BTRIM(existing_mrc_currency) = '');

ALTER TABLE leasing.requirements ALTER COLUMN bandwidth_unit SET DEFAULT 'Mbps';
ALTER TABLE leasing.requirements ALTER COLUMN bandwidth_unit SET NOT NULL;

CREATE OR REPLACE FUNCTION leasing.validate_requirement_fields()
RETURNS TRIGGER AS $$
DECLARE
    normalized_order_type TEXT;
BEGIN
    -- Empty unit is treated the same as an omitted unit.
    IF NEW.bandwidth_unit IS NULL OR BTRIM(NEW.bandwidth_unit) = '' THEN
        NEW.bandwidth_unit := 'Mbps';
    ELSE
        NEW.bandwidth_unit := CASE LOWER(BTRIM(NEW.bandwidth_unit))
            WHEN 'mbps' THEN 'Mbps'
            WHEN 'gbps' THEN 'Gbps'
            WHEN 'kbps' THEN 'Kbps'
            WHEN 'other' THEN 'Other'
            ELSE NULL
        END;
        IF NEW.bandwidth_unit IS NULL THEN
            RAISE EXCEPTION 'Satuan harus Mbps, Gbps, Kbps, atau Other.';
        END IF;
    END IF;

    IF NEW.order_type IS NULL OR BTRIM(NEW.order_type) = '' THEN
        RAISE EXCEPTION 'Jenis Order wajib diisi.';
    END IF;
    IF NEW.area IS NULL OR BTRIM(NEW.area) = '' THEN
        RAISE EXCEPTION 'Area wajib diisi.';
    END IF;
    IF NEW.address IS NULL OR BTRIM(NEW.address) = '' THEN
        RAISE EXCEPTION 'Alamat wajib diisi; Gedung/Kawasan bersifat opsional.';
    END IF;
    IF NEW.a_end IS NULL OR BTRIM(NEW.a_end) = '' THEN
        RAISE EXCEPTION 'A End wajib diisi.';
    END IF;
    IF NEW.bandwidth IS NULL OR NEW.bandwidth <= 0 THEN
        RAISE EXCEPTION 'Bandwidth wajib berupa angka lebih besar dari nol.';
    END IF;
    IF NEW.service_type IS NULL OR BTRIM(NEW.service_type) = '' THEN
        RAISE EXCEPTION 'Jasa wajib diisi.';
    END IF;
    IF NEW.special_features IS NULL OR BTRIM(NEW.special_features) = '' THEN
        RAISE EXCEPTION 'Fitur Khusus wajib diisi. Jika tidak ada, isi "Tidak ada".';
    END IF;

    normalized_order_type := UPPER(BTRIM(REGEXP_REPLACE(COALESCE(NEW.order_type, ''), '[^A-Za-z0-9]+', ' ', 'g')));
    IF normalized_order_type NOT IN ('PSB', 'PASANG BARU', 'PASANG BARU PSB')
       AND (NEW.si IS NULL OR BTRIM(NEW.si) = '') THEN
        RAISE EXCEPTION 'SI wajib diisi untuk Jenis Order selain Pasang Baru (PSB).';
    END IF;

    IF NEW.existing_mrc_amount IS NOT NULL THEN
        IF NEW.existing_mrc_amount < 0 THEN
            RAISE EXCEPTION 'MRC Eksisting tidak boleh negatif.';
        END IF;
        IF NEW.existing_mrc_currency IS NULL OR BTRIM(NEW.existing_mrc_currency) = '' THEN
            NEW.existing_mrc_currency := 'IDR';
        END IF;
    ELSE
        NEW.existing_mrc_currency := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_requirements_validate_fields_insert ON leasing.requirements;
CREATE TRIGGER trg_requirements_validate_fields_insert
BEFORE INSERT ON leasing.requirements
FOR EACH ROW EXECUTE FUNCTION leasing.validate_requirement_fields();

DROP TRIGGER IF EXISTS trg_requirements_validate_fields_update ON leasing.requirements;
CREATE TRIGGER trg_requirements_validate_fields_update
BEFORE UPDATE OF order_type, si, area, address, a_end, bandwidth, bandwidth_unit, service_type, special_features, existing_mrc_amount, existing_mrc_currency
ON leasing.requirements
FOR EACH ROW EXECUTE FUNCTION leasing.validate_requirement_fields();

COMMIT;
