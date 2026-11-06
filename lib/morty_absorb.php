<?php
declare(strict_types=1);
require_once __DIR__ . '/world_action_guard.php';
require_once __DIR__ . '/morty_release.php';
require_once __DIR__ . '/trade_references.php';

final class MortyAbsorbError extends RuntimeException {
    public int $status;
    public function __construct(string $code, int $status = 200) {
        parent::__construct($code);
        $this->status = $status;
    }
}

function morty_absorb_request($body): array {
    // The legacy handler treats an omitted/null donor list as an empty list.
    $ids = $body instanceof stdClass ? ($body->absorb_owned_morty_ids ?? []) : null;
    if (!$body instanceof stdClass
        || !is_string($body->session_id ?? null) || trim($body->session_id) === ''
        || !is_string($body->owned_morty_id ?? null) || trim($body->owned_morty_id) === ''
        || !is_array($ids)) {
        throw new MortyAbsorbError('INVALID_REQUEST');
    }
    foreach ($ids as $id) {
        if (!is_string($id) || trim($id) === '') throw new MortyAbsorbError('INVALID_REQUEST');
    }
    // One consumed row grants one point, even when the client repeats its ID.
    return [$body->session_id, $body->owned_morty_id,
        array_values(array_unique($ids, SORT_STRING))];
}

/** Native CanBeBlended uses target first; NULL follows player-details' Normal default. */
function morty_absorb_compatible(array $target, array $donor): bool {
    $species = $target['morty_id'] ?? null;
    if (!is_string($species) || trim($species) === ''
        || $species !== ($donor['morty_id'] ?? null)) return false;
    $variants = [
        'Normal' => ['Normal', 'Shiny', 'Pulsing'],
        'Shiny' => ['Normal', 'Shiny'],
        'Pulsing' => ['Normal', 'Pulsing'],
    ];
    $targetVariant = $target['variant'] ?? 'Normal';
    $donorVariant = $donor['variant'] ?? 'Normal';
    // Fail closed on malformed legacy storage; do not rewrite or coerce it.
    return is_string($targetVariant) && isset($variants[$targetVariant])
        && in_array($donorVariant, $variants[$targetVariant], true);
}

