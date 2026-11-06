<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../lib/shiny_potion.php';
require_once __DIR__ . '/../../lib/world_action_guard.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    respond(405, ['error' => ['code' => 'UNKNOWN']]);
}
$body = json_decode(file_get_contents('php://input'), true);
// The native account item method has only a session_id argument.
if (!is_array($body) || count($body) !== 1
    || !is_string($body['session_id'] ?? null) || $body['session_id'] === '') {
    respond(400, ['error' => ['code' => 'UNKNOWN']]);
}

try {
    $pdo->beginTransaction();
    $query = $pdo->prepare('SELECT id, player_id, state FROM users WHERE session_id = ? ORDER BY id FOR UPDATE');
    $query->execute([$body['session_id']]);
    $users = $query->fetchAll(PDO::FETCH_ASSOC);
    if (count($users) !== 1) {
        $pdo->rollBack();
        respond(401, ['error' => ['code' => 'UNKNOWN']]);
    }
    $user = $users[0];
    $playerId = (string)$user['player_id'];
    $query = $pdo->prepare('SELECT id FROM users WHERE player_id = ? ORDER BY id FOR UPDATE');
    $query->execute([$playerId]);
    $owners = $query->fetchAll(PDO::FETCH_ASSOC);
    if (count($owners) !== 1 || (int)$owners[0]['id'] !== (int)$user['id']) {
        $pdo->rollBack();
        respond(409, ['error' => ['code' => 'UNKNOWN']]);
    }
    if ($user['state'] !== 'WORLD' || world_action_has_active_battle($pdo, $playerId)) {
        $pdo->rollBack();
        respond(409, ['error' => ['code' => 'UNKNOWN']]);
    }
    if (shiny_potion_state($pdo, $playerId) !== null) {
        $pdo->rollBack();
        respond(409, ['error' => ['code' => 'ALREADY_ACTIVE_SHINY_POTION']]);
    }
    $query = $pdo->prepare("SELECT id, quantity FROM owned_items
        WHERE player_id = ? AND item_id = 'ItemShinyPotion' FOR UPDATE");
    $query->execute([$playerId]);
    $items = $query->fetchAll(PDO::FETCH_ASSOC);
    // Historical inventory has no unique constraint; never charge ambiguous rows.
    $stock = count($items) === 1
        ? filter_var($items[0]['quantity'], FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]])
        : false;
    if ($stock === false) {
        $pdo->rollBack();
        respond(409, ['error' => ['code' => 'NOT_ENOUGH_SHINY_POTIONS']]);
    }
    $quantity = $stock - 1;
    // Use the database UTC clock for both the two-hour duration and active checks.
    $query = $pdo->prepare('UPDATE users SET shiny_potion_expires_at = UTC_TIMESTAMP(6) + INTERVAL 2 HOUR WHERE id = ? AND player_id = ?');
    $query->execute([$user['id'], $playerId]);
    $query = $pdo->prepare('UPDATE owned_items SET quantity = ? WHERE id = ? AND player_id = ?');
    $query->execute([$quantity, $items[0]['id'], $playerId]);
    $state = shiny_potion_state($pdo, $playerId);
    $pdo->commit();
    respond(200, [
        'quantity' => $quantity,
        'shiny_potion_active' => true,
        'end_usage_time' => $state[0]['end_usage_time'],
        'shiny_potion_item_id' => 'ItemShinyPotion',
    ]);
} catch (Throwable $error) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    error_log('Shiny Potion use failed: ' . get_class($error));
    respond(500, ['error' => ['code' => 'UNKNOWN']]);
}
