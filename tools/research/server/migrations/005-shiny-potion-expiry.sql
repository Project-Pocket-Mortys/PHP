-- MariaDB 10.11: UTC expiry; historical accounts start inactive without a timer.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS shiny_potion_expires_at DATETIME(6) NULL DEFAULT NULL;
