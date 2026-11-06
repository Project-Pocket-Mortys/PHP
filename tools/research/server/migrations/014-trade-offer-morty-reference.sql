-- MariaDB 10.11: support effective-lock projection and current reference guards.
-- No data rewrite or duplicate reservation flag/provenance table.
ALTER TABLE trade_offers
    ADD INDEX IF NOT EXISTS ix_trade_offer_morty_reference (morty_offer_id);
