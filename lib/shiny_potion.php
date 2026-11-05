<?php
declare(strict_types=1);

/** UTC expiry is durable; expiration needs no write or background worker. */
function shiny_potion_state(PDO $pdo, string $playerId): ?array {
    $query = $pdo->prepare("SELECT
        shiny_potion_expires_at > UTC_TIMESTAMP(6) AS is_active,
        DATE_FORMAT(shiny_potion_expires_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS end_usage_time
        FROM users WHERE player_id = ? ORDER BY id");
    $query->execute([$playerId]);
    $rows = $query->fetchAll(PDO::FETCH_ASSOC);
    if (count($rows) !== 1 || !(bool)$rows[0]['is_active']) return null;
    $row = $rows[0];
    // SetupFromDict consumes a dictionary array and parses its first end time.
    return [['end_usage_time' => (string)$row['end_usage_time']]];
}

/** Raw startup DateTime.Parse uses local conversion for Z, then compares UTC
 * ticks without normalization. Keep UTC wall time here; typed use responses
 * retain their UTC suffix. Both forms describe the same persisted deadline.
 */
function shiny_potion_startup_state(PDO $pdo, string $playerId): ?array {
    $state = shiny_potion_state($pdo, $playerId);
    if ($state !== null) {
        $state[0]['end_usage_time'] = substr($state[0]['end_usage_time'], 0, -1);
    }
    return $state;
}
