<?php
// Only run inside the isolated Compose web container.
if (getenv('PM_DB_HOST') !== 'db' || getenv('PM_DB_NAME') !== 'pocket_mortys') {
    throw new RuntimeException('Research database environment required');
}
require __DIR__ . '/../../pocket_f4894h398r8h9w9er8he98he.php';
$pdo->beginTransaction();
foreach (['event_queue', 'battles', 'owned_morties', 'owned_items', 'decks', 'users', 'room_ids'] as $table) {
    $pdo->exec("DELETE FROM $table");
}
$pdo->exec("INSERT INTO room_ids (room_id, world_id, zone_id) VALUES ('test-room', 'test-world', '[1,1]')");
$stmt = $pdo->prepare('INSERT INTO users (secret, player_id, session_id, username, room_id, active_deck_id, state, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
foreach (['a', 'b'] as $id) {
    $stmt->execute(["test-secret-$id", "test-player-$id", "test-session-$id", "Test $id", 'test-room', 1, 'WORLD', '[]']);
}
$pdo->exec("INSERT INTO owned_morties (owned_morty_id, player_id, morty_id, hp, hp_stat) VALUES ('test-morty-a', 'test-player-a', 'Morty', 100, 100), ('test-morty-b', 'test-player-b', 'Morty', 100, 100)");
$pdo->exec("INSERT INTO owned_items (player_id, item_id, quantity) VALUES ('test-player-a', 'ItemMortyChip', 10)");
$pdo->exec("INSERT INTO battles (battle_id, player_id, opponent_id, player_active_morty, opponent_active_morty, opponent_morty_id, wild_morty_id, player_hp, opponent_hp, state) VALUES ('test-battle', 'test-player-a', 'test-wild', 'test-morty-a', 'test-wild-morty', 'Morty', 'Morty', 100, 100, 'ACTIVE')");
$pdo->commit();
echo "Synthetic accounts seeded\n";
