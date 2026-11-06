-- Research-only stream registry. Raw authentication sessions are never persisted here.
-- Liveness is fixed at ten seconds and refreshed by authenticated polls.
CREATE TABLE IF NOT EXISTS friend_battle_streams (
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL PRIMARY KEY,
    stream_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    session_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    opened_at DATETIME(6) NOT NULL,
    heartbeat_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS friend_battle_stream_bindings (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    stream_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    session_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    bound_at DATETIME(6) NOT NULL,
    PRIMARY KEY (battle_id,player_id),
    INDEX bound_stream (player_id,stream_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Durable at-most-once publication attempt; this is not a client receipt.
CREATE TABLE IF NOT EXISTS friend_battle_start_attempts (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    delivery_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    stream_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    attempted_at DATETIME(6) NOT NULL,
    PRIMARY KEY (battle_id,player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
