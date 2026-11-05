-- MariaDB 10.11 (the pinned research database): repeatable, additive migration.
-- Run before deploying handlers that read this column. Existing memberships
-- start at generation zero; no account, session, room or cursor is rewritten.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS room_membership_generation BIGINT UNSIGNED NOT NULL DEFAULT 0;
