<?php
declare(strict_types=1);

require_once __DIR__ . '/battle_membership_guard.php';
require_once __DIR__ . '/trade_references.php';

final class TradeListingError extends RuntimeException {
    public function __construct(public int $status, string $code = 'FAILED') {
        parent::__construct($code);
    }
}

/** Preserve legacy request defaults, but never coerce provided JSON values. */
function trade_listing_body($body, bool $offer): array {
    if (!$body instanceof stdClass) throw new TradeListingError(400);
    $data = get_object_vars($body);
    $required = $offer
        ? ['session_id', 'player_id', 'offered_morty_id', 'trade_request_id']
        : ['session_id', 'owned_morty_id'];
    foreach ($required as $key) {
        if (!array_key_exists($key, $data)) throw new TradeListingError(400);
    }
    $strings = $offer ? $required : ['session_id', 'player_id', 'owned_morty_id', 'requested_morty_id', 'request_variant'];
    foreach ($strings as $key) {
        if (!array_key_exists($key, $data)) continue;
        if (!is_string($data[$key]) || trim($data[$key]) === ''
            || strlen($data[$key]) > ($key === 'session_id' ? 255 : 64)) throw new TradeListingError(400);
    }
    if (!$offer) {
        $data += ['player_id' => null, 'requested_morty_id' => 'any', 'request_variant' => 'Normal', 'is_free_trade' => false];
        if (!is_bool($data['is_free_trade']) || !in_array($data['request_variant'], ['Normal', 'Shiny', 'Pulsing'], true)) {
            throw new TradeListingError(400);
        }
    }
    return $data;
}

function trade_listing_rows(PDO $pdo, string $sql, array $args): array {
    $query = $pdo->prepare($sql);
    $query->execute($args);
    return $query->fetchAll(PDO::FETCH_ASSOC);
}

/** Both creation routes serialize on the actor before parent/reference reads. */
function trade_listing_actor_lock(PDO $pdo, string $session, ?string $player): array {
    if ($pdo->inTransaction()) throw new LogicException('Standalone listing creation required');
    $pdo->beginTransaction();
    $users = trade_listing_rows($pdo, 'SELECT * FROM users WHERE session_id=? ORDER BY id FOR UPDATE', [$session]);
    if (!$users) throw new TradeListingError(401);
    if (count($users) !== 1 || $users[0]['session_id'] !== $session) throw new TradeListingError(409);
    $user = $users[0];
    if (!is_string($user['player_id']) || trim($user['player_id']) === '') throw new TradeListingError(409);
    if ($player !== null && $player !== $user['player_id']) throw new TradeListingError(403);
    $owners = trade_listing_rows($pdo, 'SELECT * FROM users WHERE player_id=? ORDER BY id FOR UPDATE', [$user['player_id']]);
    if (count($owners) !== 1 || $owners[0]['id'] !== $user['id']
        || $owners[0]['player_id'] !== $user['player_id'] || $owners[0]['session_id'] !== $session) {
        throw new TradeListingError(409);
    }
    // These locking reads establish no older snapshot before the shared guard.
    if (battle_has_shared_membership($pdo, $user['player_id'])) throw new TradeListingError(409);
    return $owners[0];
}

function trade_listing_parent_lock(PDO $pdo, string $id): array {
    $trades = trade_listing_rows($pdo, 'SELECT * FROM trades WHERE trade_id=? ORDER BY id FOR UPDATE', [$id]);
    if (!$trades) throw new TradeListingError(404, 'TRADE_NO_TRADE_EXISTS');
    if (count($trades) !== 1 || $trades[0]['trade_id'] !== $id) throw new TradeListingError(409);
    return $trades[0];
}

function trade_listing_locked($value): bool {
    if ($value === null || $value === '') return false;
    $parsed = filter_var($value, FILTER_VALIDATE_BOOLEAN, FILTER_NULL_ON_FAILURE);
    if ($parsed === null) throw new TradeListingError(409);
    return $parsed;
}

