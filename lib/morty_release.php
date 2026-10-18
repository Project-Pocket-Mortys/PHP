<?php
declare(strict_types=1);

final class MortyReleaseError extends RuntimeException {
    public int $status;
    public string $errorCode;

    public function __construct(int $status, string $errorCode = 'FAILED') {
        parent::__construct($errorCode);
        $this->status = $status;
        $this->errorCode = $errorCode;
    }
}

function morty_release_request($body): array {
    if (!is_array($body) || !is_string($body['session_id'] ?? null)
        || trim($body['session_id']) === '' || !is_array($body['owned_morty_ids'] ?? null)
        || !$body['owned_morty_ids'] || !array_is_list($body['owned_morty_ids'])) {
        throw new MortyReleaseError(400);
    }
    $ids = $body['owned_morty_ids'];
    foreach ($ids as $id) {
        if (!is_string($id) || trim($id) === '') throw new MortyReleaseError(400);
    }
    if (count(array_unique($ids, SORT_STRING)) !== count($ids)) throw new MortyReleaseError(400);
    return [$body['session_id'], $ids];
}

function morty_release_deck_ids(string $raw): array {
    // Decode without associative objects: {} must never become an empty deck.
    $ids = json_decode($raw);
    if (!is_array($ids)) $ids = json_decode(stripcslashes($raw));
    if (!is_array($ids)) throw new MortyReleaseError(409);
    foreach ($ids as $id) {
        if (!is_string($id) || trim($id) === '') throw new MortyReleaseError(409);
    }
    return $ids;
}

function morty_release_is_locked($value): bool {
    // Database flags include string "false"; a PHP boolean cast locks it.
    if ($value === null || $value === '') return false;
    $parsed = filter_var($value, FILTER_VALIDATE_BOOLEAN, FILTER_NULL_ON_FAILURE);
    if ($parsed === null) throw new MortyReleaseError(409);
    return $parsed;
}

