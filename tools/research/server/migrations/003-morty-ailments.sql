-- MariaDB 10.11: additive, repeatable WORLD Morty ailment persistence.
-- Existing Morties are healthy by default; no existing values are rewritten.
ALTER TABLE owned_morties
    ADD COLUMN IF NOT EXISTS is_poisoned BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_paralysed BOOLEAN NOT NULL DEFAULT FALSE;