/** Lock only the active deck; saved inactive decks do not exclude candidates. */
function trade_listing_active_deck_excludes(PDO $pdo, array $user, array $morty, string $unavailable): void {
    $deckId = filter_var($user['active_deck_id'] ?? null, FILTER_VALIDATE_INT,
        ['options' => ['min_range' => 0, 'max_range' => 2147483647]]);
    if ($deckId === false || is_bool($user['active_deck_id'] ?? null)) throw new TradeListingError(409);
    $decks = trade_listing_rows($pdo, 'SELECT * FROM decks WHERE player_id=? AND deck_id=? ORDER BY id FOR UPDATE', [$user['player_id'], $deckId]);
    if (count($decks) !== 1 || $decks[0]['player_id'] !== $user['player_id']
        || !is_string($decks[0]['owned_morty_ids'])) throw new TradeListingError(409);
    $raw = $decks[0]['owned_morty_ids'];
    $ids = json_decode($raw);
    if (!is_array($ids)) $ids = json_decode(stripcslashes($raw));
    if (!is_array($ids)) throw new TradeListingError(409);
    foreach ($ids as $id) {
        if (!is_string($id) || trim($id) === '') throw new TradeListingError(409);
    }
    if (!$ids) return;
    // Compare with the database's logical-ID collation too: an alias in a deck
    // must not bypass active membership of this already locked physical row.
    $in = implode(',', array_fill(0, count($ids), '?'));
    $query = $pdo->prepare("SELECT id FROM owned_morties WHERE id=? AND owned_morty_id IN ($in) FOR UPDATE");
    $query->execute(array_merge([$morty['id']], $ids));
    if ($query->fetchColumn() !== false) throw new TradeListingError(409, $unavailable);
}

function trade_listing_morty_lock(PDO $pdo, array $user, string $id, bool $offer): array {
    $ownership = $offer ? 'TRADE_OFFER_MORTY_DOES_NOT_BELONG_TO_OFFERING_PLAYER'
        : 'TRADE_REQUEST_MORTY_DOES_NOT_BELONG_TO_PLAYER';
    $unavailable = $offer ? 'FAILED' : 'TRADE_MORTY_LOCKED';
    // Logical instance IDs have no unique database constraint. Owner-filtered
    // LIMIT 1 could authorize a duplicate or an alias owned by another player.
    $morties = trade_listing_rows($pdo, 'SELECT * FROM owned_morties WHERE owned_morty_id=? ORDER BY id FOR UPDATE', [$id]);
    if (!$morties) throw new TradeListingError($offer ? 404 : 403, $offer ? 'TRADE_NO_SUCH_MORTY' : $ownership);
    if (count($morties) !== 1 || $morties[0]['owned_morty_id'] !== $id) throw new TradeListingError(409);
    $morty = $morties[0];
    if ($morty['player_id'] !== $user['player_id']) throw new TradeListingError(403, $ownership);
    if (trade_listing_locked($morty['is_locked']) || trade_listing_locked($morty['is_trading_locked'])
        || trade_reference_any_locked($pdo, [$id])) throw new TradeListingError(409, $unavailable);
    trade_listing_active_deck_excludes($pdo, $user, $morty, $unavailable);
    return $morty;
}

/** The native 'any' selection bypasses both species and variant restrictions. */
function trade_listing_offer_criteria(array $trade, array $morty): void {
    // Match get-trades' legacy defaults so the offered criteria agree with the
    // request displayed to the native client, including old NULL/empty fields.
    $requested = ($trade['requested_morty_id'] ?? null) ?: 'any';
    $variant = ($trade['request_variant'] ?? null) ?: 'Normal';
    if ($requested === 'any') return;
    if (!is_string($requested) || trim($requested) === ''
        || !in_array($variant, ['Normal', 'Shiny', 'Pulsing'], true)) throw new TradeListingError(409);
    $ownedVariant = $morty['variant'] ?? 'Normal';
    if ($morty['morty_id'] !== $requested || $ownedVariant !== $variant) {
        throw new TradeListingError(409, 'TRADE_MORTY_NOT_MATCH_CRITERIA');
    }
}

function trade_listing_error(PDO $pdo, Throwable $error): void {
    if ($pdo->inTransaction()) $pdo->rollBack();
    if (!$error instanceof TradeListingError) error_log('Trade listing creation failed: ' . get_class($error));
    http_response_code($error instanceof TradeListingError ? $error->status : 500);
    echo json_encode(['error' => ['code' => $error instanceof TradeListingError ? $error->getMessage() : 'FAILED']]);
}
