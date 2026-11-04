<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../../../pocket_f4894h398r8h9w9er8he98he.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    respond(405, ['error' => ['code' => 'FAILED']]);
}
$body = json_decode(file_get_contents('php://input'), true);
if (!is_array($body)
    || !is_string($body['session_id'] ?? null) || $body['session_id'] === ''
    || !is_string($body['owned_morty_id'] ?? null) || $body['owned_morty_id'] === ''
    || !is_bool($body['is_locked'] ?? null)) {
    respond(400, ['error' => ['code' => 'FAILED']]);
}

try {
    $pdo->beginTransaction();
    $query = $pdo->prepare('SELECT player_id, active_deck_id FROM users WHERE session_id = ? LIMIT 1 FOR UPDATE');
    $query->execute([$body['session_id']]);
    $user = $query->fetch();
    if (!$user) {
        $pdo->rollBack();
        respond(401, ['error' => ['code' => 'FAILED']]);
    }
    $query = $pdo->prepare('SELECT id FROM owned_morties WHERE player_id = ? AND owned_morty_id = ? FOR UPDATE');
    $query->execute([$user['player_id'], $body['owned_morty_id']]);
    if (!$query->fetch()) {
        $pdo->rollBack();
        respond(404, ['error' => ['code' => 'OWNED_MORTY_ID_INVALID']]);
    }
    $query = $pdo->prepare('UPDATE owned_morties SET is_locked = ? WHERE player_id = ? AND owned_morty_id = ?');
    $query->execute([$body['is_locked'] ? '1' : '0', $user['player_id'], $body['owned_morty_id']]);

    // The client replaces its decks from this response even though locking
    // changes no deck membership. Preserve empty decks as well as populated ones.
    $query = $pdo->prepare('SELECT deck_id, owned_morty_ids FROM decks WHERE player_id = ? ORDER BY deck_id');
    $query->execute([$user['player_id']]);
    $decks = [];
    foreach ($query as $deck) {
        $raw = (string)($deck['owned_morty_ids'] ?? '');
        $ids = json_decode($raw, true);
        if (!is_array($ids)) $ids = json_decode(stripcslashes($raw), true);
        $decks[] = ['deck_id' => (int)$deck['deck_id'],
                    'owned_morty_ids' => is_array($ids) ? array_values($ids) : []];
    }
    $pdo->commit();
    respond(200, ['active_deck_id' => (int)$user['active_deck_id'], 'decks' => $decks]);
} catch (Throwable $error) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    error_log('Morty lock operation failed: ' . get_class($error));
    respond(500, ['error' => ['code' => 'FAILED']]);
}
