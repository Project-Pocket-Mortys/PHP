-- Internal preparation data only; no native battle is activated.
CREATE TABLE IF NOT EXISTS friend_battle_party_snapshots (
    battle_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    player_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    deck_id INT NOT NULL,
    active_owned_morty_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    snapshot_json LONGTEXT NOT NULL,
    snapshot_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (battle_id,player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
