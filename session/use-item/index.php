<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../lib/healing_items.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    respond(405, ['error' => ['code' => 'FAILED']]);
}
$body = json_decode(file_get_contents('php://input'), true);
foreach (['session_id', 'owned_morty_id', 'item_id'] as $field) {
    if (!is_array($body) || !is_string($body[$field] ?? null) || $body[$field] === '') {
        respond(400, ['error' => ['code' => 'FAILED']]);
    }
}
$effects = morty_healing_items();
if (!array_key_exists($body['item_id'], $effects)
    && !in_array($body['item_id'], ['ItemPureHalzinger', 'ItemPurePlutonicRock'], true)) {
    respond(400, ['error' => ['code' => 'FAILED']]);
}

try {
    $pdo->beginTransaction();
    $query = $pdo->prepare('SELECT player_id, state FROM users WHERE session_id = ? LIMIT 1 FOR UPDATE');
    $query->execute([$body['session_id']]);
    $user = $query->fetch();
    if (!$user) {
        $pdo->rollBack();
        respond(401, ['error' => ['code' => 'FAILED']]);
    }
    // Party item use is separate from battle turns, which hold their own HP.
    $query = $pdo->prepare("SELECT battle_id FROM battles WHERE player_id = ? AND state = 'ACTIVE' LIMIT 1");
    $query->execute([$user['player_id']]);
    if ($user['state'] !== 'WORLD' || $query->fetchColumn()) {
        $pdo->rollBack();
        respond(409, ['error' => ['code' => 'FAILED']]);
    }
    $query = $pdo->prepare('SELECT * FROM owned_morties WHERE player_id = ? AND owned_morty_id = ? FOR UPDATE');
    $query->execute([$user['player_id'], $body['owned_morty_id']]);
    $morties = $query->fetchAll();
    if (count($morties) !== 1) {
        $pdo->rollBack();
        respond(404, ['error' => ['code' => 'FAILED']]);
    }
    $morty = $morties[0];
    $query = $pdo->prepare('SELECT id, quantity FROM owned_items WHERE player_id = ? AND item_id = ? FOR UPDATE');
    $query->execute([$user['player_id'], $body['item_id']]);
    $items = $query->fetchAll();
    // The existing schema permits duplicates. Ambiguous inventory is not charged.
    $stock = count($items) === 1 ? item_nonnegative_integer($items[0]['quantity']) : null;
    if ($stock === null || $stock <= 0) {
        $pdo->rollBack();
        respond(409, ['error' => ['code' => 'FAILED']]);
    }
    $attacks = [];
    if ($body['item_id'] === 'ItemPurePlutonicRock') {
        $query = $pdo->prepare('SELECT id, attack_id, pp, pp_stat FROM owned_attacks WHERE owned_morty_id = ? FOR UPDATE');
        $query->execute([$body['owned_morty_id']]);
        $attacks = $query->fetchAll();
    }
    $plan = morty_item_effect_plan($body['item_id'], $morty, $attacks);
    if ($plan === null) {
        $pdo->rollBack();
        respond(409, ['error' => ['code' => 'FAILED']]);
    }
    $quantity = $stock - 1;
    if ($body['item_id'] !== 'ItemPurePlutonicRock') {
        $morty['hp'] = $plan['hp'];
        $query = $pdo->prepare('UPDATE owned_morties SET hp = ? WHERE id = ? AND player_id = ?');
        $query->execute([$morty['hp'], $morty['id'], $user['player_id']]);
    }
    if ($plan['attacks']) {
        $query = $pdo->prepare('UPDATE owned_attacks SET pp = ?, pp_stat = ? WHERE id = ? AND owned_morty_id = ?');
        foreach ($plan['attacks'] as $attack) {
            $query->execute([$attack['pp'], $attack['pp'], $attack['id'], $body['owned_morty_id']]);
        }
    }
    $query = $pdo->prepare('UPDATE owned_items SET quantity = ? WHERE id = ? AND player_id = ?');
    $query->execute([$quantity, $items[0]['id'], $user['player_id']]);
    $updated = item_updated_morty($pdo, $morty);
    $pdo->commit();
    respond(200, [
        'owned_morty_id' => $body['owned_morty_id'],
        'item_id' => $body['item_id'],
        'is_success' => true,
        'effect_value' => $plan['effect_value'],
        'owned_morties' => [$updated],
        // Zero is needed to clear the consumed item in the client's merge path.
        'owned_items' => [['item_id' => $body['item_id'], 'quantity' => $quantity]],
        'attacks_to_learn' => [],
    ]);
} catch (Throwable $error) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    error_log('Morty item use failed: ' . get_class($error));
    respond(500, ['error' => ['code' => 'FAILED']]);
}
