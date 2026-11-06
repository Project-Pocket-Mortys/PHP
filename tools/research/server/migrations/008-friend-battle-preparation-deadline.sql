-- Historical NULL deadlines are preserved; do not guess a lease for old rows.
ALTER TABLE friend_battle_sessions
    ADD COLUMN IF NOT EXISTS prepare_deadline DATETIME(6) NULL DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(32) NULL DEFAULT NULL;
CREATE INDEX IF NOT EXISTS prepare_due ON friend_battle_sessions (state, prepare_deadline, battle_id);