/** Caller owns the transaction. Validation is identical for preview and confirm. */
function morty_release_plan(PDO $pdo, string $sessionId, array $ids): array {
    $query = $pdo->prepare('SELECT player_id, state, active_deck_id FROM users WHERE session_id = ? LIMIT 1 FOR UPDATE');
    $query->execute([$sessionId]);
    $user = $query->fetch();
    if (!$user) throw new MortyReleaseError(401);
    if ($user['state'] !== 'WORLD') throw new MortyReleaseError(409);
    $playerId = (string)$user['player_id'];

    // IDs are not unique in this schema, and attacks have no owner column.
    // Lock every global match and reject ambiguity before deleting any attacks.
    $query = $pdo->prepare('SELECT * FROM owned_morties WHERE owned_morty_id = ? ORDER BY id FOR UPDATE');
    $targets = [];
    $orderedIds = $ids;
    sort($orderedIds, SORT_STRING);
    foreach ($orderedIds as $id) {
        $query->execute([$id]);
        $matches = $query->fetchAll();
        if (count($matches) !== 1 || (string)$matches[0]['player_id'] !== $playerId
            || (string)$matches[0]['owned_morty_id'] !== $id) {
            throw new MortyReleaseError(404, 'OWNED_MORTY_ID_INVALID');
        }
        $morty = $matches[0];
        $pit = trim((string)($morty['fight_pit_id'] ?? ''));
        if (morty_release_is_locked($morty['is_locked'])
            || morty_release_is_locked($morty['is_trading_locked'])
            || ($pit !== '' && strtolower($pit) !== 'null')) {
            throw new MortyReleaseError(409);
        }
        $targets[] = $morty;
    }

    $in = implode(',', array_fill(0, count($ids), '?'));
    foreach ([['trades', 'morty_trade_id'], ['trade_offers', 'morty_offer_id']] as [$table, $column]) {
        $query = $pdo->prepare("SELECT id FROM $table WHERE $column IN ($in) FOR UPDATE");
        $query->execute($ids);
        if ($query->fetch()) throw new MortyReleaseError(409);
    }
    $query = $pdo->prepare("SELECT battle_id FROM battles WHERE state = 'ACTIVE' AND (player_active_morty IN ($in) OR opponent_active_morty IN ($in)) FOR UPDATE");
    $query->execute(array_merge($ids, $ids));
    if ($query->fetch()) throw new MortyReleaseError(409);

    $query = $pdo->prepare('SELECT owned_morty_id, hp FROM owned_morties WHERE player_id = ? ORDER BY id FOR UPDATE');
    $query->execute([$playerId]);
    $owned = $query->fetchAll();
    if (count($owned) <= count($ids)) throw new MortyReleaseError(409);
    $living = [];
    $ownedIds = [];
    foreach ($owned as $morty) {
        $ownedIds[(string)$morty['owned_morty_id']] = true;
        $hp = filter_var($morty['hp'], FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
        if ($hp !== false && $hp > 0) $living[(string)$morty['owned_morty_id']] = true;
    }
    $query = $pdo->prepare('SELECT id, deck_id, owned_morty_ids FROM decks WHERE player_id = ? ORDER BY deck_id, id FOR UPDATE');
    $query->execute([$playerId]);
    $decks = [];
    $updates = [];
    $activeSeen = false;
    $deckIds = [];
    foreach ($query->fetchAll() as $deck) {
        $deckId = filter_var($deck['deck_id'], FILTER_VALIDATE_INT);
        if ($deckId === false || isset($deckIds[$deckId])) throw new MortyReleaseError(409);
        $deckIds[$deckId] = true;
        $before = morty_release_deck_ids((string)$deck['owned_morty_ids']);
        $after = array_values(array_filter($before, static fn(string $id): bool => !in_array($id, $ids, true)));
        if ($deckId === (int)$user['active_deck_id']) {
            $activeSeen = true;
            $remainingOwned = array_filter($after, static fn(string $id): bool => isset($ownedIds[$id]));
            if (!$remainingOwned) throw new MortyReleaseError(409);
            $hadLiving = false;
            $hasLiving = false;
            foreach ($before as $id) if (isset($living[$id])) $hadLiving = true;
            foreach ($after as $id) if (isset($living[$id])) $hasLiving = true;
            if ($hadLiving && !$hasLiving) throw new MortyReleaseError(409);
        }
        $decks[] = ['deck_id' => $deckId, 'owned_morty_ids' => $before];
        if ($before !== $after) $updates[] = ['id' => $deck['id'], 'ids' => $after];
    }
    // An absent active deck cannot establish safe party membership.
    if (!$activeSeen) throw new MortyReleaseError(409);
    return ['player_id' => $playerId, 'active_deck_id' => (int)$user['active_deck_id'],
        'decks' => $decks, 'updates' => $updates, 'targets' => $targets];
}

function morty_release_apply(PDO $pdo, array $plan): array {
    $query = $pdo->prepare('UPDATE decks SET owned_morty_ids = ? WHERE id = ? AND player_id = ?');
    foreach ($plan['updates'] as $update) {
        $query->execute([json_encode($update['ids'], JSON_THROW_ON_ERROR), $update['id'], $plan['player_id']]);
    }
    $attacks = $pdo->prepare('DELETE FROM owned_attacks WHERE owned_morty_id = ?');
    $morties = $pdo->prepare('DELETE FROM owned_morties WHERE id = ? AND player_id = ? AND owned_morty_id = ?');
    foreach ($plan['targets'] as $morty) {
        $attacks->execute([$morty['owned_morty_id']]);
        $morties->execute([$morty['id'], $plan['player_id'], $morty['owned_morty_id']]);
        if ($morties->rowCount() !== 1) throw new MortyReleaseError(409);
    }
    $releasedIds = array_column($plan['targets'], 'owned_morty_id');
    $decks = $plan['decks'];
    foreach ($decks as &$deck) {
        $deck['owned_morty_ids'] = array_values(array_filter($deck['owned_morty_ids'],
            static fn(string $id): bool => !in_array($id, $releasedIds, true)));
    }
    unset($deck);
    return ['active_deck_id' => $plan['active_deck_id'], 'decks' => $decks];
}

function morty_release_endpoint(PDO $pdo, bool $confirm): void {
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
        header('Allow: POST');
        respond(405, ['error' => ['code' => 'FAILED']]);
    }
    try {
        $body = json_decode(file_get_contents('php://input'));
        // Preserve the JSON distinction between [] and objects with numeric keys.
        [$sessionId, $ids] = morty_release_request($body instanceof stdClass ? get_object_vars($body) : null);
        $pdo->beginTransaction();
        $plan = morty_release_plan($pdo, $sessionId, $ids);
        if ($confirm) {
            $response = morty_release_apply($pdo, $plan);
            $pdo->commit();
        } else {
            $response = ['active_deck_id' => $plan['active_deck_id'], 'decks' => $plan['decks']];
            $pdo->rollBack();
        }
        respond(200, $response);
    } catch (MortyReleaseError $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        respond($error->status, ['error' => ['code' => $error->errorCode]]);
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        error_log('Morty release failed: ' . get_class($error));
        respond(500, ['error' => ['code' => 'FAILED']]);
    }
}
