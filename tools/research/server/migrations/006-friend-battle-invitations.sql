-- Additive invitation-only lifecycle. No human battle or player-state reservation.
CREATE TABLE IF NOT EXISTS friend_battle_invites (
    invite_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    sender_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    recipient_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    sender_token CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    recipient_token CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    state VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'PENDING',
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    INDEX sender_pending (sender_id, state, expires_at),
    INDEX recipient_pending (recipient_id, state, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
