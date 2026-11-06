-- First initial ATTACK queue only: no combat resolution, resource writes or new lease.
-- The startup anchor prevents deletion of all selections from permitting recapture.
ALTER TABLE friend_battle_startups ADD COLUMN IF NOT EXISTS selection_started_at DATETIME(6) NULL;

CREATE TABLE IF NOT EXISTS friend_battle_selections (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    selection_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
    selection_json LONGTEXT NOT NULL,
    selection_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at DATETIME(6) NOT NULL,
    retired_at DATETIME(6) NULL,
    PRIMARY KEY (battle_id,player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS friend_battle_selection_pairs (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    sender_selection_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    recipient_selection_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    paired_at DATETIME(6) NOT NULL,
    retired_at DATETIME(6) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
