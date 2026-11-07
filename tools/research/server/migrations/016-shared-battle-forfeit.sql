-- Research-only initial PvF RUN. Publication attempts are not client receipts.
CREATE TABLE IF NOT EXISTS friend_battle_forfeits (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    decision_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    owned_morty_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    decision_json LONGTEXT NOT NULL,
    decision_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    decided_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS friend_battle_terminal_intents (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    delivery_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    payload_json LONGTEXT NOT NULL,
    payload_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at DATETIME(6) NOT NULL,
    -- Survives deletion of an attempt row; missing history must never redeliver.
    attempted_at DATETIME(6) NULL,
    PRIMARY KEY (battle_id,player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS friend_battle_terminal_attempts (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    delivery_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    stream_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    attempted_at DATETIME(6) NOT NULL,
    PRIMARY KEY (battle_id,player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
