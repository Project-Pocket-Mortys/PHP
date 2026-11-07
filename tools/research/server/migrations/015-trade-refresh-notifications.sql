-- Replacement account-global invalidation, not an original-server event log.
-- One row per affected account; native handlers reload authoritative state.
CREATE TABLE IF NOT EXISTS trade_refresh_notifications (
    player_id VARBINARY(255) NOT NULL,
    revision BIGINT UNSIGNED NOT NULL,
    event_name VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    PRIMARY KEY (player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
