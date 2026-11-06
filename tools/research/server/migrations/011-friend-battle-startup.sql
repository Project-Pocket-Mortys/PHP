-- Internal startup/readiness only: these records have no SSE dispatcher.
CREATE TABLE IF NOT EXISTS friend_battle_startups (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    started_at DATETIME(6) NOT NULL,
    ready_deadline DATETIME(6) NULL,
    sender_ready_at DATETIME(6) NULL,
    recipient_ready_at DATETIME(6) NULL,
    ready_at DATETIME(6) NULL,
    cancelled_at DATETIME(6) NULL,
    INDEX startup_deadline (ready_deadline,battle_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS friend_battle_start_intents (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    delivery_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    payload_json LONGTEXT NOT NULL,
    payload_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at DATETIME(6) NOT NULL,
    retired_at DATETIME(6) NULL,
    PRIMARY KEY (battle_id,player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