/** Caller owns the transaction; the user lock serializes Lock and Absorb. */
function morty_absorb_apply(PDO $pdo, string $sessionId, string $targetId, array $ids): array {
    $query = $pdo->prepare('SELECT player_id, active_deck_id FROM users WHERE session_id = ? LIMIT 1 FOR UPDATE');
    $query->execute([$sessionId]);
    $user = $query->fetch();
    if (!$user) throw new MortyAbsorbError('NOT_AUTHENTICATED');
    $playerId = (string)$user['player_id'];
    if (world_action_has_active_battle($pdo, $playerId)) throw new MortyAbsorbError('FAILED', 409);

    // Establish the active membership before locking all affected instance IDs.
    // Keep inactive duplicate logical decks as individual rows, as before.
    $activeDeckId = filter_var($user['active_deck_id'], FILTER_VALIDATE_INT,
        ['options' => ['min_range' => 0]]);
    if ($activeDeckId === false) throw new MortyAbsorbError('FAILED', 409);
    $query = $pdo->prepare('SELECT id, deck_id, owned_morty_ids FROM decks WHERE player_id = ? ORDER BY deck_id, id FOR UPDATE');
    $query->execute([$playerId]);
    $decks = [];
    $activeIds = null;
    foreach ($query->fetchAll() as $deck) {
        $before = morty_release_deck_ids((string)$deck['owned_morty_ids']);
        $deckId = filter_var($deck['deck_id'], FILTER_VALIDATE_INT);
        if ($deckId !== false && $deckId === $activeDeckId) {
            if ($activeIds !== null) throw new MortyAbsorbError('FAILED', 409);
            $activeIds = $before;
        }
        $decks[] = ['id' => $deck['id'], 'deck_id' => (int)$deck['deck_id'], 'owned_morty_ids' => $before];
    }
    if ($activeIds === null) throw new MortyAbsorbError('FAILED', 409);

    // Logical IDs are not unique, while attacks carry no owner. Lock all global
    // matches in a stable order and reject ambiguity before any mutation.
    $ordered = array_values(array_unique(array_merge([$targetId], $ids, $activeIds), SORT_STRING));
    sort($ordered, SORT_STRING);
    $rows = [];
    $query = $pdo->prepare('SELECT * FROM owned_morties WHERE owned_morty_id = ? ORDER BY id FOR UPDATE');
    foreach ($ordered as $id) {
        $query->execute([$id]);
        $matches = $query->fetchAll();
        if (count($matches) > 1) throw new MortyAbsorbError('FAILED', 409);
        if (count($matches) === 1 && (string)$matches[0]['player_id'] === $playerId
            && (string)$matches[0]['owned_morty_id'] === $id) $rows[$id] = $matches[0];
    }
    if (!isset($rows[$targetId])) throw new MortyAbsorbError('NOT_FOUND');
    $target = $rows[$targetId];
    // The native target picker permits ordinary locks but excludes trade locks.
    if (morty_release_is_locked($target['is_trading_locked'])) throw new MortyAbsorbError('FAILED', 409);
    $donors = [];
    foreach ($ids as $id) {
        // Keep the legacy filtering of missing, foreign, and recipient IDs.
        if ($id === $targetId || !isset($rows[$id])) continue;
        $morty = $rows[$id];
        $pit = trim((string)($morty['fight_pit_id'] ?? ''));
        if (morty_release_is_locked($morty['is_locked'])
            || morty_release_is_locked($morty['is_trading_locked'])
            || ($pit !== '' && strtolower($pit) !== 'null')) {
            throw new MortyAbsorbError('FAILED', 409);
        }
        if (!morty_absorb_compatible($target, $morty)) {
            throw new MortyAbsorbError('ABSORB_INVALID_MORTY', 409);
        }
        $donors[] = $morty;
    }
    if (!$donors) throw new MortyAbsorbError('NO_VALID_MORTYS');
    $removed = array_column($donors, 'owned_morty_id');
    if (trade_reference_any_locked($pdo, array_merge([$targetId], $removed))) {
        throw new MortyAbsorbError('FAILED', 409);
    }
    $points = $target['evolution_points'] === null ? 0
        : filter_var($target['evolution_points'], FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
    if ($points === false || $points > PHP_INT_MAX - count($donors)) throw new MortyAbsorbError('FAILED', 409);

    // This endpoint only adds points, including at a native evolution threshold.
    // No created/evolved Morty may be assumed to replace consumed party members.
    $living = false;
    foreach ($activeIds as $id) {
        if (in_array($id, $removed, true) || !isset($rows[$id])) continue;
        $hp = filter_var($rows[$id]['hp'], FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if ($hp !== false) $living = true;
    }
    if (!$living) throw new MortyAbsorbError('FAILED', 409);
    foreach ($decks as &$deck) {
        $deck['owned_morty_ids'] = array_values(array_filter($deck['owned_morty_ids'],
            static fn(string $id): bool => !in_array($id, $removed, true)));
    }
    unset($deck);

    $attacks = $pdo->prepare('DELETE FROM owned_attacks WHERE owned_morty_id = ?');
    $delete = $pdo->prepare('DELETE FROM owned_morties WHERE id = ? AND player_id = ? AND owned_morty_id = ?');
    foreach ($donors as $morty) {
        $attacks->execute([$morty['owned_morty_id']]);
        $delete->execute([$morty['id'], $playerId, $morty['owned_morty_id']]);
        if ($delete->rowCount() !== 1) throw new MortyAbsorbError('FAILED', 409);
    }
    $update = $pdo->prepare('UPDATE decks SET owned_morty_ids = ? WHERE id = ? AND player_id = ?');
    $responseDecks = [];
    foreach ($decks as $deck) {
        $update->execute([json_encode($deck['owned_morty_ids'], JSON_THROW_ON_ERROR), $deck['id'], $playerId]);
        $responseDecks[] = ['deck_id' => $deck['deck_id'], 'owned_morty_ids' => $deck['owned_morty_ids']];
    }
    // Preserve the established counter behavior; evolution itself is separate.
    $newPoints = $points + count($donors);
    $update = $pdo->prepare('UPDATE owned_morties SET evolution_points = ? WHERE id = ? AND player_id = ? AND owned_morty_id = ?');
    $update->execute([$newPoints, $target['id'], $playerId, $targetId]);
    if ($update->rowCount() !== 1) throw new MortyAbsorbError('FAILED', 409);
    return ['removed' => $removed,
        'modified' => ['owned_morty_id' => $targetId, 'evolution_points' => $newPoints],
        'decks' => $responseDecks];
}

function morty_absorb_endpoint(PDO $pdo): void {
    try {
        [$sessionId, $targetId, $ids] = morty_absorb_request(json_decode(file_get_contents('php://input')));
        $pdo->beginTransaction();
        $response = morty_absorb_apply($pdo, $sessionId, $targetId, $ids);
        $pdo->commit();
        respond(200, $response);
    } catch (MortyAbsorbError $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        respond($error->status, ['error' => ['code' => $error->getMessage()]]);
    } catch (MortyReleaseError $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        respond(409, ['error' => ['code' => 'FAILED']]);
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        error_log('Morty absorb failed: ' . get_class($error));
        respond(500, ['error' => ['code' => 'SERVER_ERROR']]);
    }
}
