-- Research-only liveness: one current session/room heartbeat per account.
-- Existing users and last_seen semantics are unchanged.
CREATE TABLE IF NOT EXISTS research_client_heartbeats (
    user_id INT UNSIGNED NOT NULL PRIMARY KEY,
    session_id TEXT NOT NULL,
    room_id TEXT NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_research_heartbeat_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
