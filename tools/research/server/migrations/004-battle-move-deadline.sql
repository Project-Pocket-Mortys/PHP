-- MariaDB 10.11: nullable UTC selection deadline; historical battles stay unarmed.
ALTER TABLE battles
    ADD COLUMN IF NOT EXISTS move_deadline DATETIME(6) NULL DEFAULT NULL,
    ADD INDEX IF NOT EXISTS ix_battle_move_deadline (state, move_deadline);
