-- Internal recipient projections only; does not activate or publish a battle.
ALTER TABLE friend_battle_sessions ADD COLUMN IF NOT EXISTS start_views_created_at DATETIME(6) NULL;

CREATE TABLE IF NOT EXISTS friend_battle_start_views (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    context_json LONGTEXT NOT NULL,
    context_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    view_json LONGTEXT NOT NULL,
    view_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (battle_id,player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
