-- Internal preparation only. Public invitation acceptance remains unavailable.
CREATE TABLE IF NOT EXISTS friend_battle_sessions (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    invite_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    sender_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    recipient_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    state VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS friend_battle_memberships (
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL PRIMARY KEY,
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    INDEX battle_members (battle_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
